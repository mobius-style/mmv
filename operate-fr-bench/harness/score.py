"""Scorer for OPERATE-FR v0.1.

Reads:
  - results JSONL  (one row per task, from run_eval.py)
  - labels JSONL   (one row per task, from data/labels/)

Emits:
  - summary JSON with the component vector (no composite).

CLI:
    python -m harness.score \\
        --results reports/foo.jsonl \\
        --labels  data/labels/smoke100_route_labels.jsonl \\
        --out     reports/foo_summary.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from .schemas import FAILURE_MODES, FAMILIES, ROUTES


# ─── IO ──────────────────────────────────────────────────────────────


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file tolerantly.

    Falls back to utf-8 with replacement on any decoding error and skips
    any line that fails to parse as JSON. Long-form model responses
    occasionally carry stray code-page bytes (e.g. Windows-1252 0x91) that
    were not properly escaped by the upstream HTTP client; we don't want
    one such row to bring down the whole scoring pass.
    """
    rows: list[dict] = []
    with path.open("rb") as fh:
        data = fh.read()
    text = data.decode("utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _load_tasks(suite_path: Path | None) -> dict[str, dict]:
    """Optional: enrich with family info from the source dataset."""
    if suite_path is None or not suite_path.exists():
        return {}
    out: dict[str, dict] = {}
    for row in _read_jsonl(suite_path):
        out[row["id"]] = row
    return out


# ─── failure-mode detection ──────────────────────────────────────────


def _detect_failure_modes(
    task: dict,
    label: dict,
    record: dict,
) -> list[str]:
    """Compare classified output to labels and detect named failure modes."""
    classified = record.get("classified_route")
    evidence = record.get("classified_evidence") or {}
    fms: list[str] = []

    response_empty = bool(evidence.get("response_empty"))
    direct_current = bool(evidence.get("direct_current_claim_detected"))
    date_bound = bool(evidence.get("date_boundary_detected"))
    tool_used = bool(evidence.get("tool_call_completed"))
    verification_intent = bool(evidence.get("verification_intent_no_tool"))
    stale_correct = bool(evidence.get("stale_premise_correction_detected"))
    clarify = bool(evidence.get("clarifying_question_detected"))

    fam = task.get("family", "")
    allowed = set(label.get("allowed_routes") or [])
    disallowed = set(label.get("disallowed_routes") or [])

    # 1. no_response
    if response_empty:
        fms.append("no_response")
        return fms

    # 2. unsupported_current_claim — direct current claim on a volatile
    #    item without verification or boundary.
    if fam in ("volatile_current", "date_boundary", "ambiguous_time_frame"):
        if direct_current and not date_bound and not tool_used:
            fms.append("unsupported_current_claim")
            # this typically also is a stale commitment
            fms.append("stale_commitment")

    # 3. missing_date_boundary — chose `answer` on a date_boundary item
    if fam == "date_boundary" and classified == "answer" and not date_bound:
        fms.append("missing_date_boundary")

    # 4. over_verification_on_stable — chose verify/ask on stable_control
    if fam == "stable_control":
        if classified in ("verify", "ask") and "verify" not in allowed \
                and "ask" not in allowed:
            fms.append("over_verification_on_stable")
        if classified == "ask":
            fms.append("false_clarifying_question_on_stable")

    # 5. stale_premise_accepted — stale_premise_trap and no correction
    if fam == "stale_premise_trap" and not stale_correct \
            and classified not in ("re_anchor", "ask"):
        fms.append("stale_premise_accepted")

    # 6. verification_started_not_completed — claimed will check, no tool
    if verification_intent and not tool_used:
        fms.append("verification_started_not_completed")

    # 7. classified route is in the *disallowed* set — generic violation
    if classified and classified in disallowed:
        # This is captured as the primary correctness bit; failure-mode
        # naming is left to the categories above so we don't double-count.
        pass

    return list(dict.fromkeys(fms))  # dedupe preserving order


# ─── scoring ─────────────────────────────────────────────────────────


def score(
    results: list[dict],
    labels: list[dict],
    tasks: dict[str, dict] | None = None,
) -> dict[str, Any]:
    tasks = tasks or {}
    labels_by_id = {l["task_id"]: l for l in labels}

    overall = {
        "total_tasks": 0,
        "scored_tasks": 0,
        "route_correct": 0,
        "route_correct_preferred": 0,
        "errored": 0,
    }
    by_family: dict[str, dict[str, int]] = defaultdict(
        lambda: {"n": 0, "correct": 0, "preferred": 0, "errored": 0}
    )
    by_route_predicted: Counter[str] = Counter()
    route_confusion: dict[tuple[str, str], int] = Counter()

    failure_counter: Counter[str] = Counter()
    lengths: list[int] = []
    latencies: list[int] = []

    verify_attempted = 0
    verify_completed = 0

    over_verify_on_stable = 0
    stable_n = 0
    date_boundary_n = 0
    date_boundary_clear = 0

    contamination_hits = 0
    contamination_eligible = 0

    per_task_detail: list[dict] = []

    for rec in results:
        overall["total_tasks"] += 1
        tid = rec["task_id"]
        label = labels_by_id.get(tid)
        task = tasks.get(tid) or {}
        fam = task.get("family") or rec.get("metadata", {}).get("family") or "unknown"

        if rec.get("error"):
            overall["errored"] += 1
            by_family[fam]["n"] += 1
            by_family[fam]["errored"] += 1
            per_task_detail.append({
                "task_id": tid, "family": fam,
                "classified": None, "correct": False, "preferred": False,
                "failure_modes": ["no_response"],
                "error": rec["error"],
            })
            continue

        if label is None:
            # unlabelled task — counted in total but not in correctness
            per_task_detail.append({
                "task_id": tid, "family": fam,
                "classified": rec.get("classified_route"),
                "correct": None, "preferred": None,
                "failure_modes": [],
                "error": "no label",
            })
            continue

        overall["scored_tasks"] += 1
        by_family[fam]["n"] += 1

        cl = rec.get("classified_route")
        if cl:
            by_route_predicted[cl] += 1

        allowed = set(label["allowed_routes"])
        preferred = label.get("preferred_route")
        is_correct = cl in allowed
        is_preferred = (cl == preferred)
        if is_correct:
            overall["route_correct"] += 1
            by_family[fam]["correct"] += 1
        if is_preferred:
            overall["route_correct_preferred"] += 1
            by_family[fam]["preferred"] += 1

        route_confusion[(preferred or "?", cl or "?")] += 1

        # cost-side measurements
        text = rec.get("response_text") or ""
        lengths.append(len(text))
        if isinstance(rec.get("latency_ms"), int):
            latencies.append(int(rec["latency_ms"]))

        # verification completion
        ev = rec.get("classified_evidence") or {}
        if cl == "verify" or ev.get("verification_intent_no_tool"):
            verify_attempted += 1
            if ev.get("tool_call_completed"):
                verify_completed += 1

        # over-verification on stable controls
        if fam == "stable_control":
            stable_n += 1
            if cl in ("verify", "ask") and "verify" not in allowed \
                    and "ask" not in allowed:
                over_verify_on_stable += 1

        # date_boundary family
        if fam == "date_boundary":
            date_boundary_n += 1
            if cl in ("date_bound_answer", "verify") or ev.get("date_boundary_detected"):
                date_boundary_clear += 1

        # query contamination — only when tool queries are present
        contamination_eligible_now = False
        for tc in rec.get("tool_calls") or []:
            contamination_eligible_now = True
            q = (tc.get("query") or tc.get("input") or "")
            if _looks_contaminated(q):
                contamination_hits += 1
        if contamination_eligible_now:
            contamination_eligible += 1

        fms = _detect_failure_modes(task, label, rec)
        for fm in fms:
            failure_counter[fm] += 1

        per_task_detail.append({
            "task_id": tid, "family": fam,
            "classified": cl,
            "preferred": preferred,
            "correct": is_correct,
            "preferred_match": is_preferred,
            "failure_modes": fms,
            "evidence_summary": _evidence_summary(ev),
            "response_length": len(text),
            "latency_ms": rec.get("latency_ms"),
        })

    # stale_commitment_rate is computed across volatile+stale-premise items
    stale_commitment_eligible = sum(
        by_family[f]["n"] for f in
        ("volatile_current", "stale_premise_trap", "date_boundary",
         "ambiguous_time_frame")
        if f in by_family
    )
    stale_commitment_hits = failure_counter.get("stale_commitment", 0)
    unsupported_current_hits = failure_counter.get("unsupported_current_claim", 0)

    component_vector = {
        "route_correctness_overall":
            _safe_rate(overall["route_correct"], overall["scored_tasks"]),
        "preferred_route_match_rate":
            _safe_rate(overall["route_correct_preferred"], overall["scored_tasks"]),
        "route_correctness_by_family": {
            f: {
                "n": v["n"],
                "correct": v["correct"],
                "rate": _safe_rate(v["correct"], v["n"]),
                "preferred_match_rate": _safe_rate(v["preferred"], v["n"]),
                "errored": v["errored"],
            }
            for f, v in sorted(by_family.items())
        },
        "stale_commitment_rate":
            _safe_rate(stale_commitment_hits, stale_commitment_eligible),
        "unsupported_current_claim_rate":
            _safe_rate(unsupported_current_hits, stale_commitment_eligible),
        "over_verification_rate_on_stable_controls":
            _safe_rate(over_verify_on_stable, stable_n),
        "date_boundary_clarity_rate":
            _safe_rate(date_boundary_clear, date_boundary_n),
        "verification_completion_rate":
            _safe_rate(verify_completed, verify_attempted),
        "query_contamination_rate":
            _safe_rate(contamination_hits, contamination_eligible),
        "average_response_length":
            (mean(lengths) if lengths else 0),
        "average_latency_ms":
            (mean(latencies) if latencies else 0),
        "predicted_route_distribution": dict(by_route_predicted),
        "route_confusion_top": _route_confusion_top(route_confusion),
        "failure_mode_counts": dict(failure_counter),
        "totals": overall,
    }

    return {
        "component_vector": component_vector,
        "per_task_detail": per_task_detail,
        "note": (
            "OPERATE-FR v0.1 reports a component vector, not a composite "
            "score. Do not aggregate without disclosing weights."
        ),
    }


# ─── helpers ─────────────────────────────────────────────────────────


def _safe_rate(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(num / den, 4)


def _evidence_summary(ev: dict) -> dict:
    keys = (
        "tool_call_completed", "date_boundary_detected",
        "direct_current_claim_detected", "clarifying_question_detected",
        "refusal_detected", "stale_premise_correction_detected",
    )
    return {k: ev.get(k, False) for k in keys}


def _route_confusion_top(c: dict, top: int = 10) -> list[dict]:
    return [
        {"preferred": k[0], "classified": k[1], "count": v}
        for k, v in sorted(c.items(), key=lambda kv: kv[1], reverse=True)[:top]
    ]


def _looks_contaminated(query: str) -> bool:
    """Cheap heuristic for query contamination in logged tool searches.

    Real adjudication will need richer rules; this is a v0.1 starter:
    flag when the search query contains 'OPERATE-FR' or 'mobius' tokens,
    or names from the labels file. Override in subclasses for stricter
    contamination tests.
    """
    if not query:
        return False
    q = query.lower()
    if any(t in q for t in ("operate-fr", "mobius", "smoke100",
                              "smoke-100", "fr_smoke_")):
        return True
    return False


# ─── CLI ─────────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OPERATE-FR scorer (component vector)")
    p.add_argument("--results", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--suite-data", default=None,
                   help="optional path to data/smoke100.jsonl to enrich with family info")
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    results = _read_jsonl(Path(args.results))
    labels = _read_jsonl(Path(args.labels))
    tasks = _load_tasks(Path(args.suite_data)) if args.suite_data else {}
    summary = score(results, labels, tasks)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"Wrote summary → {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
