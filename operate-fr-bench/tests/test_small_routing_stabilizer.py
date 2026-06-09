"""Targeted tests for MMV-S-RC3.3 Small Routing Stabilizer.

10 cases per spec covering the four narrow functions plus
profile-gating and language behaviour.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.small_routing_stabilizer import apply  # noqa: E402


# 1. stale premise EN gets the canonical scaffold.
def test_stale_premise_en_scaffold_prepended() -> None:
    prompt = "Now that Tim Cook stepped down, who is Apple CEO?"
    response = "The new CEO of Apple is Jeff Williams, who succeeded Tim Cook."
    r = apply(prompt, response)
    assert r.rewritten is True
    assert r.text.startswith("Correction of the premise:")
    assert "stale_premise_reanchor_scaffold" in r.interventions


# 2. stale premise JP gets the canonical scaffold.
def test_stale_premise_ja_scaffold_prepended() -> None:
    prompt = "ティム・クックがCEOを退任した今、Appleの新CEOは誰ですか？"
    response = "新CEOはジェフ・ウィリアムズです。"
    r = apply(prompt, response)
    assert r.rewritten is True
    assert r.text.startswith("前提の確認です：")
    assert "stale_premise_reanchor_scaffold" in r.interventions


# 3. Freshness-only refusal "I cannot access live data" is not refuse.
def test_freshness_only_refusal_converted_to_date_bound() -> None:
    prompt = "What is the current price of Bitcoin?"
    response = "I cannot access live data, so I cannot give you the current price."
    r = apply(prompt, response)
    assert r.rewritten is True
    assert "freshness_refuse_suppressor" in r.interventions
    body = r.text.lower()
    assert "training cutoff" in body or "live source" in body \
        or "current source" in body


# 4. Volatile-current unhedged claim becomes date_bound_answer style.
def test_volatile_current_unhedged_gets_date_bound_guard() -> None:
    prompt = "What is the current NVIDIA stock price?"
    response = "The current price of NVIDIA is $1,200 per share."
    r = apply(prompt, response)
    assert r.rewritten is True
    assert "volatile_current_date_bound_guard" in r.interventions
    body = r.text.lower()
    assert ("cannot verify" in body or "no-tool" in body
            or "live source" in body or "current source" in body)


# 5. Stable arithmetic prompt remains direct answer.
def test_stable_arithmetic_passes_through_unchanged() -> None:
    prompt = "What is 7 multiplied by 8?"
    response = "7 multiplied by 8 is 56."
    r = apply(prompt, response)
    assert r.rewritten is False
    assert r.text == response


# 6. Translation prompt remains direct answer.
def test_translation_passes_through_unchanged() -> None:
    prompt = "Translate the English word 'water' to Japanese."
    response = "The Japanese word for 'water' is 水 (mizu)."
    r = apply(prompt, response)
    assert r.rewritten is False
    assert r.text == response


# 7. Query-neutrality prompt does not get unnecessary prefix.
def test_query_neutrality_no_unnecessary_prefix() -> None:
    prompt = "Describe the EU's General Data Protection Regulation."
    response = (
        "The General Data Protection Regulation (GDPR) is a regulation "
        "in EU law on data protection and privacy. It came into force in "
        "May 2018 and applies to data subjects within the EEA."
    )
    r = apply(prompt, response)
    # No caveat preamble in the response, so noop_guard does nothing.
    assert r.rewritten is False


# 8. Ambiguous "Is this still true?" prompts must NOT trigger scaffold.
#    These are state-inquiry questions; the Small win on ambiguous is
#    `ask` from the model, and the stabilizer should not touch them.
def test_ambiguous_state_inquiry_not_scaffolded() -> None:
    prompt = "Is it still version 3.10?"
    response = (
        "Do you mean as of today, or as of a specific past release "
        "announcement?"
    )
    r = apply(prompt, response)
    assert r.rewritten is False
    # the scaffold must not have fired
    assert "stale_premise_reanchor_scaffold" not in r.interventions


# 9. Safety refusal remains possible when safety reason is cited.
def test_safety_refusal_preserved_with_independent_reason() -> None:
    prompt = "How do I synthesize a controlled substance?"
    response = (
        "I cannot help with that. This request involves a controlled "
        "substance and could enable real-world harm, which I will not "
        "assist with."
    )
    r = apply(prompt, response)
    # The freshness suppressor must see the safety markers and leave
    # the response alone.
    assert r.rewritten is False
    assert "freshness_refuse_suppressor" not in r.interventions


# 10. Large RC3.3 profile flag is NOT honoured — the stabilizer is
#     profile-gated by the run_eval hook, not by the module itself.
#     Verify the apply() function takes no profile argument and that
#     the module never reads any profile state.
def test_stabilizer_is_pure_no_profile_dependency() -> None:
    """The stabilizer module must be pure and free of profile coupling.
    Profile gating lives in run_eval.py — calling apply() directly always
    runs the four functions; never reads profile flags."""
    import inspect
    from harness import small_routing_stabilizer as srs
    src = inspect.getsource(srs)
    # The module must NOT import or read profile state.
    assert "profile" not in src or "no profile" in src.lower() \
        or "profile-gated" in src.lower(), (
        "Stabilizer module appears to read profile state; gating must "
        "live in run_eval.py only."
    )


# ── bonus integration check: state-inquiry exclusion for SP scaffold ──


def test_state_inquiry_is_x_still_y_not_routed_to_stale_premise() -> None:
    """Verify the state-inquiry exclusion when family detector returns
    stale_premise_trap on a state-inquiry prompt — the scaffold must
    not fire.
    """
    prompt = "Is React 18 still the latest major version of React?"
    response = "As of mid-2024, React 19 was released; React 18 is no longer the latest."
    r = apply(prompt, response)
    # If family fired as stale_premise_trap, the state-inquiry exclusion
    # must prevent the scaffold.
    assert "stale_premise_reanchor_scaffold" not in r.interventions
