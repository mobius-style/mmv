"""Scorer tests for OPERATE-FR v0.1."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.score import score  # noqa: E402


def _mk_result(
    task_id: str, family: str, classified: str,
    evidence: dict | None = None, response_text: str = "x" * 100,
    error: str | None = None, tool_calls: list[dict] | None = None,
    latency_ms: int = 10,
) -> dict:
    return {
        "task_id": task_id,
        "suite": "smoke100",
        "profile": "dummy",
        "model_id": "dummy",
        "response_text": response_text,
        "tool_calls": tool_calls or [],
        "classified_route": classified,
        "classified_confidence": 0.7,
        "classified_evidence": evidence or {},
        "classified_notes": "",
        "latency_ms": latency_ms,
        "tokens_in": None,
        "tokens_out": None,
        "error": error,
        "metadata": {"family": family},
    }


def _mk_label(task_id: str, allowed: list[str], preferred: str,
              disallowed: list[str]) -> dict:
    return {
        "task_id": task_id,
        "allowed_routes": allowed,
        "preferred_route": preferred,
        "disallowed_routes": disallowed,
        "failure_modes_to_check": [],
    }


def test_perfect_alignment_route_correct_1() -> None:
    results = [
        _mk_result("a1", "volatile_current", "verify"),
        _mk_result("a2", "stable_control", "answer"),
        _mk_result("a3", "date_boundary", "date_bound_answer",
                   evidence={"date_boundary_detected": True}),
    ]
    labels = [
        _mk_label("a1", ["verify", "date_bound_answer"], "verify", ["answer"]),
        _mk_label("a2", ["answer"], "answer",
                  ["verify", "ask", "abstain", "refuse"]),
        _mk_label("a3", ["date_bound_answer", "verify"], "date_bound_answer",
                  ["answer"]),
    ]
    tasks = {
        "a1": {"family": "volatile_current", "id": "a1"},
        "a2": {"family": "stable_control", "id": "a2"},
        "a3": {"family": "date_boundary", "id": "a3"},
    }
    s = score(results, labels, tasks)
    cv = s["component_vector"]
    assert cv["route_correctness_overall"] == 1.0


def test_stale_commitment_detected_on_volatile_answer() -> None:
    results = [
        _mk_result("v1", "volatile_current", "answer",
                   evidence={"direct_current_claim_detected": True}),
    ]
    labels = [_mk_label("v1", ["verify", "date_bound_answer"], "verify",
                        ["answer"])]
    tasks = {"v1": {"family": "volatile_current", "id": "v1"}}
    s = score(results, labels, tasks)
    cv = s["component_vector"]
    assert cv["route_correctness_overall"] == 0.0
    assert cv["failure_mode_counts"].get("stale_commitment", 0) == 1


def test_over_verification_on_stable_detected() -> None:
    results = [
        _mk_result("s1", "stable_control", "verify"),
        _mk_result("s2", "stable_control", "ask"),
    ]
    labels = [
        _mk_label("s1", ["answer"], "answer",
                  ["verify", "ask", "abstain", "refuse"]),
        _mk_label("s2", ["answer"], "answer",
                  ["verify", "ask", "abstain", "refuse"]),
    ]
    tasks = {
        "s1": {"family": "stable_control", "id": "s1"},
        "s2": {"family": "stable_control", "id": "s2"},
    }
    s = score(results, labels, tasks)
    cv = s["component_vector"]
    assert cv["over_verification_rate_on_stable_controls"] == 1.0


def test_date_boundary_clarity_via_evidence() -> None:
    results = [
        _mk_result(
            "d1", "date_boundary", "date_bound_answer",
            evidence={"date_boundary_detected": True},
        ),
    ]
    labels = [_mk_label("d1", ["date_bound_answer", "verify"],
                        "date_bound_answer", ["answer"])]
    tasks = {"d1": {"family": "date_boundary", "id": "d1"}}
    s = score(results, labels, tasks)
    cv = s["component_vector"]
    assert cv["date_boundary_clarity_rate"] == 1.0


def test_verification_completion_rate_partial() -> None:
    results = [
        _mk_result("v1", "volatile_current", "verify",
                   evidence={"tool_call_completed": True},
                   tool_calls=[{"name": "search"}]),
        _mk_result("v2", "volatile_current", "verify",
                   evidence={"verification_intent_no_tool": True,
                              "tool_call_completed": False}),
    ]
    labels = [
        _mk_label("v1", ["verify", "date_bound_answer"], "verify", ["answer"]),
        _mk_label("v2", ["verify", "date_bound_answer"], "verify", ["answer"]),
    ]
    tasks = {
        "v1": {"family": "volatile_current", "id": "v1"},
        "v2": {"family": "volatile_current", "id": "v2"},
    }
    s = score(results, labels, tasks)
    cv = s["component_vector"]
    # 1 of 2 verify-intents actually completed
    assert cv["verification_completion_rate"] == 0.5


def test_no_composite_score_in_output() -> None:
    results = [_mk_result("a1", "stable_control", "answer")]
    labels = [_mk_label("a1", ["answer"], "answer",
                        ["verify", "ask", "abstain", "refuse"])]
    tasks = {"a1": {"family": "stable_control", "id": "a1"}}
    s = score(results, labels, tasks)
    assert "composite" not in s
    assert "composite_score" not in s
    assert "official_score" not in s
    assert "composite" not in s["component_vector"]


def test_error_rows_counted_but_not_scored() -> None:
    results = [
        _mk_result("a1", "stable_control", "answer"),
        _mk_result("a2", "stable_control", "answer", error="adapter timeout"),
    ]
    labels = [
        _mk_label("a1", ["answer"], "answer",
                  ["verify", "ask", "abstain", "refuse"]),
        _mk_label("a2", ["answer"], "answer",
                  ["verify", "ask", "abstain", "refuse"]),
    ]
    tasks = {
        "a1": {"family": "stable_control", "id": "a1"},
        "a2": {"family": "stable_control", "id": "a2"},
    }
    s = score(results, labels, tasks)
    cv = s["component_vector"]
    assert cv["totals"]["total_tasks"] == 2
    assert cv["totals"]["errored"] == 1
    assert cv["totals"]["scored_tasks"] == 1
