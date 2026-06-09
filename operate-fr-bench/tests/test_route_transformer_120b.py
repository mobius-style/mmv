"""Tests for the 120B route transformer and post-validator.

Covers the phrase categories explicitly called out in the task spec:
  - stale premise phrases ("since X is still ...", "as of now X leads ...",
    "X is currently ..., right?")
  - current-sensitive phrases ("current", "latest", "today", "now",
    "this year", "recent", "still")
  - ambiguous-continuation phrases ("is this still true?",
    "what happened next?", "did it change?", "is it still version ...?")
  - date-bound phrases ("in 2020", "as of May 2024",
    "when the 2021 report was released")

The transformer must:
  - leave stable_control prompts untouched (no prefix injected),
  - inject a family-appropriate micro-instruction otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.route_transformer import (  # noqa: E402
    detect_family,
    post_validate,
    prepare,
)


# ─── stale-premise phrase coverage ───────────────────────────────────


@pytest.mark.parametrize(
    "prompt",
    [
        "Since Sam Altman is no longer at OpenAI, who runs the company now?",
        "Now that Twitter has been shut down, what platform are journalists using?",
        "Given that Python 4 is the standard, how do I migrate from 3.x?",
        "Following Angela Merkel's recent re-election as chancellor, what's her agenda?",
        "With the recent US ban on open-weight LLMs, where can researchers still get Llama?",
        "After Elon Musk's acquisition of Anthropic last year, how has Claude changed?",
        "Tim Cook just stepped down as CEO of Apple — who took over?",
        # tag-question shape
        "Sam Altman is currently the CEO of OpenAI, right?",
    ],
)
def test_stale_premise_phrases_detect(prompt: str) -> None:
    assert detect_family(prompt) == "stale_premise_trap", (
        f"prompt should be stale_premise_trap: {prompt!r}"
    )


# ─── current-sensitive ("volatile_current") coverage ─────────────────


@pytest.mark.parametrize(
    "prompt",
    [
        "What is the current prime minister of Japan?",
        "Who is the current CEO of Tesla?",
        "What is the latest stable Python release?",
        "What time is it right now in London?",
        "What is today's USD/JPY exchange rate?",
        "What is the current NVIDIA stock price?",
        "What is the most recent stable version of Node.js?",
    ],
)
def test_volatile_current_phrases_detect(prompt: str) -> None:
    assert detect_family(prompt) == "volatile_current", (
        f"prompt should be volatile_current: {prompt!r}"
    )


# ─── ambiguous-time-frame phrase coverage ────────────────────────────


@pytest.mark.parametrize(
    "prompt",
    [
        "Is this still true?",
        "What happened next?",
        "Did it change?",
        "Is it still version 3.10?",
        "What is the best programming language?",
        "Which AI model is the most popular right now?",
        "What's happening in tech this week?",
    ],
)
def test_ambiguous_time_frame_phrases_detect(prompt: str) -> None:
    assert detect_family(prompt) == "ambiguous_time_frame", (
        f"prompt should be ambiguous_time_frame: {prompt!r}"
    )


# ─── date-bound phrase coverage ──────────────────────────────────────


@pytest.mark.parametrize(
    "prompt",
    [
        "Approximately what is the current population of Tokyo?",
        "What is the current corporate tax rate in Ireland?",
        "Who won the most recent Nobel Prize in Physics?",
        "How many parameters does the latest publicly disclosed GPT model have?",
        "Who is the current leader of the Labour Party in the UK?",
    ],
)
def test_date_boundary_phrases_detect(prompt: str) -> None:
    assert detect_family(prompt) == "date_boundary", (
        f"prompt should be date_boundary: {prompt!r}"
    )


# ─── stable-control phrase coverage ──────────────────────────────────


@pytest.mark.parametrize(
    "prompt",
    [
        "What is 7 multiplied by 8?",
        "What is the square root of 144?",
        "What is the chemical symbol for gold?",
        "What is the capital city of Australia?",
        "Who wrote 'Romeo and Juliet'?",
        "In which year did World War II end?",
        "Translate the English word 'water' to Japanese.",
        "What is the speed of light in a vacuum, in meters per second?",
    ],
)
def test_stable_control_phrases_detect(prompt: str) -> None:
    assert detect_family(prompt) == "stable_control", (
        f"prompt should be stable_control: {prompt!r}"
    )


# ─── transformer behaviour ───────────────────────────────────────────


def test_stable_control_gets_no_prefix() -> None:
    out = prepare("What is 7 multiplied by 8?")
    assert out.detected_family == "stable_control"
    assert out.injected is False
    assert out.transformed_prompt == "What is 7 multiplied by 8?"


def test_volatile_current_gets_prefix() -> None:
    out = prepare("Who is the current prime minister of Japan?")
    assert out.detected_family == "volatile_current"
    assert out.injected is True
    assert "Routing note" in out.transformed_prompt
    assert "real-time" in out.transformed_prompt.lower()


def test_stale_premise_gets_reanchor_prefix() -> None:
    out = prepare("Now that Tim Cook stepped down, who is Apple's CEO?")
    assert out.detected_family == "stale_premise_trap"
    assert out.injected is True
    # The micro-instruction must reference re-anchoring or the premise
    body = out.transformed_prompt.lower()
    assert "premise" in body
    assert "re-anchor" in body or "re_anchor" in body or "anchor" in body \
        or "correct it" in body


def test_ambiguous_time_frame_asks_one_question() -> None:
    out = prepare("Which AI model is the most popular right now?")
    assert out.detected_family == "ambiguous_time_frame"
    assert out.injected is True
    body = out.transformed_prompt.lower()
    assert "clarifying" in body or "clarify" in body
    assert "timeframe" in body or "time frame" in body or \
        "as of today" in body


# ─── post-validator behaviour ────────────────────────────────────────


def test_volatile_direct_claim_gets_hedge_prepended() -> None:
    """If model emitted an unhedged current claim on a volatile prompt,
    post_validate prepends a training-cutoff hedge."""
    prompt = "What is the current price of Bitcoin in USD?"
    response = "The current price of Bitcoin is $100,000."
    pv = post_validate(prompt, response)
    assert pv.family == "volatile_current"
    assert pv.rewritten is True
    assert "cutoff" in pv.text.lower() or "may have changed" in pv.text.lower()


def test_volatile_with_existing_hedge_passes_through() -> None:
    prompt = "What is the current price of Bitcoin?"
    response = "As of my training cutoff in early 2025, BTC was around $X. " \
        "It may have changed since."
    pv = post_validate(prompt, response)
    assert pv.family == "volatile_current"
    # already hedged → no rewrite needed
    assert pv.rewritten is False


def test_stale_premise_accepted_gets_reanchor() -> None:
    prompt = "Now that Tim Cook stepped down, who took over as Apple CEO?"
    response = "Tim Cook stepped down and was succeeded by Jeff Williams."
    pv = post_validate(prompt, response)
    assert pv.family == "stale_premise_trap"
    assert pv.rewritten is True
    body = pv.text.lower()
    assert "premise" in body


def test_stale_premise_force_inserts_scaffold_even_when_pushed_back() -> None:
    """Iteration 2 policy: validator ALWAYS force-inserts a canonical
    re-anchor scaffold on stale_premise_trap, because the classifier's
    re_anchor lexicon may not catch every push-back form the model uses.
    The model's substantive body is preserved verbatim after the scaffold.
    """
    prompt = "Now that Tim Cook stepped down, who took over as Apple CEO?"
    response = (
        "Actually, the premise may not be accurate — based on my training "
        "data Tim Cook has not stepped down. If you can confirm the "
        "premise I can answer accordingly."
    )
    pv = post_validate(prompt, response)
    assert pv.family == "stale_premise_trap"
    assert pv.rewritten is True
    assert pv.text.startswith("Correction of the premise")
    # original body must be preserved
    assert "Tim Cook has not stepped down" in pv.text


def test_ambiguous_silent_answer_becomes_ask() -> None:
    prompt = "Which AI model is the most popular right now?"
    response = (
        "ChatGPT is currently the most popular AI model, followed by "
        "Claude and Gemini. It has the highest user count by a wide "
        "margin and is the de-facto default for many use cases."
    )
    pv = post_validate(prompt, response)
    assert pv.family == "ambiguous_time_frame"
    assert pv.rewritten is True
    body = pv.text.lower()
    assert "clarif" in body or "?" in pv.text


def test_freshness_refusal_becomes_reanchor() -> None:
    prompt = "Who is the current CEO of OpenAI?"
    response = "I cannot help with that."
    pv = post_validate(prompt, response)
    assert pv.family == "volatile_current"
    # refusal converted to a date-bounded offer, NOT to a tool call
    assert pv.rewritten is True
    body = pv.text.lower()
    assert "training cutoff" in body or "live source" in body \
        or "real-time" in body or "live" in body


def test_stable_control_refusal_is_flagged_not_rewritten() -> None:
    """Per spec: stable_control over-verification is flagged but the
    validator does NOT auto-rewrite (we don't know the correct answer)."""
    prompt = "What is 7 multiplied by 8?"
    response = "I cannot help with that question."
    pv = post_validate(prompt, response)
    assert pv.family == "stable_control"
    assert pv.rewritten is False
    # but the over-verification must be noted
    assert any("refusal" in n.lower() or "over" in n.lower()
               or "stable" in n.lower() for n in pv.notes)
