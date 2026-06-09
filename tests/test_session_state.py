import json
from src.state.session_state import SessionState, Correction


def test_record_route_increments_turn():
    state = SessionState()
    state.record_route({"route": "ask", "reason_codes": ["MISSING_CONSTRAINTS"]})
    state.record_route({"route": "answer", "reason_codes": ["LOW_STAKES_STABLE"]})
    assert state.current_turn == 2
    assert state.route_history[0]["turn"] == 1
    assert state.route_history[1]["turn"] == 2


def test_apply_correction_to_facts():
    state = SessionState()
    state.apply_correction("facts", "User is researching Japanese law")
    assert "User is researching Japanese law" in state.facts
    assert len(state.corrections) == 1
    assert state.corrections[0].field == "facts"


def test_apply_correction_to_summary():
    state = SessionState()
    state.apply_correction("summary", "Session about electoral law")
    assert state.summary == "Session about electoral law"
    assert state.corrections[0].old_value == ""


def test_export_import_roundtrip():
    state = SessionState()
    state.active_language = "ja"
    state.facts.append("テスト")
    state.record_route({"route": "ask", "reason_codes": ["AMBIGUOUS_INTENT"]})
    state.apply_correction("summary", "テストセッション")

    exported = state.export_json()
    restored = SessionState.import_json(exported)

    assert restored.session_id      == state.session_id
    assert restored.active_language == "ja"
    assert "テスト" in restored.facts
    assert restored.summary         == "テストセッション"
    assert len(restored.route_history) == 1
    assert len(restored.corrections)   == 1


def test_export_is_valid_json():
    state = SessionState()
    exported = state.export_json()
    data = json.loads(exported)
    assert "session_id" in data
    assert "route_history" in data
