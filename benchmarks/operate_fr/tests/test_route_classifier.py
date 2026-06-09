"""Unit tests for the rule-based route classifier."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.operate_fr.harness.classify_route import RouteClassifier


def _r(response: str, *, prompt: str = "X?", tool_calls=None) -> dict:
    return RouteClassifier().classify(prompt, response, tool_calls=tool_calls)


def test_direct_answer_short_fact() -> None:
    assert _r("100°C.")["route"] == "answer"


def test_clarifying_question_classified_as_ask() -> None:
    r = _r("Which country are you asking about?")
    assert r["route"] == "ask"


def test_date_bound_answer_with_as_of() -> None:
    r = _r("As of January 2024, the prime minister of Japan is Fumio Kishida.")
    assert r["route"] == "date_bound_answer"


def test_hedge_without_verification_classified_as_verify() -> None:
    r = _r("I do not have access to real-time data, so I can't give you the current price.")
    assert r["route"] == "verify"


def test_tool_call_classified_as_verify() -> None:
    r = _r("Here is the answer.", tool_calls=[{"name": "browser.search", "args": {"q": "x"}}])
    assert r["route"] == "verify"
    assert r["evidence"]["tool_call_detected"] is True


def test_stale_premise_correction_classified_as_re_anchor() -> None:
    r = _r(
        "Actually, Shinzo Abe is no longer prime minister of Japan; "
        "he stepped down from that role in 2020."
    )
    assert r["route"] == "re_anchor"


def test_refusal_classified_as_refuse() -> None:
    r = _r("I cannot help with that.")
    assert r["route"] == "refuse"


def test_would_check_but_did_not_classified_as_verify() -> None:
    r = _r("I should check the latest documentation for that, but here is my best guess: ...")
    # would-check signal triggers verify route
    assert r["route"] in ("verify", "ask")


def test_ja_clarify_is_ask() -> None:
    r = _r("どの会社について教えてほしいですか？")
    assert r["route"] == "ask"


def test_ja_hedge_is_verify() -> None:
    r = _r("申し訳ありませんが、リアルタイムのデータにはアクセスできません。最新の値は公式サイトをご確認ください。")
    assert r["route"] == "verify"
