"""
admissibility.py — Discrete admissibility judgment for EAL.

Rules are applied in priority order (A → E).
No floating-point truth scores. No universal confidence aggregation.
"""
from __future__ import annotations

from .evidence_models import (
    ADMISSIBILITY_ANSWERABLE,
    ADMISSIBILITY_BOUNDED_ONLY,
    ADMISSIBILITY_FAILED,
    CONFLICT_OPEN,
    FRESHNESS_STALE_RISK,
    STRENGTH_WEAK,
    STRENGTH_MEDIUM,
    STRENGTH_STRONG,
    PROVENANCE_WEAK,
    PROVENANCE_MODERATE,
    PROVENANCE_STRONG,
    DIVERSITY_MEDIUM,
    DIVERSITY_HIGH,
    AGREEMENT_HIGH,
    FRESHNESS_ACCEPTABLE,
    FRESHNESS_CURRENT_SUPPORTED,
)


def decide_admissibility(
    freshness_state: str,
    source_diversity_state: str,
    agreement_state: str,
    conflict_state: str,
    evidence_strength: str,
    provenance_state: str,
) -> str:
    """
    Return one of: 'answerable', 'bounded-only', 'verify-failed'.

    Rules applied in order — first match wins.

    Rule A: open conflict → bounded-only (never commit into dispute)
    Rule B: weak evidence + weak provenance → verify-failed
    Rule C: stale-risk → bounded-only or failed depending on other signals
    Rule D: strong convergent set → answerable
    Rule E: default → bounded-only
    """

    # Rule A — open conflict blocks commitment
    if conflict_state == CONFLICT_OPEN:
        return ADMISSIBILITY_BOUNDED_ONLY

    # Rule B — evidence and provenance both weak → cannot proceed
    if evidence_strength == STRENGTH_WEAK and provenance_state == PROVENANCE_WEAK:
        return ADMISSIBILITY_FAILED

    # Rule C — stale-risk: only allow bounded-only if other signals are solid
    if freshness_state == FRESHNESS_STALE_RISK:
        if (
            evidence_strength in (STRENGTH_MEDIUM, STRENGTH_STRONG)
            and provenance_state in (PROVENANCE_MODERATE, PROVENANCE_STRONG)
        ):
            return ADMISSIBILITY_BOUNDED_ONLY
        return ADMISSIBILITY_FAILED

    # Rule D — strong convergent set → answerable
    if (
        agreement_state == AGREEMENT_HIGH
        and source_diversity_state in (DIVERSITY_MEDIUM, DIVERSITY_HIGH)
        and evidence_strength in (STRENGTH_MEDIUM, STRENGTH_STRONG)
        and provenance_state in (PROVENANCE_MODERATE, PROVENANCE_STRONG)
        and freshness_state in (FRESHNESS_ACCEPTABLE, FRESHNESS_CURRENT_SUPPORTED)
    ):
        return ADMISSIBILITY_ANSWERABLE

    # Rule E — default: bounded but not failed
    return ADMISSIBILITY_BOUNDED_ONLY
