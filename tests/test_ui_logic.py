"""Test UI helper functions without launching Gradio."""
import sys, types

# Stub gradio so the import doesn't fail in CI
gradio_stub = types.ModuleType("gradio")
for attr in ["Blocks","Row","Column","Chatbot","Textbox","Button","Markdown",
             "HTML","State","Dropdown","File","themes"]:
    setattr(gradio_stub, attr, object)
gradio_stub.themes = types.SimpleNamespace(Soft=lambda **kw: None)
sys.modules.setdefault("gradio", gradio_stub)

from src.app.ui import _badge_html, _why_html, _state_md, ROUTE_COLOURS, ROUTE_LABELS
from src.state.session_state import SessionState


def test_badge_html_all_routes():
    for route in ("answer", "ask", "verify", "abstain"):
        html = _badge_html(route)
        assert ROUTE_LABELS[route] in html
        fg, bg = ROUTE_COLOURS[route]
        assert bg in html
        assert fg in html


def test_why_html_with_sources():
    trace = {
        "Reason":        "FRESHNESS_SENSITIVE",
        "VerifyOutcome": "partial",
        "Sources":       ["doc1.md", "doc2.md"],
    }
    html = _why_html(trace)
    assert "FRESHNESS_SENSITIVE" in html
    assert "partial" in html
    assert "doc1.md" in html


def test_why_html_no_sources():
    trace = {"Reason": "LOW_STAKES_STABLE", "VerifyOutcome": None, "Sources": []}
    html = _why_html(trace)
    assert "LOW_STAKES_STABLE" in html
    assert "Sources" not in html


def test_state_md_empty_session():
    state = SessionState()
    md = _state_md(state)
    assert "Session" in md
    assert "Language" in md
    assert "Turn" in md


def test_state_md_with_facts():
    state = SessionState()
    state.facts.append("User researches Japanese law")
    md = _state_md(state)
    assert "Japanese law" in md


def test_state_md_with_corrections():
    state = SessionState()
    state.apply_correction("facts", "test fact")
    md = _state_md(state)
    assert "Corrections" in md
