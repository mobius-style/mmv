from src.kernel.routing_engine import RoutingEngine
from src.state.session_state import SessionState


def test_ask_route_for_under_specified_query():
    engine = RoutingEngine()
    result = engine.evaluate("What about this?", SessionState())
    assert result.decision.route == "ask"


def test_ask_route_for_ambiguous_freshness_query():
    engine = RoutingEngine()
    result = engine.evaluate("What is the latest regulation on this policy?", SessionState())
    assert result.decision.route == "ask"


def test_verify_route_for_specified_freshness_query():
    engine = RoutingEngine()
    result = engine.evaluate("Please summarize the regulations currently governing municipal solar permitting in California as of November 2026", SessionState())
    assert result.decision.route == "verify"


def test_answer_route_for_clear_low_stakes_question():
    engine = RoutingEngine()
    result = engine.evaluate("Explain the basic idea of checks and balances in government.", SessionState())
    assert result.decision.route == "answer"
    assert result.decision.answer_shape in {"low_movement_answer", "admissible_reframing_answer"}
