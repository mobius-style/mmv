"""Box W skip on casual_greeting — integration contract tests.

Per Evolution Log cyc_20260423_production_failure_deep_fix_2 (Layer 6):
Box W (Wikipedia) was retrieved unconditionally on every non-self-ref,
non-CONV_OVERRIDE query with top_score >= 0.75 semantic similarity —
so first-turn greetings like 「こんにちは」 leaked Wikipedia content
into responses (Yorushika song for 天気 queries, こんにちは entry for
greetings, 将棋 piece entry for しりとり…うま, etc.).

The fix adds `intent_type == "casual_greeting"` as a third skip gate
alongside CONV_OVERRIDE and supervisor cap=insufficient. These tests
lock in the gate at two layers:

  1. Intent-level: _infer_intent_type returns "casual_greeting" for
     greetings.
  2. Behavior-level: _prepare_answer_stream short-circuits with a
     brief-greeting prompt and emits CASUAL_GREETING_FAST_PATH reason
     code, without consulting Box W / Box 0.
  3. Regression: factual and self-ref queries still reach their
     respective paths (Box 0 consulted for self-ref, Box W gate
     reachable for factual).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.kernel.appraisal import Appraiser
from src.kernel.route_decision import RouteDecision, select_route
from src.kernel.routing_engine import RoutingEngine
from src.state.session_state import SessionState


def _mk_engine(box_0_adapter=None, wiki_adapter=None, adapter=None):
    """Minimal RoutingEngine wiring for prepare_answer_stream tests."""
    return RoutingEngine(
        adapter                = adapter,
        web_search_adapter     = None,
        kiwix_adapter          = None,
        box_0_adapter          = box_0_adapter,
        wiki_adapter           = wiki_adapter,
    )


def _mk_inputs(query: str):
    ap = Appraiser().evaluate(query)
    dec = select_route(ap)
    state = SessionState()
    state.active_language = "ja" if any("぀" <= c <= "ヿ" for c in query) else "en"
    return ap, dec, state


# ── Group 1: Intent classification ────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "こんにちは",
    "ありがとうございます",
    "今日は良い天気ですね",
    "hello",
    "thanks",
    "你好",
    "谢谢",
])
def test_intent_classifies_greeting_as_casual(q: str) -> None:
    ap = Appraiser().evaluate(q)
    assert RoutingEngine._infer_intent_type(q, ap) == "casual_greeting"


@pytest.mark.parametrize("q", [
    "クリリンの妻は誰？",
    "Python の lambda とは",
    "What is quantum computing?",
])
def test_intent_factual_preserved(q: str) -> None:
    ap = Appraiser().evaluate(q)
    # ism may override to a different label (game_move / clarification /
    # etc. per pre-existing ISM heuristics); what MUST NOT happen is
    # classification as casual_greeting for a substantive query.
    assert RoutingEngine._infer_intent_type(q, ap) != "casual_greeting"


@pytest.mark.parametrize("q", [
    "貴方の特徴を教えてください",
    "貴殿の特徴を教えてください",
    "あなたは誰ですか",
])
def test_intent_self_ref_not_reclassified_as_greeting(q: str) -> None:
    # Fix 1 self_referential flag must retain priority. Even if a
    # kanji-self-ref query happened to share a surface pattern with a
    # greeting, the self_referential branch runs before casual_greeting
    # in _infer_intent_type and routes to meta_question (or whatever
    # ism supplies).
    ap = Appraiser().evaluate(q)
    assert ap.self_referential is True
    assert RoutingEngine._infer_intent_type(q, ap) != "casual_greeting"


# ── Group 2: Fast-path behavior (streaming path) ──────────────────────────

def test_casual_greeting_returns_brief_prompt_without_box_w() -> None:
    # Wire a mock wiki_adapter and box_0_adapter; neither should be
    # called on a pure greeting.
    wiki = MagicMock()
    wiki.is_available.return_value = True
    wiki.retrieve = MagicMock()
    box0 = MagicMock()
    box0.retrieve = MagicMock()
    adapter = MagicMock()

    engine = _mk_engine(box_0_adapter=box0, wiki_adapter=wiki, adapter=adapter)
    ap, dec, state = _mk_inputs("こんにちは")

    prompt, fallback, sources = engine._prepare_answer_stream(
        "こんにちは", dec, ap, state,
    )

    assert prompt is not None, "casual_greeting must yield a prompt"
    # The brief-acknowledgement prompt MAY mention "Wikipedia" in its
    # instruction ("do not bring in Wikipedia …"), but must not contain
    # an "Evidence from Wikipedia" block or any retrieved chunks.
    assert "Evidence from Wikipedia" not in prompt, (
        "casual_greeting prompt must not contain retrieved Wiki evidence"
    )
    assert "Reference (canonical MOBIUS documentation)" not in prompt, (
        "casual_greeting prompt must not pull Box 0 reference"
    )
    assert wiki.retrieve.call_count == 0, (
        "wiki_adapter.retrieve must NOT be called on casual_greeting"
    )
    assert box0.retrieve.call_count == 0, (
        "box_0_adapter.retrieve must NOT be called on casual_greeting"
    )
    # Reason code must mark the fast path for trace observability.
    assert "CASUAL_GREETING_FAST_PATH" in dec.reason_codes


def test_factual_query_still_reaches_wiki_gate() -> None:
    # Regression: a factual query must NOT get the casual greeting
    # short-circuit; the Box W gate must be reachable.
    wiki = MagicMock()
    wiki.is_available.return_value = True
    # Return an empty result so the path proceeds but we can assert
    # the call happened.
    from src.adapters.wiki_adapter import RetrievalResult as _WR
    wiki.retrieve.return_value = _WR(sources=[], outcome="failed", synthesis="")
    adapter = MagicMock()

    engine = _mk_engine(wiki_adapter=wiki, adapter=adapter)
    ap, dec, state = _mk_inputs("Python の lambda とは")

    # We don't care about the prompt content here, only that wiki was
    # consulted and the reason code is NOT the fast path.
    engine._prepare_answer_stream("Python の lambda とは", dec, ap, state)

    assert "CASUAL_GREETING_FAST_PATH" not in dec.reason_codes
    assert wiki.retrieve.call_count >= 1, (
        "factual query must still reach the Box W gate"
    )


def test_mixed_greeting_plus_question_does_not_short_circuit() -> None:
    # A query longer than 20 chars or containing ? must not fast-path;
    # this protects against swallowing substantive queries that start
    # with a greeting.
    wiki = MagicMock()
    wiki.is_available.return_value = True
    from src.adapters.wiki_adapter import RetrievalResult as _WR
    wiki.retrieve.return_value = _WR(sources=[], outcome="failed", synthesis="")
    adapter = MagicMock()

    engine = _mk_engine(wiki_adapter=wiki, adapter=adapter)
    q = "こんにちは、Answer Entitlement とは何ですか"
    ap, dec, state = _mk_inputs(q)

    engine._prepare_answer_stream(q, dec, ap, state)

    assert "CASUAL_GREETING_FAST_PATH" not in dec.reason_codes
