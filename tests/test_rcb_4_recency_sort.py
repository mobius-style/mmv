"""
RCB_4 Recency Rule: programmatic sort as Outer Conscience backstop.

Per Phase 1 Audit (2026-04-22): previous implementation was prompt-only.
CC_13 (Outer Conscience) requires inspectable/adjustable external governance,
not hidden prompt instruction. This test set locks in the programmatic
sort contract so LLM non-compliance with the recency_rule prompt cannot
silently elevate stale evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.compose.verify_synthesizer import (
    _sort_items_by_freshness,
    _build_evidence_block,
)


@dataclass
class _MockItem:
    title: str
    freshness_state: str | None = None
    source_name: str = "test-source"
    snippet: str = "snippet"
    url: str = "http://example.com"


# ── _sort_items_by_freshness ────────────────────────────────────────────────

def test_current_supported_first():
    items = [
        _MockItem("stale",      "stale-risk"),
        _MockItem("current",    "current-supported"),
        _MockItem("acceptable", "acceptable"),
    ]
    out = _sort_items_by_freshness(items)
    assert [i.title for i in out] == ["current", "acceptable", "stale"]


def test_stable_sort_within_class():
    items = [
        _MockItem("a", "acceptable"),
        _MockItem("b", "acceptable"),
        _MockItem("c", "acceptable"),
    ]
    out = _sort_items_by_freshness(items)
    assert [i.title for i in out] == ["a", "b", "c"]


def test_missing_freshness_treated_as_acceptable():
    items = [
        _MockItem("stale",   "stale-risk"),
        _MockItem("unknown", None),
        _MockItem("current", "current-supported"),
    ]
    out = _sort_items_by_freshness(items)
    assert [i.title for i in out] == ["current", "unknown", "stale"]


def test_unknown_freshness_string_treated_as_acceptable():
    # A defensive case: if a provider emits a freshness_state we do not
    # recognise, treat it as acceptable (middle), never as stale.
    items = [
        _MockItem("stale",       "stale-risk"),
        _MockItem("weird-state", "some-future-value"),
        _MockItem("current",     "current-supported"),
    ]
    out = _sort_items_by_freshness(items)
    assert out[0].title == "current"
    assert out[-1].title == "stale"


def test_all_same_class_preserved_order():
    items = [
        _MockItem("first",  "current-supported"),
        _MockItem("second", "current-supported"),
        _MockItem("third",  "current-supported"),
    ]
    out = _sort_items_by_freshness(items)
    assert [i.title for i in out] == ["first", "second", "third"]


def test_empty_list_returns_empty():
    assert _sort_items_by_freshness([]) == []


# ── _build_evidence_block: sorted order reflected ───────────────────────────

def _make_adjudicated(items):
    """Minimal AdjudicatedEvidenceSet proxy — _build_evidence_block only
    reads .items, so a simple namespace suffices."""
    class _X:
        pass
    x = _X()
    x.items = items
    return x


def test_evidence_block_enumerates_in_freshness_order():
    items = [
        _MockItem("stale-t",   "stale-risk",        source_name="stale-src"),
        _MockItem("current-t", "current-supported", source_name="current-src"),
    ]
    block = _build_evidence_block(_make_adjudicated(items))
    # "[1]" must be paired with the current item, "[2]" with the stale one.
    idx1 = block.find("[1]")
    idx2 = block.find("[2]")
    idx_current = block.find("current-src")
    idx_stale = block.find("stale-src")
    assert idx1 < idx_current < idx2
    assert idx_current < idx_stale


def test_evidence_block_does_not_mutate_input_order():
    # Contract: the sort must not mutate the caller's list (sorted() returns
    # a new list). Protect against a future refactor that uses .sort().
    items = [
        _MockItem("stale",   "stale-risk"),
        _MockItem("current", "current-supported"),
    ]
    original = list(items)
    _build_evidence_block(_make_adjudicated(items))
    assert items == original


# ── Recency prompt instruction retained ────────────────────────────────────

def test_recency_rule_prompt_instruction_retained():
    # The programmatic sort complements, not replaces, the prompt instruction.
    # Both defenses must remain in _build_prompt so LLMs that honour the
    # instruction still see it.
    from src.compose.verify_synthesizer import _build_prompt
    from src.adjudication.evidence_models import AdjudicatedEvidenceSet
    adjudicated = AdjudicatedEvidenceSet()
    prompt = _build_prompt(
        query="test",
        outcome="verify_success",
        evidence_block="",
        adjudicated=adjudicated,
        active_language="en",
    )
    # Match on a unique fragment of the recency_rule body defined in
    # verify_synthesizer.py:135-142.
    assert "most recent temporal evidence" in prompt
