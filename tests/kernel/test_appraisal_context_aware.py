"""C-2 fix: context-aware self-ref tests.

Phase 2 Commit 12 — appraisal.py extended to inspect
metadata["recent_user_queries"] (list, last 3) when the current query
lacks a SELF_REF anchor. The bare-aspect pattern + a prior self-ref
turn jointly classify the current query as self-referential.

Asserts:
1. Self-ref turn 1 + bare aspect-question turn 2 → self_referential=True
2. Non-self-ref turn 1 + bare aspect-question turn 2 → self_referential=False
3. 4-turn-old self-ref is outside the 3-turn window → False
4. Regression: Fix 1 kanji self-ref query alone (no metadata) still True
"""
from __future__ import annotations

from src.kernel.appraisal import Appraiser


def test_c2_self_ref_then_bare_aspect_question_is_self_ref() -> None:
    """Turn 0 self-ref, turn 1 bare 'どんなアーキテクチャですか'."""
    a = Appraiser()
    state = a.evaluate(
        "どんなアーキテクチャですか",
        metadata={"recent_user_queries": ["あなたの名前は？"]},
    )
    assert state.self_referential is True


def test_c2_non_self_ref_prior_does_not_promote_aspect_question() -> None:
    """Turn 0 NOT self-ref ('Python の lambda とは?'), turn 1 bare
    aspect-question. Should NOT be marked self-ref — there is no
    prior self-ref turn to inherit from."""
    a = Appraiser()
    state = a.evaluate(
        "どんなアーキテクチャですか",
        metadata={"recent_user_queries": ["Python の lambda とは?"]},
    )
    assert state.self_referential is False


def test_c2_old_self_ref_outside_window_does_not_fire() -> None:
    """Self-ref turn 4-back with 3 unrelated turns between is outside
    the window; routing_engine only forwards the most recent 3 user
    queries, so the appraiser never sees turn-back-4. With only 3
    non-self-ref recent queries, C-2 must NOT fire."""
    a = Appraiser()
    state = a.evaluate(
        "どんなアーキテクチャですか",
        metadata={
            "recent_user_queries": [
                "Python の lambda とは?",
                "BTC の現在価格は?",
                "明日の天気を教えて",
            ],
        },
    )
    assert state.self_referential is False


def test_c2_regression_fix_1_kanji_self_ref_alone_still_works() -> None:
    """Fix 1 (kanji self-ref via SELF_REF_PATTERNS) MUST remain
    intact. A standalone '貴方の特徴を教えてください' with no
    metadata should still be self-ref via the existing path —
    nothing in C-2 added overrides it."""
    a = Appraiser()
    state = a.evaluate("貴方の特徴を教えてください")
    assert state.self_referential is True


def test_c2_does_not_promote_topic_shift() -> None:
    """Turn 0 self-ref, turn 1 a clear topic shift ("クリリンの妻は誰?")
    must NOT be flagged as self-ref. The bare-aspect pattern is
    intentionally narrow so proper-noun / entity queries fall through."""
    a = Appraiser()
    state = a.evaluate(
        "クリリンの妻は誰?",
        metadata={"recent_user_queries": ["あなたの名前は？"]},
    )
    assert state.self_referential is False


def test_c2_legacy_prev_user_metadata_key_also_works() -> None:
    """The metadata key `prev_user` (legacy single-turn variant) is
    accepted in lieu of `recent_user_queries`."""
    a = Appraiser()
    state = a.evaluate(
        "どんなアーキテクチャですか",
        metadata={"prev_user": "あなたは誰?"},
    )
    assert state.self_referential is True


def test_c2_en_aspect_question_after_self_ref() -> None:
    """English: 'What is your name' → 'What is its architecture'
    second turn should be self-ref under C-2."""
    a = Appraiser()
    state = a.evaluate(
        "What is its architecture?",
        metadata={"recent_user_queries": ["What is your name?"]},
    )
    assert state.self_referential is True


def test_c2_zh_aspect_question_after_self_ref() -> None:
    """Chinese: 你叫什么名字 → 架构是什么 should be self-ref under C-2."""
    a = Appraiser()
    state = a.evaluate(
        "架构是什么",
        metadata={"recent_user_queries": ["你叫什么名字"]},
    )
    assert state.self_referential is True


def test_c2_no_metadata_no_promotion() -> None:
    """If metadata is None, C-2 path is inert. Bare aspect query alone
    (no SELF_REF match) → not self-ref."""
    a = Appraiser()
    state = a.evaluate("どんなアーキテクチャですか")
    assert state.self_referential is False
