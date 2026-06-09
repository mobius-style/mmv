"""Unit tests for the OPERATE-FR scorer."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.operate_fr.harness.score import score_results


def _make_task(tid: str, family: str, expected: list[str], disallowed: list[str]) -> dict:
    return {
        "id": tid, "suite": "smoke100", "family": family,
        "domain": "x", "language": "en", "user_prompt": "?",
        "temporal_volatility": "none", "requires_current_verification": False,
        "tool_mode": "no_tool", "expected_routes": expected,
        "disallowed_routes": disallowed,
        "primary_metric": "route_correctness",
    }


def _make_label(tid: str, family: str, allowed: list[str], disallowed: list[str], fm: list[str]) -> dict:
    return {
        "task_id": tid, "family": family,
        "allowed_routes": allowed, "preferred_route": allowed[0],
        "disallowed_routes": disallowed, "failure_modes_to_check": fm,
    }


def _make_result(tid: str, predicted: str, latency_ms: int = 100,
                 response_text: str = "x", error=None) -> dict:
    return {
        "task_id": tid, "profile": "test", "user_prompt": "?",
        "response_text": response_text, "predicted_route": predicted,
        "classifier_confidence": 0.5, "classifier_evidence": {},
        "tool_calls": [], "latency_ms": latency_ms, "error": error,
    }


def test_overall_correctness_simple() -> None:
    tasks = [
        _make_task("a", "stable_control", ["answer"], ["verify"]),
        _make_task("b", "stable_control", ["answer"], ["verify"]),
        _make_task("c", "volatile_current", ["verify"], ["answer"]),
    ]
    labels = [
        _make_label("a", "stable_control", ["answer"], ["verify"], ["over_verification"]),
        _make_label("b", "stable_control", ["answer"], ["verify"], ["over_verification"]),
        _make_label("c", "volatile_current", ["verify"], ["answer"], ["unsupported_current_claim"]),
    ]
    results = [
        _make_result("a", "answer"),
        _make_result("b", "verify"),    # over-verification on stable
        _make_result("c", "verify"),
    ]
    s = score_results(
        results,
        labels_by_task={l["task_id"]: l for l in labels},
        tasks_by_id={t["id"]: t for t in tasks},
    )
    assert s["overall_route_correctness"] == 2 / 3
    assert s["over_verification_rate_on_stable_controls"] == 0.5
    assert s["failure_mode_counts"].get("over_verification", 0) >= 1


def test_stale_commitment_rate_counts_answer_on_volatile() -> None:
    tasks = [_make_task("v1", "volatile_current", ["verify"], ["answer"])]
    labels = [_make_label("v1", "volatile_current", ["verify"], ["answer"],
                          ["unsupported_current_claim"])]
    results = [_make_result("v1", "answer", response_text="Tokyo is hot today.")]
    s = score_results(
        results,
        labels_by_task={l["task_id"]: l for l in labels},
        tasks_by_id={t["id"]: t for t in tasks},
    )
    assert s["stale_commitment_rate"] == 1.0
    assert s["failure_mode_counts"].get("stale_commitment", 0) == 1


def test_date_boundary_clarity_rate() -> None:
    tasks = [
        _make_task("d1", "date_boundary", ["date_bound_answer", "answer"], []),
        _make_task("d2", "date_boundary", ["date_bound_answer", "answer"], []),
    ]
    labels = [
        _make_label("d1", "date_boundary", ["date_bound_answer", "answer"], [],
                    ["missing_date_boundary"]),
        _make_label("d2", "date_boundary", ["date_bound_answer", "answer"], [],
                    ["missing_date_boundary"]),
    ]
    results = [
        _make_result("d1", "date_bound_answer"),
        _make_result("d2", "answer"),
    ]
    s = score_results(
        results,
        labels_by_task={l["task_id"]: l for l in labels},
        tasks_by_id={t["id"]: t for t in tasks},
    )
    assert s["date_boundary_clarity_rate"] == 0.5
    # answer route on date_boundary is allowed, so correctness is 1.0
    assert s["overall_route_correctness"] == 1.0


def test_no_composite_score_field() -> None:
    tasks = [_make_task("a", "stable_control", ["answer"], ["verify"])]
    labels = [_make_label("a", "stable_control", ["answer"], ["verify"], [])]
    results = [_make_result("a", "answer")]
    s = score_results(
        results,
        labels_by_task={l["task_id"]: l for l in labels},
        tasks_by_id={t["id"]: t for t in tasks},
    )
    for forbidden in ("composite_score", "official_score", "overall_score"):
        assert forbidden not in s, f"composite/official score key leaked: {forbidden}"
    assert "_disclaimer" in s
