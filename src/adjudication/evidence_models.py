"""
evidence_models.py — Canonical data contracts for MMV Verify / EAL.

All provider-specific code must normalize to these types.
The kernel, adjudicator, and synthesizer depend only on these contracts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Search contracts ──────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source_name: str
    fetched_at: str                          # ISO 8601 UTC string
    rank: int | None = None
    provider: str | None = None
    provider_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResponse:
    query: str
    provider: str
    success: bool
    results: list[SearchResult] = field(default_factory=list)
    error_message: str | None = None


# ── Adjudication contracts ────────────────────────────────────────────────────

# Discrete state literals — do not change values without updating admissibility.py

# freshness_state
FRESHNESS_STALE_RISK       = "stale-risk"
FRESHNESS_ACCEPTABLE       = "acceptable"
FRESHNESS_CURRENT_SUPPORTED = "current-supported"

# provenance_state
PROVENANCE_WEAK     = "weak"
PROVENANCE_MODERATE = "moderate"
PROVENANCE_STRONG   = "strong"

# reliability_cue_state
RELIABILITY_WEAK     = "weak"
RELIABILITY_MODERATE = "moderate"
RELIABILITY_STRONG   = "strong"

# source_diversity_state
DIVERSITY_LOW    = "low"
DIVERSITY_MEDIUM = "medium"
DIVERSITY_HIGH   = "high"

# agreement_state
AGREEMENT_LOW   = "low"
AGREEMENT_MIXED = "mixed"
AGREEMENT_HIGH  = "high"

# conflict_state
CONFLICT_NONE          = "none"
CONFLICT_MINOR         = "minor-conflict"
CONFLICT_OPEN          = "open-conflict"

# evidence_strength
STRENGTH_WEAK   = "weak"
STRENGTH_MEDIUM = "medium"
STRENGTH_STRONG = "strong"

# admissibility — final output gate
ADMISSIBILITY_ANSWERABLE   = "answerable"
ADMISSIBILITY_BOUNDED_ONLY = "bounded-only"
ADMISSIBILITY_FAILED       = "verify-failed"


@dataclass
class AdjudicatedEvidenceItem:
    title: str
    url: str
    snippet: str
    source_name: str
    fetched_at: str
    provider: str
    # Stage 1: central_claim is an auxiliary comparison aid only.
    # Must be lightweight and deterministic — use raw snippet or shallow rule.
    # LLM-based extraction is deferred to a later hardening stage.
    central_claim: str
    freshness_state: str
    provenance_state: str
    reliability_cue_state: str


@dataclass
class AdjudicatedEvidenceSet:
    items: list[AdjudicatedEvidenceItem] = field(default_factory=list)
    source_count: int = 0
    source_diversity_state: str = DIVERSITY_LOW
    agreement_state: str = AGREEMENT_LOW
    conflict_state: str = CONFLICT_NONE
    evidence_strength: str = STRENGTH_WEAK
    freshness_state: str = FRESHNESS_STALE_RISK
    provenance_state: str = PROVENANCE_WEAK
    admissibility: str = ADMISSIBILITY_FAILED
    rationale: list[str] = field(default_factory=list)
