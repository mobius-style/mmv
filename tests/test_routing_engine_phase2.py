"""Phase 2 routing engine tests — no adapter, no RAG required."""
from src.kernel.routing_engine import RoutingEngine
from src.state.session_state import SessionState


def test_multi_turn_state_accumulates():
    engine = RoutingEngine()
    state  = SessionState()

    engine.evaluate("What about this?", state)
    engine.evaluate("Explain checks and balances in government.", state)

    assert state.current_turn == 2
    assert state.route_history[0]["route"] == "ask"
    assert state.route_history[1]["route"] == "answer"


def test_active_language_switches():
    engine = RoutingEngine()
    state  = SessionState()

    engine.evaluate("Explain the basics of democracy.", state)
    assert state.active_language == "en"

    engine.evaluate("民主主義の基本を説明してください。", state)
    assert state.active_language == "ja"


def test_trace_is_attached():
    engine = RoutingEngine()
    state  = SessionState()
    result = engine.evaluate("What is the current GDP of Japan?", state)

    assert "Route"   in result.trace
    assert "Reason"  in result.trace
    assert result.trace["Route"] in ("answer", "ask", "verify", "abstain")


def test_session_export_after_turns():
    import json
    engine = RoutingEngine()
    state  = SessionState()

    engine.evaluate("Explain checks and balances.", state)
    engine.evaluate("What is today's inflation rate in Japan?", state)

    exported = state.export_json()
    data     = json.loads(exported)

    assert len(data["route_history"]) == 2
    assert data["active_language"] == "en"
