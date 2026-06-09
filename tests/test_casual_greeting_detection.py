"""Casual greeting detection — boundary contract tests.

Per Evolution Log cyc_20260423_production_failure_deep_fix_2 (Layer 7):
first-turn chit-chat queries like 「こんにちは」, 「今日は良い天気ですね」,
"hello" etc. were falling through _infer_intent_type's default to
`factual_query` and triggering unconditional Box W retrieval. The fix
adds a high-precision `_is_casual_greeting` detector that:

  - matches self-contained pleasantries / greetings / thanks / farewells
    across JA / EN / ZH
  - requires short query length (≤ 20 chars after strip) so substantive
    queries starting with a greeting route normally
  - excludes any query containing '?' or '？' so genuine questions
    ('お元気ですか？') bypass the fast path

These tests lock in:
  1. Pure-greeting queries in JA / EN / ZH match.
  2. Mixed greeting + substantive queries do NOT match.
  3. Question-mark queries (even greeting-ish ones) do NOT match.
  4. Self-ref queries are unaffected (Fix 1 / kanji self-ref preserved
     via the self_referential flag, which is checked BEFORE the
     casual_greeting branch in _infer_intent_type).
"""
from __future__ import annotations

import pytest

from src.kernel.routing_engine import _is_casual_greeting


# ── Group 1: JA pure greetings (must match) ────────────────────────────────

JA_GREETINGS = [
    "こんにちは",
    "こんばんは",
    "おはよう",
    "おはようございます",
    "ありがとう",
    "ありがとうございます",
    "ありがとうございました",
    "どうも",
    "よろしく",
    "よろしくお願いします",
    "よろしくお願いいたします",
    "はじめまして",
    "初めまして",
    "さようなら",
    "さよなら",
    "またね",
    "また明日",
    "お疲れ様",
    "お疲れ様です",
    "お疲れさまでした",
    "今日は良い天気ですね",
    "今日はいい天気ですね",
    "おやすみ",
    "おやすみなさい",
]


@pytest.mark.parametrize("q", JA_GREETINGS)
def test_ja_pure_greeting_matches(q: str) -> None:
    assert _is_casual_greeting(q), f"JA greeting should match: {q!r}"


# ── Group 2: EN pure greetings (must match) ────────────────────────────────

EN_GREETINGS = [
    "hello",
    "Hello",
    "HELLO",
    "hi",
    "Hi",
    "Hey",
    "Hiya",
    "good morning",
    "Good morning",
    "good afternoon",
    "good evening",
    "good night",
    "thanks",
    "Thanks",
    "thanks a lot",
    "Thanks so much",
    "thank you",
    "Thank you very much",
    "thx",
    "ty",
    "cheers",
    "goodbye",
    "bye",
    "bye-bye",
    "see you",
    "see you later",
    "see you tomorrow",
    "nice to meet you",
    "pleased to meet you",
    "take care",
    "have a nice day",
    "have a good weekend",
]


@pytest.mark.parametrize("q", EN_GREETINGS)
def test_en_pure_greeting_matches(q: str) -> None:
    assert _is_casual_greeting(q), f"EN greeting should match: {q!r}"


# ── Group 3: ZH pure greetings (must match) ────────────────────────────────

ZH_GREETINGS = [
    "你好",
    "您好",
    "大家好",
    "早上好",
    "上午好",
    "下午好",
    "晚上好",
    "晚安",
    "谢谢",
    "谢谢你",
    "谢谢您",
    "多谢",
    "感谢",
    "再见",
    "拜拜",
    "回头见",
    "明天见",
    "请多关照",
    "请多指教",
    "辛苦了",
]


@pytest.mark.parametrize("q", ZH_GREETINGS)
def test_zh_pure_greeting_matches(q: str) -> None:
    assert _is_casual_greeting(q), f"ZH greeting should match: {q!r}"


# ── Group 4: Mixed / substantive queries (must NOT match) ──────────────────

MIXED_SUBSTANTIVE = [
    "こんにちは、Answer Entitlement とは何ですか",
    "ありがとう、でももう少し詳しく教えて",
    "hello, what is MOBIUS?",
    "Thanks, can you explain further?",
    "你好，你是谁？",
    "谢谢，请问 MOBIUS 是什么？",
    # Greeting-shaped but with substantive content after:
    "こんにちは、Python の lambda とは",
    "Hi there, please explain Answer Entitlement",
]


@pytest.mark.parametrize("q", MIXED_SUBSTANTIVE)
def test_mixed_substantive_does_not_match(q: str) -> None:
    assert not _is_casual_greeting(q), (
        f"Mixed greeting + substantive query must not fast-path: {q!r}"
    )


# ── Group 5: Question-mark queries must NOT match (high precision) ─────────

QUESTION_MARK_QUERIES = [
    "お元気ですか？",
    "お元気ですか",  # bare, but still looks like a question without ?
    "How are you?",
    "how are you",
    "你好吗？",
]


def test_question_mark_does_not_match_even_if_greeting_shaped() -> None:
    # ? / ？ short-circuits the detector regardless of greeting shape —
    # we want the high-precision gate, not high-recall.
    assert not _is_casual_greeting("お元気ですか？")
    assert not _is_casual_greeting("How are you?")
    assert not _is_casual_greeting("你好吗？")


# ── Group 6: Self-ref / factual / creative (must NOT match) ────────────────

NON_GREETING_QUERIES = [
    # Self-ref (Fix 1 kanji forms — must remain unaffected)
    "貴方の特徴を教えてください",
    "貴殿の特徴を教えてください",
    "あなたは誰ですか",
    "MOBIUS MMV とは",
    # Factual
    "クリリンの妻は誰？",
    "東京の人口は",
    "Python の lambda とは",
    "What is quantum computing?",
    # Creative
    "もし雨が降ったら物語を書いて",
    "write a poem about the sea",
]


@pytest.mark.parametrize("q", NON_GREETING_QUERIES)
def test_non_greeting_does_not_match(q: str) -> None:
    assert not _is_casual_greeting(q), (
        f"Non-greeting query must not be classified as casual: {q!r}"
    )


# ── Group 7: Empty / whitespace edge cases ─────────────────────────────────

def test_empty_string_does_not_match() -> None:
    assert not _is_casual_greeting("")
    assert not _is_casual_greeting("   ")
    assert not _is_casual_greeting("\t\n")


# ── Group 8: Length boundary (20-char cap) ─────────────────────────────────

def test_long_greeting_does_not_match() -> None:
    # A query longer than 20 chars after strip is excluded even if its
    # opening words are greeting-ish. This is the "mixed query" guard.
    long_q = "こんにちは、Answer Entitlement とは何ですか、詳しく教えてください"
    assert len(long_q) > 20
    assert not _is_casual_greeting(long_q)
