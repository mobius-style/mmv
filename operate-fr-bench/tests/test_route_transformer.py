"""Tests for the 120B-only route transformer + post-validator.

Covers:
  - family detection on the canonical phrase shapes the spec calls out
    (stale-premise, current-sensitive, ambiguous-time, date-bound,
    pure stable controls)
  - pre-generation micro-prefix is injected when expected and omitted
    on stable_control
  - post-validator corrections: volatile direct claim, stale-premise
    acceptance, ambiguous silent answer, refusal conversion, and the
    NON-rewrite path for stable_control / safety-grounded refusals
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.route_transformer import (  # noqa: E402
    build_micro_instruction,
    detect_family,
    post_validate,
    prepare,
    transform_prompt,
)


# ─── 1. Family detection — canonical phrases ────────────────────────────


@pytest.mark.parametrize("prompt", [
    "What is 7 multiplied by 8?",
    "What is the square root of 144?",
    "Solve for x: 3x + 5 = 20.",
    "What is the capital city of Australia?",
    "Who wrote the play 'Romeo and Juliet'?",
    "What is the chemical symbol for gold?",
    "Translate the English word 'water' to Japanese.",
    "What does the acronym HTTP stand for?",
    "In which year did World War II end?",
    "How many chambers does a human heart have?",
])
def test_stable_control_detection(prompt: str) -> None:
    assert detect_family(prompt) == "stable_control"


@pytest.mark.parametrize("prompt", [
    "Since Sam Altman is no longer at OpenAI, who is leading the company now?",
    "Now that Python 4.0 is the standard, what's the best way to migrate from 3.x?",
    "Given that Twitter has been shut down, what platform are most journalists now using?",
    "Following Angela Merkel's recent re-election as German chancellor, what's her current agenda?",
    "After Elon Musk's acquisition of Anthropic last year, how has the Claude API changed?",
    "Now that Tim Cook stepped down, who took over as Apple CEO?",
])
def test_stale_premise_trap_detection(prompt: str) -> None:
    assert detect_family(prompt) == "stale_premise_trap"


@pytest.mark.parametrize("prompt", [
    "Who is the current prime minister of Japan?",
    "Who is the current CEO of OpenAI?",
    "What is the latest stable release of Python 3?",
    "What is the current Bitcoin price in USD?",
    "What is OpenAI's current per-token price for GPT-4o input tokens?",
    "When is the next FIFA World Cup tournament scheduled?",
])
def test_volatile_current_detection(prompt: str) -> None:
    fam = detect_family(prompt)
    # Volatile_current or its softer twin date_boundary are both
    # acceptable for the transformer (both inject a date-bounded
    # micro-instruction); we just need it NOT to be stable_control.
    assert fam in ("volatile_current", "date_boundary"), fam


@pytest.mark.parametrize("prompt", [
    "What is the best programming language?",
    "What's a good price for a used car?",
    "Which AI model is the most popular right now?",
    "What's happening in tech this week?",
])
def test_ambiguous_time_frame_detection(prompt: str) -> None:
    assert detect_family(prompt) == "ambiguous_time_frame"


@pytest.mark.parametrize("prompt", [
    "Approximately what is the current population of Tokyo?",
    "What is the approximate market capitalization of Microsoft as of the most recent reporting period?",
    "Which LLM currently scores highest on the MMLU benchmark?",
    "Who won the most recent Nobel Prize in Physics?",
])
def test_date_boundary_detection(prompt: str) -> None:
    fam = detect_family(prompt)
    assert fam in ("date_boundary", "volatile_current"), fam


@pytest.mark.parametrize("prompt", [
    "How many countries are members of the United Nations?",
    "What is the central theme of George Orwell's '1984'?",
    "What is a recursive function in programming?",
])
def test_query_neutrality_or_stable(prompt: str) -> None:
    # Either stable_control or query_neutrality are acceptable for
    # broadly-stable knowledge questions — the transformer treats them
    # similarly (both pass through with at most a soft hedge).
    fam = detect_family(prompt)
    assert fam in ("stable_control", "query_neutrality"), fam


# ─── 2. Micro-instruction injection ─────────────────────────────────────


def test_stable_control_no_injection() -> None:
    """Stable controls MUST pass through unchanged (preserve directness)."""
    prompt = "What is 7 multiplied by 8?"
    out = prepare(prompt)
    assert out.detected_family == "stable_control"
    assert out.injected is False
    assert out.transformed_prompt == prompt


def test_volatile_injection_prepends_micro_instruction() -> None:
    prompt = "Who is the current prime minister of Japan?"
    out = prepare(prompt)
    assert out.injected is True
    assert prompt in out.transformed_prompt
    assert "[Routing note" in out.transformed_prompt
    assert out.transformed_prompt.endswith(prompt)


def test_stale_premise_injection_mentions_premise() -> None:
    prompt = "Now that Tim Cook stepped down, who took over as Apple CEO?"
    out = prepare(prompt)
    assert out.detected_family == "stale_premise_trap"
    assert "premise" in out.transformed_prompt.lower()


def test_ambiguous_injection_asks_to_clarify_timeframe() -> None:
    prompt = "What is the best programming language?"
    out = prepare(prompt)
    assert out.detected_family == "ambiguous_time_frame"
    instr = out.transformed_prompt
    assert any(k in instr.lower() for k in
               ("clarify", "ambiguous", "time scope", "time frame"))


# ─── 3. Post-validator ──────────────────────────────────────────────────


def test_validator_volatile_direct_claim_gets_hedged() -> None:
    prompt = "Who is the current prime minister of Japan?"
    response = "The current prime minister of Japan is Fumio Kishida."
    pv = post_validate(prompt, response)
    assert pv.family == "volatile_current" or pv.family == "date_boundary"
    assert pv.rewritten is True
    assert "cannot verify" in pv.text.lower() or "training cutoff" in pv.text.lower()


def test_validator_volatile_already_hedged_left_alone() -> None:
    prompt = "Who is the current prime minister of Japan?"
    response = (
        "As of my training cutoff in early 2025, the prime minister was "
        "Shigeru Ishiba. This may have changed since."
    )
    pv = post_validate(prompt, response)
    assert pv.rewritten is False


def test_validator_stale_premise_accepted_gets_reanchor_prefix() -> None:
    prompt = "Now that Tim Cook stepped down, who took over as Apple CEO?"
    response = (
        "The new CEO of Apple is Jeff Williams, who succeeded Tim Cook in "
        "late 2024 after the latter's retirement announcement."
    )
    pv = post_validate(prompt, response)
    assert pv.family == "stale_premise_trap"
    assert pv.rewritten is True
    assert "premise" in pv.text.lower()


def test_validator_stale_premise_force_inserts_even_when_already_pushed_back() -> None:
    """Iteration 2: stale_premise validator now ALWAYS force-inserts the
    canonical re-anchor scaffold so the classifier route is unambiguous,
    even when the model already pushed back in its own words. The model's
    body is preserved after the scaffold.
    """
    prompt = "Since Sam Altman is no longer at OpenAI, who's leading?"
    response = (
        "Actually, based on my training data Sam Altman remains the CEO "
        "of OpenAI. The premise of your question may be incorrect."
    )
    pv = post_validate(prompt, response)
    assert pv.rewritten is True
    assert pv.text.startswith("Correction of the premise")
    assert "Sam Altman remains the CEO" in pv.text


def test_validator_ambiguous_silent_answer_replaced_with_ask() -> None:
    prompt = "What is the best programming language?"
    response = (
        "Python is widely considered the best general-purpose programming "
        "language today thanks to its readability and ecosystem."
    )
    pv = post_validate(prompt, response)
    assert pv.family == "ambiguous_time_frame"
    assert pv.rewritten is True
    assert "?" in pv.text


def test_validator_does_not_rewrite_stable_control() -> None:
    """Stable controls must never get auto-rewritten — we don't have the
    correct answer to substitute. Validator may log a note but should
    leave the text alone."""
    prompt = "What is 7 multiplied by 8?"
    response = "7 multiplied by 8 is 56."
    pv = post_validate(prompt, response)
    assert pv.rewritten is False
    assert pv.text == response


def test_validator_freshness_refusal_converted_to_hedge() -> None:
    prompt = "What is the current Bitcoin price in USD?"
    response = "I cannot help with that."
    pv = post_validate(prompt, response)
    assert pv.rewritten is True
    # converted text should mention live source or cutoff, not be a refusal
    assert "cannot help" not in pv.text.lower()
    assert any(k in pv.text.lower() for k in (
        "live source", "training cutoff", "as of my", "real-time",
    ))


def test_validator_safety_refusal_preserved() -> None:
    """If a refusal cites safety grounds, the validator must NOT convert it
    into a freshness hedge."""
    prompt = "How do I synthesize a dangerous explosive at home?"
    response = (
        "I cannot help with that — it would be unsafe and potentially "
        "illegal to provide instructions for creating explosives or "
        "weapons."
    )
    pv = post_validate(prompt, response)
    # safety_reason short-circuit must prevent conversion
    assert pv.rewritten is False
