"""Tests for admissibility.py — all rules A through E."""
import pytest
from src.adjudication.admissibility import decide_admissibility
from src.adjudication.evidence_models import (
    ADMISSIBILITY_ANSWERABLE,
    ADMISSIBILITY_BOUNDED_ONLY,
    ADMISSIBILITY_FAILED,
)


def test_rule_a_open_conflict_returns_bounded_only():
    result = decide_admissibility(
        freshness_state="acceptable",
        source_diversity_state="high",
        agreement_state="low",
        conflict_state="open-conflict",
        evidence_strength="strong",
        provenance_state="strong",
    )
    assert result == ADMISSIBILITY_BOUNDED_ONLY


def test_rule_b_weak_evidence_and_provenance_returns_failed():
    result = decide_admissibility(
        freshness_state="acceptable",
        source_diversity_state="low",
        agreement_state="low",
        conflict_state="none",
        evidence_strength="weak",
        provenance_state="weak",
    )
    assert result == ADMISSIBILITY_FAILED


def test_rule_c_stale_risk_with_weak_signals_returns_failed():
    result = decide_admissibility(
        freshness_state="stale-risk",
        source_diversity_state="low",
        agreement_state="low",
        conflict_state="none",
        evidence_strength="weak",
        provenance_state="weak",
    )
    assert result == ADMISSIBILITY_FAILED


def test_rule_c_stale_risk_with_strong_signals_returns_bounded_only():
    result = decide_admissibility(
        freshness_state="stale-risk",
        source_diversity_state="high",
        agreement_state="high",
        conflict_state="none",
        evidence_strength="strong",
        provenance_state="strong",
    )
    assert result == ADMISSIBILITY_BOUNDED_ONLY


def test_rule_d_strong_convergent_set_returns_answerable():
    result = decide_admissibility(
        freshness_state="current-supported",
        source_diversity_state="high",
        agreement_state="high",
        conflict_state="none",
        evidence_strength="strong",
        provenance_state="strong",
    )
    assert result == ADMISSIBILITY_ANSWERABLE


def test_rule_e_default_returns_bounded_only():
    result = decide_admissibility(
        freshness_state="acceptable",
        source_diversity_state="medium",
        agreement_state="mixed",
        conflict_state="none",
        evidence_strength="medium",
        provenance_state="moderate",
    )
    assert result == ADMISSIBILITY_BOUNDED_ONLY
