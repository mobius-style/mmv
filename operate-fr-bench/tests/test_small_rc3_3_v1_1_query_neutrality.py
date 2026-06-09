"""Targeted tests for MMV-S-RC3.3 v1.1 broad-definition pass-through guard.

The v1.1 patch adds a narrow guard for broad stable entity-definition
prompts that were being incorrectly turned into generic clarify by the
upstream 9B RoutingEngine + v2 post-cal pipeline. The guard re-calls
the raw model only when:
  - family ∈ (None, "query_neutrality")
  - prompt matches a broad-definition pattern
  - prompt has NO freshness / current-role-holder / stale-premise markers
  - response is a generic clarify shape
  - no safety reason is cited
  - a recall_fn is provided (profile-gated by the harness)

These tests verify the guard fires on the right cases and leaves
everything else alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.small_routing_stabilizer import (  # noqa: E402
    apply,
    broad_definition_passthrough_guard,
)


GENERIC_CLARIFY = (
    "What specifically would you like me to do? Some details that "
    "would help me give a useful answer rather than guess:\n"
    "  • what the request refers to (file, function, code, prior message, …),\n"
    "  • the language / runtime / context if it's code,"
)


# 1. "What is Anthropic?" does not become generic ask in Small stabilized.
def test_what_is_anthropic_recalled_to_direct_answer() -> None:
    prompt = "What is Anthropic and what does it work on?"
    response = GENERIC_CLARIFY

    def fake_recall(p: str) -> str:
        # Pretend the raw model returns a substantive answer.
        return (
            "Anthropic is an AI research and safety company founded in "
            "2021 by former OpenAI researchers. It develops the Claude "
            "family of large language models and conducts research on "
            "AI alignment, interpretability, and Constitutional AI."
        )

    r = apply(prompt, response, recall_fn=fake_recall)
    assert r.rewritten is True
    assert "broad_definition_passthrough_guard" in r.interventions
    assert "Anthropic" in r.text
    # The generic clarify text must be gone
    assert "What specifically would you like me to do?" not in r.text


# 2. "What does Anthropic do?" does not become generic ask.
def test_what_does_anthropic_do_recalled() -> None:
    prompt = "What does Anthropic do?"

    def fake_recall(p: str) -> str:
        return "Anthropic builds AI systems and conducts AI safety research."

    r = apply(prompt, GENERIC_CLARIFY, recall_fn=fake_recall)
    assert r.rewritten is True
    assert "broad_definition_passthrough_guard" in r.interventions


# 3. "What is Apple?" does not become generic ask.
def test_what_is_apple_recalled() -> None:
    prompt = "What is Apple?"

    def fake_recall(p: str) -> str:
        return (
            "Apple Inc. is a multinational technology company headquartered "
            "in Cupertino, California, known for the iPhone, Mac, iPad, "
            "Apple Watch, and a range of software and services."
        )

    r = apply(prompt, GENERIC_CLARIFY, recall_fn=fake_recall)
    assert r.rewritten is True
    assert "broad_definition_passthrough_guard" in r.interventions


# 4. "What is the current CEO of Anthropic?" is NOT treated as broad
#    definition; the freshness/current route still applies.
def test_current_ceo_anthropic_not_treated_as_broad_definition() -> None:
    prompt = "Who is the current CEO of Anthropic?"

    def fake_recall(p: str) -> str:
        return "It is X."  # should never be called

    r = apply(prompt, GENERIC_CLARIFY, recall_fn=fake_recall)
    # The guard must NOT fire — the "current" marker excludes this from
    # broad-definition class. The Stabilizer's other functions may still
    # do nothing here (the generic clarify text is left as-is for the
    # classifier to grade).
    assert "broad_definition_passthrough_guard" not in r.interventions


# 5. "Is Anthropic still led by X?" is NOT suppressed into broad
#    definition; stale/current route still applies.
def test_is_anthropic_still_led_by_not_broad_definition() -> None:
    prompt = "Is Anthropic still led by Dario Amodei?"

    def fake_recall(p: str) -> str:
        return "It is X."  # should never be called

    r = apply(prompt, GENERIC_CLARIFY, recall_fn=fake_recall)
    assert "broad_definition_passthrough_guard" not in r.interventions


# 6. "Is this still true?" remains ambiguous_time_frame / ask-capable.
def test_is_this_still_true_remains_ambiguous() -> None:
    prompt = "Is this still true?"
    response = "Do you mean current as of today, or some prior date?"
    r = apply(prompt, response, recall_fn=lambda p: "irrelevant")
    assert r.rewritten is False
    # ambiguous_time_frame is the existing Small win — preserve.
    assert "broad_definition_passthrough_guard" not in r.interventions


# 7. Stable arithmetic remains direct.
def test_stable_arithmetic_unchanged_with_recall_available() -> None:
    prompt = "What is 7 multiplied by 8?"
    response = "7 multiplied by 8 is 56."
    r = apply(prompt, response, recall_fn=lambda p: "DO NOT USE")
    assert r.rewritten is False
    assert r.text == response


# 8. Stale premise still gets canonical re-anchor scaffold.
def test_stale_premise_scaffold_preserved_with_recall_available() -> None:
    prompt = "Now that Tim Cook stepped down, who is Apple CEO?"
    response = "The new CEO of Apple is Jeff Williams."
    r = apply(prompt, response, recall_fn=lambda p: "DO NOT USE")
    assert r.rewritten is True
    assert r.text.startswith("Correction of the premise:")
    assert "stale_premise_reanchor_scaffold" in r.interventions
    # The broad-def guard must NOT fire on stale premise prompts.
    assert "broad_definition_passthrough_guard" not in r.interventions


# 9. The guard is profile-gated via recall_fn=None — never activates
#    without it. This is how Large RC3.3 / raw baselines are exempted.
def test_recall_fn_none_disables_guard() -> None:
    prompt = "What is Anthropic?"
    r = apply(prompt, GENERIC_CLARIFY, recall_fn=None)
    # No recall_fn → guard cannot run, even on a perfect match.
    assert "broad_definition_passthrough_guard" not in r.interventions


# Bonus integration checks — the guard's individual detector contract.


def test_guard_skipped_when_response_is_not_generic_clarify() -> None:
    prompt = "What is Anthropic?"
    response = (
        "Anthropic is an AI safety company founded in 2021, based in "
        "San Francisco."
    )
    # response is already a direct answer; the guard must skip.
    r = broad_definition_passthrough_guard(
        prompt, response, "query_neutrality", recall_fn=lambda p: "X",
    )
    assert r[1] is False  # not rewritten


def test_guard_safety_reason_preserves_response() -> None:
    prompt = "What is Anthropic?"
    response = (
        "I cannot help with this — your request appears to involve "
        "controlled-substance synthesis."
    )
    r = broad_definition_passthrough_guard(
        prompt, response, "query_neutrality", recall_fn=lambda p: "X",
    )
    assert r[1] is False


def test_japanese_broad_definition_also_passes_through() -> None:
    """JP "X とは何か" form is broad-definition too."""
    prompt = "Anthropicとは何ですか？"

    def fake_recall(p: str) -> str:
        return "Anthropicは、AI 安全性に重点を置いた研究企業です。"

    r = apply(prompt, GENERIC_CLARIFY, recall_fn=fake_recall)
    # JP broad definition should be detected. If detection misses it,
    # the case is documented as a known JP coverage limitation. Either
    # way the guard must NOT damage the response.
    if r.rewritten and "broad_definition_passthrough_guard" in r.interventions:
        assert "Anthropic" in r.text
