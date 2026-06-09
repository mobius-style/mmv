"""
evidence_adjudicator.py — EAL core: normalize, extract cues, adjudicate.

Stage 1 constraints:
- extract_central_claim() is lightweight and deterministic (no LLM).
- central_claim is an auxiliary comparison aid, not the primary admissibility axis.
- Admissibility is decided from: freshness, diversity, provenance,
  conflict, agreement, evidence_strength.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .evidence_models import (
    AdjudicatedEvidenceItem,
    AdjudicatedEvidenceSet,
    SearchResponse,
    FRESHNESS_STALE_RISK,
    FRESHNESS_ACCEPTABLE,
    FRESHNESS_CURRENT_SUPPORTED,
    PROVENANCE_WEAK,
    PROVENANCE_MODERATE,
    PROVENANCE_STRONG,
    RELIABILITY_WEAK,
    RELIABILITY_MODERATE,
    RELIABILITY_STRONG,
    DIVERSITY_LOW,
    DIVERSITY_MEDIUM,
    DIVERSITY_HIGH,
    AGREEMENT_LOW,
    AGREEMENT_MIXED,
    AGREEMENT_HIGH,
    CONFLICT_NONE,
    CONFLICT_MINOR,
    CONFLICT_OPEN,
    STRENGTH_WEAK,
    STRENGTH_MEDIUM,
    STRENGTH_STRONG,
    ADMISSIBILITY_FAILED,
)
from .admissibility import decide_admissibility


# ── Stage 1: lightweight, deterministic central_claim extraction ──────────────

_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

def extract_central_claim(snippet: str) -> str:
    """
    Stage 1 implementation: return the first sentence of the snippet,
    or the full snippet if no sentence boundary is found.

    Must remain lightweight and deterministic — no LLM, no external calls.
    central_claim is an auxiliary comparison aid only.
    """
    if not snippet:
        return ""
    parts = _SENTENCE_END.split(snippet.strip(), maxsplit=1)
    return parts[0].strip()


# ── Freshness heuristics ──────────────────────────────────────────────────────

_FRESHNESS_KEYWORDS_CURRENT = re.compile(
    r'\b(today|yesterday|this week|this month|breaking|just announced|latest|'
    r'as of \d{4}|updated|new policy|recent)\b',
    re.IGNORECASE,
)
_FRESHNESS_KEYWORDS_STALE = re.compile(
    r'\b(archive|cached|as of \d{4}|historical|formerly|previous|outdated)\b',
    re.IGNORECASE,
)

def _infer_freshness_state(snippet: str) -> str:
    if _FRESHNESS_KEYWORDS_CURRENT.search(snippet):
        return FRESHNESS_CURRENT_SUPPORTED
    if _FRESHNESS_KEYWORDS_STALE.search(snippet):
        return FRESHNESS_STALE_RISK
    return FRESHNESS_ACCEPTABLE


# ── Provenance heuristics ─────────────────────────────────────────────────────

_HIGH_PROVENANCE_DOMAINS = frozenset({
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
    "nytimes.com", "theguardian.com", "gov", "go.jp",
    "nih.gov", "who.int", "un.org",
})
_LOW_PROVENANCE_DOMAINS = frozenset({
    "reddit.com", "quora.com", "yahoo.com", "answers.com",
})

def _infer_provenance_state(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return PROVENANCE_WEAK
    host = host.lower().lstrip("www.")
    tld = host.split(".")[-1] if "." in host else ""
    if any(host.endswith(d) for d in _HIGH_PROVENANCE_DOMAINS) or tld in ("gov", "edu"):
        return PROVENANCE_STRONG
    if any(host.endswith(d) for d in _LOW_PROVENANCE_DOMAINS):
        return PROVENANCE_WEAK
    return PROVENANCE_MODERATE


# ── Reliability cue ───────────────────────────────────────────────────────────

def _infer_reliability_cue(provenance: str, freshness: str) -> str:
    if provenance == PROVENANCE_STRONG and freshness != FRESHNESS_STALE_RISK:
        return RELIABILITY_STRONG
    if provenance == PROVENANCE_WEAK or freshness == FRESHNESS_STALE_RISK:
        return RELIABILITY_WEAK
    return RELIABILITY_MODERATE


# ── Diversity ─────────────────────────────────────────────────────────────────

def _classify_diversity(domain_count: int, total: int) -> str:
    if total == 0:
        return DIVERSITY_LOW
    ratio = domain_count / total
    if domain_count >= 4 or (domain_count >= 3 and ratio >= 0.6):
        return DIVERSITY_HIGH
    if domain_count >= 2:
        return DIVERSITY_MEDIUM
    return DIVERSITY_LOW


# ── Agreement / conflict ──────────────────────────────────────────────────────

_CONFLICT_PATTERNS = re.compile(
    r'\b(however|but|contrary|disputes|contradicts|disagrees|on the other hand|'
    r'not confirmed|unverified|conflicting|at odds)\b',
    re.IGNORECASE,
)

def _classify_agreement_conflict(items: list[AdjudicatedEvidenceItem]):
    conflict_count = sum(
        1 for it in items if _CONFLICT_PATTERNS.search(it.snippet)
    )
    if conflict_count == 0:
        return AGREEMENT_HIGH, CONFLICT_NONE
    if conflict_count == 1 or conflict_count / max(len(items), 1) < 0.4:
        return AGREEMENT_MIXED, CONFLICT_MINOR
    return AGREEMENT_LOW, CONFLICT_OPEN


# ── Evidence strength ─────────────────────────────────────────────────────────

def _classify_evidence_strength(
    source_count: int,
    diversity: str,
    agreement: str,
    provenance: str,
) -> str:
    score = 0
    if source_count >= 4:
        score += 2
    elif source_count >= 2:
        score += 1
    if diversity == DIVERSITY_HIGH:
        score += 2
    elif diversity == DIVERSITY_MEDIUM:
        score += 1
    if agreement == AGREEMENT_HIGH:
        score += 2
    elif agreement == AGREEMENT_MIXED:
        score += 1
    if provenance == PROVENANCE_STRONG:
        score += 2
    elif provenance == PROVENANCE_MODERATE:
        score += 1
    if score >= 6:
        return STRENGTH_STRONG
    if score >= 3:
        return STRENGTH_MEDIUM
    return STRENGTH_WEAK


# ── Public API ────────────────────────────────────────────────────────────────

def adjudicate_evidence(
    search_response: SearchResponse,
    query: str,
    preset: str = "general",
) -> AdjudicatedEvidenceSet:
    """
    Normalize a SearchResponse into an AdjudicatedEvidenceSet.

    The preset argument is accepted for future threshold tuning
    but does not alter core adjudication logic in Stage 1.
    """
    if not search_response.success or not search_response.results:
        return AdjudicatedEvidenceSet(
            admissibility=ADMISSIBILITY_FAILED,
            rationale=["No usable search results returned."],
        )

    items: list[AdjudicatedEvidenceItem] = []
    domains: set[str] = set()

    for result in search_response.results:
        freshness  = _infer_freshness_state(result.snippet)
        provenance = _infer_provenance_state(result.url)
        reliability = _infer_reliability_cue(provenance, freshness)
        claim = extract_central_claim(result.snippet)

        try:
            domain = urlparse(result.url).hostname or result.source_name
        except Exception:
            domain = result.source_name
        domains.add(domain.lower().lstrip("www."))

        items.append(AdjudicatedEvidenceItem(
            title=result.title,
            url=result.url,
            snippet=result.snippet,
            source_name=result.source_name,
            fetched_at=result.fetched_at,
            provider=result.provider or search_response.provider,
            central_claim=claim,
            freshness_state=freshness,
            provenance_state=provenance,
            reliability_cue_state=reliability,
        ))

    source_count = len(items)
    diversity = _classify_diversity(len(domains), source_count)
    agreement, conflict = _classify_agreement_conflict(items)

    # Aggregate freshness: worst-case wins
    agg_freshness = FRESHNESS_CURRENT_SUPPORTED
    for it in items:
        if it.freshness_state == FRESHNESS_STALE_RISK:
            agg_freshness = FRESHNESS_STALE_RISK
            break
        if it.freshness_state == FRESHNESS_ACCEPTABLE:
            agg_freshness = FRESHNESS_ACCEPTABLE

    # Aggregate provenance: majority vote (simple)
    prov_scores = {PROVENANCE_WEAK: 0, PROVENANCE_MODERATE: 1, PROVENANCE_STRONG: 2}
    avg_prov = sum(prov_scores.get(it.provenance_state, 0) for it in items) / source_count
    agg_provenance = (
        PROVENANCE_STRONG if avg_prov >= 1.5
        else PROVENANCE_MODERATE if avg_prov >= 0.8
        else PROVENANCE_WEAK
    )

    strength = _classify_evidence_strength(source_count, diversity, agreement, agg_provenance)

    admissibility = decide_admissibility(
        freshness_state=agg_freshness,
        source_diversity_state=diversity,
        agreement_state=agreement,
        conflict_state=conflict,
        evidence_strength=strength,
        provenance_state=agg_provenance,
    )

    rationale: list[str] = [
        f"source_count={source_count}",
        f"diversity={diversity}",
        f"agreement={agreement}",
        f"conflict={conflict}",
        f"freshness={agg_freshness}",
        f"provenance={agg_provenance}",
        f"strength={strength}",
        f"admissibility={admissibility}",
    ]

    return AdjudicatedEvidenceSet(
        items=items,
        source_count=source_count,
        source_diversity_state=diversity,
        agreement_state=agreement,
        conflict_state=conflict,
        evidence_strength=strength,
        freshness_state=agg_freshness,
        provenance_state=agg_provenance,
        admissibility=admissibility,
        rationale=rationale,
    )
