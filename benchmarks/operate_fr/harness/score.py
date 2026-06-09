"""Scoring for OPERATE-FR v0.1.

Computes the **component vector** (per spec §8). Deliberately does NOT compute
an official composite score; an optional non-official scorecard helper is
provided for downstream reporting but must be labeled as non-official by the
caller.

Metrics produced:
  - overall_route_correctness
  - route_correctness_by_family (dict)
  - stale_commitment_rate                      (in volatile_current + stale_premise_trap, model claimed
                                                a current/stale fact without verification or anchor)
  - over_verification_rate_on_stable_controls  (in stable_control, model routed to verify/ask)
  - date_boundary_clarity_rate                 (fraction of allowed=date_bound_answer rows that hit it)
  - verification_completion_rate               (when tool_calls present: fraction that ran tools)
  - query_contamination_rate                   (placeholder; tool queries not logged in v0.1)
  - average_response_length
  - average_latency_ms
  - failure_mode_counts
"""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any


def _is_correct(predicted: str | None, allowed: list[str]) -> bool:
    return predicted in (allowed or [])


def _is_disallowed(predicted: str | None, disallowed: list[str]) -> bool:
    return predicted in (disallowed or [])


def score_results(
    results: list[dict],
    labels_by_task: dict[str, dict],
    tasks_by_id: dict[str, dict],
) -> dict[str, Any]:
    """Return the component-vector summary for a single profile run."""

    by_family_correct: dict[str, list[int]] = defaultdict(list)
    fm_counts: Counter = Counter()

    stale_commit_num = 0
    stale_commit_den = 0

    overver_num = 0
    overver_den = 0

    db_num = 0
    db_den = 0

    verify_complete_num = 0
    verify_complete_den = 0

    response_lengths: list[int] = []
    latencies: list[int] = []

    overall_correct = 0
    overall_total = 0
    errors = 0

    for r in results:
        tid = r.get("task_id")
        task = tasks_by_id.get(tid)
        label = labels_by_task.get(tid)
        if not task or not label:
            continue

        if r.get("error"):
            errors += 1
            continue

        family = task.get("family", "?")
        predicted = r.get("predicted_route")
        allowed = label.get("allowed_routes", [])
        disallowed = label.get("disallowed_routes", [])

        correct = _is_correct(predicted, allowed)
        by_family_correct[family].append(1 if correct else 0)
        overall_total += 1
        overall_correct += int(correct)

        response_lengths.append(len(r.get("response_text") or ""))
        latencies.append(int(r.get("latency_ms") or 0))

        # Stale-commitment rate (for volatile + stale_premise_trap):
        # model issued an `answer` route (asserted current claim) when allowed
        # was verify/date_bound/re_anchor.
        if family in ("volatile_current", "stale_premise_trap"):
            stale_commit_den += 1
            if predicted == "answer" and _is_disallowed(predicted, disallowed):
                stale_commit_num += 1
                fm_counts["stale_commitment"] += 1

        # Over-verification on stable controls: model routed to verify/ask on
        # a stable fact.
        if family == "stable_control":
            overver_den += 1
            if predicted in ("verify", "ask"):
                overver_num += 1
                fm_counts["over_verification"] += 1

        # Date-boundary clarity: of rows where allowed includes
        # date_bound_answer, what fraction took it?
        if "date_bound_answer" in (allowed or []):
            db_den += 1
            if predicted == "date_bound_answer":
                db_num += 1
            elif family == "date_boundary":
                fm_counts["missing_date_boundary"] += 1

        # Verification completion (only meaningful when tool_calls present)
        tool_calls = r.get("tool_calls") or []
        if tool_calls:
            verify_complete_den += 1
            if predicted == "verify":
                verify_complete_num += 1

        # Failure-mode counts from disallowed routes
        if _is_disallowed(predicted, disallowed):
            for fm in (label.get("failure_modes_to_check") or []):
                fm_counts[fm] += 1

    def _safe_div(n: int, d: int) -> float | None:
        return (n / d) if d > 0 else None

    return {
        "n_total_results": len(results),
        "n_scored": overall_total,
        "n_errors": errors,
        "overall_route_correctness": _safe_div(overall_correct, overall_total),
        "route_correctness_by_family": {
            fam: (sum(vals) / len(vals)) for fam, vals in by_family_correct.items()
        },
        "n_by_family": {fam: len(vals) for fam, vals in by_family_correct.items()},
        "stale_commitment_rate": _safe_div(stale_commit_num, stale_commit_den),
        "over_verification_rate_on_stable_controls":
            _safe_div(overver_num, overver_den),
        "date_boundary_clarity_rate": _safe_div(db_num, db_den),
        "verification_completion_rate": _safe_div(verify_complete_num,
                                                  verify_complete_den),
        "query_contamination_rate": None,  # v0.1: tool queries not logged
        "average_response_length_chars": mean(response_lengths) if response_lengths else None,
        "average_latency_ms": mean(latencies) if latencies else None,
        "failure_mode_counts": dict(fm_counts),
        "_disclaimer": (
            "OPERATE-FR v0.1 reports a component vector. No official composite "
            "score is provided. See docs/PAPER.md."
        ),
    }
