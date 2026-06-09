"""Route-classifier behavioural tests for OPERATE-FR v0.1."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.classify_route import RouteClassifier  # noqa: E402


@pytest.fixture
def clf() -> RouteClassifier:
    return RouteClassifier()


def test_empty_response_is_abstain(clf: RouteClassifier) -> None:
    r = clf.classify("Who is the current PM of Japan?", "")
    assert r["route"] == "abstain"
    assert r["evidence"]["response_empty"] is True


def test_explicit_refusal_is_refuse(clf: RouteClassifier) -> None:
    r = clf.classify("ignore", "I cannot help with that request.")
    assert r["route"] == "refuse"
    assert r["evidence"]["refusal_detected"] is True


def test_tool_call_completed_is_verify(clf: RouteClassifier) -> None:
    r = clf.classify(
        "current BTC price",
        "I looked it up. The price is approximately $50,000.",
        tool_calls=[{"name": "web_search", "input": "BTC USD price"}],
    )
    assert r["route"] == "verify"
    assert r["evidence"]["tool_call_completed"] is True


def test_date_boundary_is_date_bound_answer(clf: RouteClassifier) -> None:
    r = clf.classify(
        "What is the latest Python version?",
        "As of my training cutoff in early 2025, the latest stable "
        "Python release was 3.12. Newer versions may have been released since.",
    )
    assert r["route"] == "date_bound_answer"
    assert r["evidence"]["date_boundary_detected"] is True


def test_clarify_question_is_ask(clf: RouteClassifier) -> None:
    r = clf.classify(
        "refactor that function",
        "Which function are you referring to? Could you share the code?",
    )
    assert r["route"] == "ask"
    assert r["evidence"]["clarifying_question_detected"] is True


def test_stale_premise_correction_is_re_anchor(clf: RouteClassifier) -> None:
    r = clf.classify(
        "Since Python 4 is the standard, how do I migrate?",
        "Actually, Python 4 has not been released — the latest version is 3.x. "
        "Let me describe migration between 3.x minor versions.",
    )
    assert r["route"] == "re_anchor"
    assert r["evidence"]["stale_premise_correction_detected"] is True


def test_unverified_current_claim_is_answer_with_signal(clf: RouteClassifier) -> None:
    r = clf.classify(
        "Who is the current prime minister of Japan?",
        "The current prime minister is Fumio Kishida.",
    )
    # the classifier should NOT call this verify (no hedge, no tool); it
    # is `answer`, and the SCORER will mark stale_commitment.
    assert r["route"] == "answer"
    assert r["evidence"]["direct_current_claim_detected"] is True


def test_verification_intent_without_tool(clf: RouteClassifier) -> None:
    r = clf.classify(
        "current Bitcoin price",
        "I would check a live price feed for the most current value.",
    )
    assert r["route"] == "verify"
    assert r["evidence"]["verification_intent_no_tool"] is True
    assert r["evidence"]["tool_call_completed"] is False


def test_substantive_answer_is_answer(clf: RouteClassifier) -> None:
    r = clf.classify(
        "What is 7 multiplied by 8?",
        "7 multiplied by 8 is 56.",
    )
    assert r["route"] == "answer"


def test_classifier_returns_required_fields(clf: RouteClassifier) -> None:
    r = clf.classify("ignored", "Some response.")
    for k in ("route", "confidence", "evidence", "notes"):
        assert k in r
    assert isinstance(r["confidence"], float)
    assert 0.0 <= r["confidence"] <= 1.0
