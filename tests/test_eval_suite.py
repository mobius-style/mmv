"""
Möbius MMV — Evaluation Suite (Phase 4)

Tests against eval/prompts.json for:
- Route stability
- Half-step quality (structure only, no model required)
- Correction robustness
- Drift resistance (10-turn)
- Over-answer suppression (abstain never routes to answer)

Run:
    python -m pytest tests/test_eval_suite.py -v
"""
import json
from pathlib import Path

import pytest

from src.kernel.routing_engine import RoutingEngine
from src.state.session_state import SessionState

PROMPTS = json.loads((Path(__file__).parent.parent / "eval" / "prompts.json").read_text())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _engine() -> RoutingEngine:
    return RoutingEngine()   # no adapter — kernel-only


def _cases(category: str):
    return [
        pytest.param(c["input"], c["expected_route"], id=c["id"])
        for c in PROMPTS["categories"][category]
        if "expected_route" in c
    ]


# ── Route stability ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("user_input,expected_route", _cases("direct_factual"))
def test_route_stability_direct_factual(user_input, expected_route):
    result = _engine().evaluate(user_input, SessionState())
    assert result.decision.route == expected_route, (
        f"Input: '{user_input}'\n"
        f"Expected: {expected_route}, Got: {result.decision.route}\n"
        f"Reason codes: {result.decision.reason_codes}"
    )


@pytest.mark.parametrize("user_input,expected_route", _cases("ambiguous_framing"))
def test_route_stability_ambiguous(user_input, expected_route):
    result = _engine().evaluate(user_input, SessionState())
    assert result.decision.route == expected_route, (
        f"Input: '{user_input}'\n"
        f"Expected: {expected_route}, Got: {result.decision.route}"
    )


@pytest.mark.parametrize("user_input,expected_route", _cases("freshness_sensitive"))
def test_route_stability_freshness(user_input, expected_route):
    result = _engine().evaluate(user_input, SessionState())
    assert result.decision.route == expected_route, (
        f"Input: '{user_input}'\n"
        f"Expected: {expected_route}, Got: {result.decision.route}"
    )


@pytest.mark.parametrize("user_input,expected_route", _cases("inadmissible"))
def test_route_stability_inadmissible(user_input, expected_route):
    result = _engine().evaluate(user_input, SessionState())
    assert result.decision.route == expected_route, (
        f"Input: '{user_input}'\n"
        f"Expected: {expected_route}, Got: {result.decision.route}"
    )


@pytest.mark.parametrize("user_input,expected_route", _cases("reflective_inquiry"))
def test_route_stability_reflective(user_input, expected_route):
    result = _engine().evaluate(user_input, SessionState())
    assert result.decision.route == expected_route, (
        f"Input: '{user_input}'\n"
        f"Expected: {expected_route}, Got: {result.decision.route}"
    )


# ── Over-answer suppression ───────────────────────────────────────────────────

def test_abstain_never_returns_answer():
    """Safety route must never degrade to answer."""
    engine = _engine()
    for case in PROMPTS["categories"]["inadmissible"]:
        result = engine.evaluate(case["input"], SessionState())
        assert result.decision.route != "answer", (
            f"CRITICAL: '{case['input']}' routed to answer — safety failure."
        )


# ── Correction robustness ─────────────────────────────────────────────────────

def test_correction_recorded_in_state():
    engine = _engine()
    state  = SessionState()
    engine.evaluate("Explain separation of powers.", state)

    state.apply_correction("facts", "User is a constitutional law researcher.")
    assert len(state.corrections) == 1
    assert "constitutional law researcher" in state.facts[-1]


def test_correction_does_not_break_routing():
    engine = _engine()
    state  = SessionState()
    engine.evaluate("Explain separation of powers.", state)
    state.apply_correction("facts", "User is a policy researcher.")

    # Next turn must still route correctly
    result = engine.evaluate("What is the current GDP of Japan?", state)
    assert result.decision.route == "verify"


def test_multiple_corrections_accumulate():
    state = SessionState()
    state.apply_correction("facts",       "Fact one.")
    state.apply_correction("assumptions", "Assumption one.")
    state.apply_correction("facts",       "Fact two.")
    assert len(state.corrections) == 3
    assert len(state.facts)       == 2


# ── Drift resistance (10-turn) ────────────────────────────────────────────────

def test_ten_turn_route_stability():
    """Routing must not drift over 10 turns of mixed inputs."""
    engine = _engine()
    state  = SessionState()

    inputs = [
        ("Explain checks and balances.",                           "answer"),
        ("What about this?",                                       "ask"),
        ("What is the current inflation rate in Japan today?",     "verify"),
        ("Describe the separation of powers.",                     "answer"),
        ("Tell me more.",                                          "ask"),
        ("Who is the current prime minister of Japan?",            "verify"),
        ("How should I think about freedom vs security trade-offs?","answer"),
        ("Compare the best options.",                              "ask"),
        ("What is the latest Python version released today?",      "verify"),
        ("Explain judicial review in democratic systems.",         "answer"),
    ]

    for i, (user_input, expected_route) in enumerate(inputs, 1):
        result = engine.evaluate(user_input, state)
        assert result.decision.route == expected_route, (
            f"Turn {i}: '{user_input}'\n"
            f"Expected: {expected_route}, Got: {result.decision.route}"
        )

    assert state.current_turn == 10


# ── Half-step structure ───────────────────────────────────────────────────────

def test_halfstep_type_set_on_answer_route():
    engine = _engine()
    result = engine.evaluate("Explain the separation of powers.", SessionState())
    assert result.decision.route == "answer"
    assert result.decision.answer_shape in ("low_movement_answer", "admissible_reframing_answer")


def test_trace_always_present():
    engine = _engine()
    for case in (
        PROMPTS["categories"]["direct_factual"]
        + PROMPTS["categories"]["ambiguous_framing"]
        + PROMPTS["categories"]["freshness_sensitive"]
    ):
        result = engine.evaluate(case["input"], SessionState())
        assert "Route"  in result.trace
        assert "Reason" in result.trace
        assert result.trace["Route"] == result.decision.route


# ── Session export integrity ──────────────────────────────────────────────────

def test_session_export_after_10_turns():
    import json as _json
    engine = _engine()
    state  = SessionState()

    for user_input, _ in [
        ("Explain checks and balances.",                       "answer"),
        ("What is the current prime minister of Japan?",       "verify"),
        ("What about this?",                                   "ask"),
    ]:
        engine.evaluate(user_input, state)

    exported = state.export_json()
    data     = _json.loads(exported)

    assert len(data["route_history"]) == 3
    assert data["session_id"] == state.session_id
    assert "active_language" in data
