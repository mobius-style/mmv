#!/usr/bin/env python3
"""Smoke runner for v0.1-rc2 route-calibration patch.

Uses scripts.pseudo_ui_runner.PseudoUISession (same harness as
Phase 5C). Captures route, reason_codes, response_text excerpt per
query. No judge call. Compares against the Phase 5C v0.1-rc1 baseline
already saved in `eval/p9_evidence_pack_v1/holdout_eval_results.jsonl`
for the same query IDs (where available).

Output:
  results.jsonl      — per-query trace with rc1_baseline comparison
  summary.json       — aggregate metrics + regression guard
  summary.md         — human-readable summary
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

OUT_DIR = Path(__file__).resolve().parent
INP = OUT_DIR / "smoke_input.jsonl"
RES_JSONL = OUT_DIR / "results.jsonl"
SUMMARY = OUT_DIR / "summary.json"
SUMMARY_MD = OUT_DIR / "summary.md"

# Phase 5C v0.1-rc1 baseline (already saved):
RC1_BASELINE = ROOT / "eval/p9_evidence_pack_v1/holdout_eval_results.jsonl"


def load_baseline_by_id() -> dict:
    out = {}
    if not RC1_BASELINE.exists():
        return out
    for line in RC1_BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        out[r["id"]] = r
    return out


def classify(expected: str, actual: str) -> str:
    if expected == actual:
        return "match"
    if expected in ("ask", "verify", "abstain") and actual == "answer":
        return "A"   # over-answer (Cat A)
    if expected == "answer" and actual == "ask":
        return "B"   # excess clarification
    if expected == "answer" and actual == "verify":
        return "C"   # cautious verify on direct-answer
    if expected == "verify" and actual == "ask":
        return "C"
    return "other"


def detect_strict_evidence_failure(text: str) -> bool:
    """Heuristic: is the response a clear over-verification refusal? We
    flag only phrases that signal "I refused to answer because retrieval
    missed", not generic "based on the source" citations.
    """
    if not text:
        return False
    t = text.lower()
    markers = [
        "cannot answer",
        "do not contain information",
        "does not contain information",
        "based strictly on the retri",
        "unable to answer",
        "no information was provided",
        "the retrieved sources do not",
        "the provided sources do not",
        "i cannot answer",
        "the retrieved source only",
        "i cannot provide",
        "not covered in the provided",
        "is not in the retrieved",
    ]
    return any(m in t for m in markers)


def main() -> int:
    from scripts.pseudo_ui_runner import PseudoUISession
    pairs = []
    for line in INP.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        pairs.append(json.loads(line))
    print(f"loaded {len(pairs)} queries", flush=True)

    baseline = load_baseline_by_id()
    print(f"baseline rows available for cross-ref: {len(baseline)}", flush=True)

    rows = []
    cat_counts = {}                              # category → {match,A,B,C,other,n}
    rc2_strict_evidence = 0
    rc1_strict_evidence_for_same_ids = 0
    direct_answer_cats = {"specialized_terminology", "conceptual_explanation",
                          "casual_smalltalk"}
    restraint_cats     = {"ambiguous_underspecified", "continuation"}
    aux_fallback_count = 0

    t0 = time.time()
    for i, q in enumerate(pairs, 1):
        sess = PseudoUISession()
        try:
            r = sess.process_turn(q["query"])
            actual_route = r.route or "(empty)"
            rcs = list(r.reason_codes or [])
            text = r.response_text or ""
        except Exception as e:
            actual_route = "(error)"
            rcs = [f"harness_error:{type(e).__name__}"]
            text = ""

        cat = classify(q["expected_route"], actual_route)
        is_strict_fail = detect_strict_evidence_failure(text)
        if is_strict_fail:
            rc2_strict_evidence += 1
        if "WIKI_INSUFFICIENT_AUX_FALLBACK" in rcs:
            aux_fallback_count += 1

        bcat = q["category"]
        if bcat not in cat_counts:
            cat_counts[bcat] = {"n": 0, "match": 0, "A": 0, "B": 0, "C": 0,
                                 "other": 0, "strict_evidence_fail": 0,
                                 "aux_fallback_fired": 0}
        cat_counts[bcat]["n"] += 1
        cat_counts[bcat][cat] += 1
        if is_strict_fail:
            cat_counts[bcat]["strict_evidence_fail"] += 1
        if "WIKI_INSUFFICIENT_AUX_FALLBACK" in rcs:
            cat_counts[bcat]["aux_fallback_fired"] += 1

        # Per-query baseline (rc1) comparison.
        b = baseline.get(q["id"])
        rc1_route = (b or {}).get("actual_route", "")
        rc1_rcs = (b or {}).get("reason_codes", [])
        # rc1 strict-evidence fail flag — we have rcs but not response_text
        # in the baseline, so use reason_codes as a coarse proxy:
        # WIKI_INSUFFICIENT_ESCALATED + verify route → strict-fail-likely
        rc1_strict_fail_proxy = False
        if b is not None:
            if ("WIKI_INSUFFICIENT_ESCALATED" in rc1_rcs and
                    rc1_route == "verify"):
                rc1_strict_fail_proxy = True
            elif ("DEFINITIONAL_NEEDS_EVIDENCE" in rc1_rcs and
                    rc1_route == "verify"):
                rc1_strict_fail_proxy = True
        if rc1_strict_fail_proxy:
            rc1_strict_evidence_for_same_ids += 1

        rows.append({
            "id": q["id"],
            "category": q["category"],
            "query": q["query"],
            "expected_route": q["expected_route"],
            "rc2_actual_route": actual_route,
            "rc2_cat": cat,
            "rc2_reason_codes": rcs[:8],
            "rc2_response_excerpt": text[:240],
            "rc2_strict_evidence_fail": is_strict_fail,
            "rc2_aux_fallback_fired": "WIKI_INSUFFICIENT_AUX_FALLBACK" in rcs,
            "rc1_actual_route": rc1_route,
            "rc1_reason_codes": rc1_rcs,
            "rc1_strict_fail_proxy": rc1_strict_fail_proxy,
        })

        if i % 10 == 0 or i == len(pairs):
            elapsed = time.time() - t0
            print(f"  [{i}/{len(pairs)}] elapsed={elapsed:.1f}s "
                  f"strict_evidence_fail={rc2_strict_evidence} "
                  f"aux_fallback={aux_fallback_count}", flush=True)

    # Aggregate by domain group.
    direct_answer_n  = sum(cat_counts[c]["n"] for c in direct_answer_cats if c in cat_counts)
    direct_answer_strict_fail_rc2 = sum(
        cat_counts[c]["strict_evidence_fail"] for c in direct_answer_cats if c in cat_counts
    )
    direct_answer_aux_fallback = sum(
        cat_counts[c]["aux_fallback_fired"] for c in direct_answer_cats if c in cat_counts
    )
    restraint_n  = sum(cat_counts[c]["n"] for c in restraint_cats if c in cat_counts)
    restraint_cat_A_rc2 = sum(
        cat_counts[c]["A"] for c in restraint_cats if c in cat_counts
    )
    fresh_cat = "factual_inquiry"
    fresh_n = cat_counts.get(fresh_cat, {}).get("n", 0)
    fresh_cat_A_rc2 = cat_counts.get(fresh_cat, {}).get("A", 0)

    # rc1 strict-evidence proxy in same direct-answer ids
    rc1_strict_da = 0
    for r in rows:
        if r["category"] in direct_answer_cats and r["rc1_strict_fail_proxy"]:
            rc1_strict_da += 1
    # Also look at rc1 baseline rows that hit WIKI_INSUFFICIENT_ESCALATED
    # in direct-answer cats AND came back with answer-route — these were
    # the borderline cases where rc1 escalated but produced text.
    rc1_da_escalated = 0
    for r in rows:
        if r["category"] in direct_answer_cats and "WIKI_INSUFFICIENT_ESCALATED" in (r["rc1_reason_codes"] or []):
            rc1_da_escalated += 1

    summary = {
        "test": "v0_1_rc2_route_calibration_smoke",
        "n_total": len(rows),
        "elapsed_s": round(time.time() - t0, 1),
        "by_category": cat_counts,

        "direct_answer_categories": sorted(direct_answer_cats),
        "direct_answer_n": direct_answer_n,
        "direct_answer_strict_evidence_fail_rc2": direct_answer_strict_fail_rc2,
        "direct_answer_aux_fallback_fired_rc2": direct_answer_aux_fallback,
        "direct_answer_rc1_wiki_insufficient_escalated": rc1_da_escalated,

        "restraint_categories": sorted(restraint_cats),
        "restraint_n": restraint_n,
        "restraint_cat_A_rc2": restraint_cat_A_rc2,

        "freshness_category": fresh_cat,
        "freshness_n": fresh_n,
        "freshness_cat_A_rc2": fresh_cat_A_rc2,

        "regression_guards": {
            "restraint_cat_A_rate_rc2": (
                round(restraint_cat_A_rc2 / restraint_n, 4)
                if restraint_n else None
            ),
            "freshness_cat_A_rate_rc2": (
                round(fresh_cat_A_rc2 / fresh_n, 4)
                if fresh_n else None
            ),
        },
        "method": (
            "Pseudo-UI smoke. Cat A = expected ask|verify|abstain & actual answer. "
            "Strict-evidence fail = heuristic phrase match in response_text "
            "('cannot answer', 'do not contain information', etc.) — "
            "indicates the over-verification mode Phase 5C surfaced."
        ),
    }

    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    RES_JSONL.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    md = []
    md.append("# Route-calibration smoke (v0.1-rc2) — summary")
    md.append("")
    md.append(f"- N total: {summary['n_total']}")
    md.append(f"- Elapsed: {summary['elapsed_s']} s")
    md.append("")
    md.append("## Direct-answer categories (target of patch)")
    md.append("")
    md.append("| metric | value |")
    md.append("|---|---|")
    md.append(f"| n | {direct_answer_n} |")
    md.append(f"| rc2 strict-evidence-fail responses | {direct_answer_strict_fail_rc2} |")
    md.append(f"| rc2 WIKI_INSUFFICIENT_AUX_FALLBACK firings | {direct_answer_aux_fallback} |")
    md.append(f"| rc1 had WIKI_INSUFFICIENT_ESCALATED on same ids | {rc1_da_escalated} |")
    md.append("")
    md.append("## Restraint categories (regression guard)")
    md.append("")
    md.append("| metric | value |")
    md.append("|---|---|")
    md.append(f"| n | {restraint_n} |")
    md.append(f"| rc2 Cat A (over-answered) | {restraint_cat_A_rc2} |")
    md.append(f"| rc2 Cat A rate | {summary['regression_guards']['restraint_cat_A_rate_rc2']} |")
    md.append("")
    md.append("## Freshness / volatile-fact (regression guard)")
    md.append("")
    md.append("| metric | value |")
    md.append("|---|---|")
    md.append(f"| n | {fresh_n} |")
    md.append(f"| rc2 Cat A | {fresh_cat_A_rc2} |")
    md.append(f"| rc2 Cat A rate | {summary['regression_guards']['freshness_cat_A_rate_rc2']} |")
    md.append("")
    md.append("## Per-category breakdown")
    md.append("")
    md.append("| category | n | match | A | B | C | other | strict_evidence_fail | aux_fallback |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for cat in ("specialized_terminology","conceptual_explanation","casual_smalltalk",
                "ambiguous_underspecified","continuation","factual_inquiry"):
        if cat not in cat_counts:
            continue
        d = cat_counts[cat]
        md.append(f"| {cat} | {d['n']} | {d['match']} | {d['A']} | {d['B']} | "
                  f"{d['C']} | {d['other']} | {d['strict_evidence_fail']} | "
                  f"{d['aux_fallback_fired']} |")
    SUMMARY_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"\nwrote: {RES_JSONL}\nwrote: {SUMMARY}\nwrote: {SUMMARY_MD}")
    print(f"direct-answer strict-evidence fail (rc2): {direct_answer_strict_fail_rc2}")
    print(f"direct-answer aux-fallback fired (rc2): {direct_answer_aux_fallback}")
    print(f"restraint Cat A (rc2): {restraint_cat_A_rc2}/{restraint_n}")
    print(f"freshness Cat A (rc2): {fresh_cat_A_rc2}/{fresh_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
