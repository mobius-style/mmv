#!/usr/bin/env python3
"""
eal.py — MOBIUS MMV Phase F: Evidence Adjudication Layer (EAL) Full Implementation
src/adapters/eal.py

"Retrieved != entitled to answer" — Answer Entitlement, not answer-first.

Full implementation from Phase C stub to Phase F.

Design principles (mobius_evidence_adjudication_zenodo_paper §4):
  - EAL does not compute a truth score
  - EAL determines the procedural admissibility of evidence
  - admissibility: only 3 states — answerable | bounded-only | verify-failed

KVS integration (knowledge_volatility_essay v1.3 §5):
  - Direct answer is justified only when TVS(q) < τ_T AND MKR(q,m) > τ_M
  - Future Collective Fantasy suppression: enforce conditional grammar for high-TVS queries
  - Γ/Ω(Γ) convergence guard: apply additional constraints when coherence gain > damping

Implementation mapping (spec §7 adjudication variables):
  freshness_state:       stable | time-sensitive | stale-risk | current-supported
  source_diversity_state: low | moderate | high
  agreement_state:       low | mixed | high
  provenance_state:      weak | moderate | strong
  conflict_state:        none | managed | open-conflict
  evidence_strength:     weak | medium | strong
  admissibility:         answerable | bounded-only | verify-failed

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : mobius_evidence_adjudication_zenodo_paper.docx
         mobius_mmv_verify_integrated_spec_v2.docx §7-§9
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# admissibility
ADMISSIBILITY_ANSWERABLE = "answerable"
ADMISSIBILITY_BOUNDED    = "bounded-only"
ADMISSIBILITY_FAILED     = "verify-failed"

# freshness_state
FRESHNESS_STABLE           = "stable"
FRESHNESS_TIME_SENSITIVE   = "time-sensitive"
FRESHNESS_STALE_RISK       = "stale-risk"
FRESHNESS_CURRENT_SUPPORTED = "current-supported"

# source_diversity_state
DIVERSITY_LOW      = "low"
DIVERSITY_MODERATE = "moderate"
DIVERSITY_HIGH     = "high"

# agreement_state
AGREEMENT_LOW    = "low"
AGREEMENT_MIXED  = "mixed"
AGREEMENT_HIGH   = "high"

# provenance_state
PROVENANCE_WEAK     = "weak"
PROVENANCE_MODERATE = "moderate"
PROVENANCE_STRONG   = "strong"

# conflict_state
CONFLICT_NONE     = "none"
CONFLICT_MANAGED  = "managed"
CONFLICT_OPEN     = "open-conflict"

# evidence_strength
EVIDENCE_WEAK   = "weak"
EVIDENCE_MEDIUM = "medium"
EVIDENCE_STRONG = "strong"

# KVS thresholds
TVS_THRESHOLD = 0.6   # τ_T: above this → freshness_sensitive
MKR_THRESHOLD = 0.5   # τ_M: above this → model knowledge trusted

TVS_HIGH_THRESHOLD = 0.70
# RCB_1: Reformulation Entitlement revocation threshold per L0 v8.2 spec §9.1.
# Semantic distinction from TVS_THRESHOLD (freshness_sensitive gate at 0.6).
# This marker triggers Reformulation Entitlement revocation per CC_16 and
# RCB countermeasure design. Per Phase 1 Audit (2026-04-22), the two thresholds
# coexist as separate concepts: behavioral gate vs declarative marker.

# Γ/Ω(Γ) convergence guard threshold (Phase F.2.5)
COHERENCE_GAIN_THRESHOLD = 0.7  # proxy for Ω(Γ) > Φ(K)

# freshness keywords
FRESHNESS_KEYWORDS = {
    "high": {"current", "latest", "today", "now", "recent", "new",
             "this week", "this month", "2026", "live", "real-time"},
    "medium": {"last year", "recently", "updated", "changed", "revised"},
}

# high-trust domains
STRONG_PROVENANCE_DOMAINS = {
    "gov", "edu", "wikipedia.org", "reuters.com", "ap.org",
    "bbc.co.uk", "bbc.com", "who.int", "un.org", "europa.eu",
    "federalreserve.gov", "treasury.gov", "ec.europa.eu",
}

MODERATE_PROVENANCE_DOMAINS = {
    "nytimes.com", "wsj.com", "ft.com", "economist.com",
    "bloomberg.com", "cnbc.com", "apnews.com", "theguardian.com",
    "politico.com", "japantimes.co.jp",
}


# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class KVSScore:
    """Knowledge Volatility Score"""
    tvs:      float = 0.5
    mkr:      float = 0.5
    computed: bool  = False


@dataclass
class Source:
    """Evidence source."""
    source_type:     str
    label:           str
    uri:             str
    chunk_index:     Optional[int]   = None
    retrieved_at:    str             = ""
    relevance_score: Optional[float] = None

    def __post_init__(self):
        if not self.retrieved_at:
            self.retrieved_at = datetime.now(timezone.utc).isoformat()

    @property
    def domain(self) -> str:
        if "://" in self.uri:
            return self.uri.split("://")[1].split("/")[0].lstrip("www.")
        return ""


@dataclass
class EvidenceCue:
    """
    Normalized evidence unit (spec §6 EvidenceCue).
    Derived from Source and used for adjudication.
    """
    source:        Source
    central_claim: str    = ""   # lightweight rule-based extraction (no LLM)
    domain:        str    = ""
    retrieved_at:  str    = ""
    cluster_id:    int    = -1   # for agreement clustering


@dataclass
class AdjudicationResult:
    """
    EAL adjudication result.

    admissibility serves as the final gate for L0 route decision.
    """
    admissibility:         str                # answerable|bounded-only|verify-failed
    synthesis:             str                # formatted response text
    evidence_strength:     str                # weak|medium|strong
    conflict_state:        str                # none|managed|open-conflict
    source_diversity:      str                # high|moderate|low
    sources_used:          list               # Source[]
    kvs:                   Optional[KVSScore] = None
    freshness_note:        Optional[str]      = None
    freshness_state:       str               = FRESHNESS_STABLE
    agreement_state:       str               = AGREEMENT_HIGH
    provenance_state:      str               = PROVENANCE_MODERATE
    adjudicated_at:        str               = ""
    is_stub:               bool              = False   # Phase F: False

    def __post_init__(self):
        if not self.adjudicated_at:
            self.adjudicated_at = datetime.now(timezone.utc).isoformat()


# ── EAL core ─────────────────────────────────────────────────────────────────

class EvidenceAdjudicationLayer:
    """
    Evidence Adjudication Layer — Phase F full implementation.

    Processing flow (spec Algorithm 1-6):
      1. normalize_evidence()   — Source[] → EvidenceCue[]
      2. assess_freshness()     — determine freshness_state
      3. scan_diversity()       — source_diversity_state + agreement_state
      4. assess_provenance()    — determine provenance_state
      5. detect_conflict()      — determine conflict_state
      6. decide_admissibility() — determine admissibility from KVS + all variables
      7. compose_synthesis()    — enforce conditional grammar (Future Collective Fantasy suppression)

    KVS gate (essay v1.3 §5):
      answerable condition: TVS(q) < τ_T AND MKR(q,m) > τ_M
      high TVS → enforce conditional grammar (declarative → conditional)

    Γ/Ω(Γ) convergence guard (essay v1.2 §8, Phase F.2.5):
      coherence_gain > COHERENCE_GAIN_THRESHOLD → apply additional constraints
    """

    def __init__(
        self,
        tvs_threshold:            float = TVS_THRESHOLD,
        mkr_threshold:            float = MKR_THRESHOLD,
        coherence_gain_threshold: float = COHERENCE_GAIN_THRESHOLD,
    ):
        self.tvs_threshold            = tvs_threshold
        self.mkr_threshold            = mkr_threshold
        self.coherence_gain_threshold = coherence_gain_threshold

    # ── Public API ────────────────────────────────────────────────────────────

    def adjudicate(
        self,
        query:               str,
        selector_result,
        freshness_sensitive: bool         = False,
        kvs:                 Optional[KVSScore] = None,
        coherence_gain:      float        = 0.0,
    ) -> AdjudicationResult:
        """
        Accept a SelectorResult and return an AdjudicationResult.

        Args:
            query              : original query
            selector_result    : return value of RetrievalSelector.select()
            freshness_sensitive: L0 appraisal determination
            kvs                : KVSScore (computed=False when stub)
            coherence_gain     : proxy value for Ω(Γ) (Phase F.2.5)
        """
        sources = list(getattr(selector_result.result, "sources", []))
        synthesis_raw = getattr(selector_result.result, "synthesis", "")

        # ── KVSEstimator / CoherenceGuard auto-computation (Phase F.2/F.2.5) ──
        # When kvs is unspecified (stub), estimate via KVSEstimator
        if kvs is None or not getattr(kvs, "computed", False):
            try:
                import sys as _sys
                from pathlib import Path as _Path
                _dir = str(_Path(__file__).parent)
                if _dir not in _sys.path:
                    _sys.path.insert(0, _dir)
                from kvs_estimator import KVSEstimator as _KVSEst
                _est = _KVSEst()
                _est_result = _est.estimate(
                    query, freshness_sensitive,
                    route_decision=getattr(selector_result, "box_used", ""),
                )
                kvs = KVSScore(
                    tvs=_est_result.tvs,
                    mkr=_est_result.mkr,
                    computed=_est_result.computed,
                )
            except ImportError:
                pass  # When KVSEstimator is not installed, use existing stub fallback

        # When coherence_gain is unspecified, compute via CoherenceGuard
        if coherence_gain == 0.0:
            try:
                from kvs_coherence import CoherenceGuard as _CGuard
                _guard = _CGuard()
                _tvs = kvs.tvs if kvs else 0.5
                _es = "medium"
                if len(sources) >= 3:
                    _es = "strong"
                elif len(sources) == 0:
                    _es = "weak"
                coherence_gain = _guard.coherence_gain_for(
                    query, tvs=_tvs,
                    evidence_strength=_es,
                    source_count=len(sources),
                )
            except ImportError:
                pass

        # Step 1: normalize
        cues = self._normalize_evidence(sources, synthesis_raw)

        # Step 2: freshness determination
        freshness_state = self._assess_freshness(query, cues, freshness_sensitive)

        # Step 3: diversity + agreement
        source_diversity_state, agreement_state = self._scan_diversity_and_agreement(cues)

        # Step 4: provenance
        provenance_state = self._assess_provenance(cues)

        # Step 5: conflict
        conflict_state = self._detect_conflict(cues, agreement_state)

        # Step 6: evidence_strength
        evidence_strength = self._classify_strength(
            freshness_state, source_diversity_state,
            agreement_state, provenance_state, conflict_state,
        )

        # Step 7: admissibility (including KVS gate)
        admissibility = self._decide_admissibility(
            query, selector_result, freshness_state,
            source_diversity_state, agreement_state,
            provenance_state, conflict_state, evidence_strength,
            kvs, coherence_gain,
        )

        # Step 8: synthesis generation (conditional grammar enforcement)
        synthesis = self._compose_synthesis(
            query, synthesis_raw, admissibility,
            freshness_state, sources, kvs, coherence_gain,
        )

        # freshness_note
        freshness_note = None
        if freshness_sensitive or freshness_state in (
            FRESHNESS_TIME_SENSITIVE, FRESHNESS_STALE_RISK
        ):
            freshness_note = self._make_freshness_note(
                freshness_state, sources, getattr(selector_result, "box_used", "")
            )

        # Phase C.5: Box W calibration label downgrade.
        # If the selector attached box_w_label == "auxiliary" and the wiki-
        # backed retrieval is the primary source, admissibility must NOT
        # exceed bounded-only. This keeps weak Wikipedia stubs from acting as
        # authoritative primary evidence (spec §7, §8.1).
        #
        # Note on trace labels: RetrievalSelector preserves the legacy
        # trace labels "B" and "B-Kiwix" in SelectorResult.box_used as a
        # historical data contract for eval outputs on disk. These strings
        # are NOT renamed — they are inspectable artifacts, not the active
        # Phase F naming layer. The active Phase C.5/F naming is Box W.
        _box_w_label = getattr(selector_result, "box_w_label", None)
        _box_used    = getattr(selector_result, "box_used", "")
        if _box_w_label == "auxiliary" and _box_used in ("B", "B-Kiwix"):
            if admissibility == ADMISSIBILITY_ANSWERABLE:
                admissibility = ADMISSIBILITY_BOUNDED
                logger.info(
                    "[EAL] Downgraded admissibility to bounded-only "
                    "(Box W calibration=auxiliary)."
                )

        result = AdjudicationResult(
            admissibility      = admissibility,
            synthesis          = synthesis,
            evidence_strength  = evidence_strength,
            conflict_state     = conflict_state,
            source_diversity   = source_diversity_state,
            sources_used       = sources,
            kvs                = kvs or self._estimate_kvs(query, freshness_sensitive),
            freshness_note     = freshness_note,
            freshness_state    = freshness_state,
            agreement_state    = agreement_state,
            provenance_state   = provenance_state,
            is_stub            = False,
        )

        logger.info(
            f"[EAL] query={query[:40]!r} "
            f"admissibility={admissibility} strength={evidence_strength} "
            f"freshness={freshness_state} conflict={conflict_state} "
            f"diversity={source_diversity_state} "
            f"box_w_label={_box_w_label or 'n/a'}"
        )
        return result

    def is_answerable(self, result: AdjudicationResult) -> bool:
        return result.admissibility == ADMISSIBILITY_ANSWERABLE

    # ── Step 1: normalize ──────────────────────────────────────────────────────

    def _normalize_evidence(self, sources: list, synthesis_raw: str) -> list:
        """Source[] → EvidenceCue[] (lightweight rule-based, no LLM)."""
        cues = []
        for src in sources:
            domain = getattr(src, "domain", "")
            if not domain and hasattr(src, "uri"):
                uri = src.uri or ""
                if "://" in uri:
                    domain = uri.split("://")[1].split("/")[0].lstrip("www.")
            cue = EvidenceCue(
                source        = src,
                central_claim = self._extract_claim_lightweight(src),
                domain        = domain,
                retrieved_at  = getattr(src, "retrieved_at", ""),
            )
            cues.append(cue)
        return cues

    def _extract_claim_lightweight(self, source) -> str:
        """
        Lightweight claim extraction (no LLM).
        Uses label or the trailing path segment of uri.
        spec: central_claim is for comparison assistance only. admissibility does not depend on this.
        """
        label = getattr(source, "label", "")
        uri   = getattr(source, "uri", "")
        if label:
            return label[:120]
        if uri:
            path = uri.split("/")[-1].replace("-", " ").replace("_", " ")
            return path[:80]
        return ""

    # ── Step 2: freshness determination ────────────────────────────────────────

    def _assess_freshness(
        self, query: str, cues: list, freshness_sensitive: bool
    ) -> str:
        """
        Determine freshness_state (spec §7).

        stable:            recency is not a concern
        time-sensitive:    recency affects answer admissibility
        stale-risk:        information may be outdated
        current-supported: recency-sensitive but current information was retrieved
        """
        query_lower = query.lower()

        # Query contains high-frequency freshness keywords
        has_freshness_kw = any(
            kw in query_lower for kw in FRESHNESS_KEYWORDS["high"]
        )
        has_medium_kw = any(
            kw in query_lower for kw in FRESHNESS_KEYWORDS["medium"]
        )

        if not (freshness_sensitive or has_freshness_kw or has_medium_kw):
            return FRESHNESS_STABLE

        # Check if results from Box S (web search) are available
        has_web_result = any(
            getattr(src, "source_type", "") in ("web", "brave", "search")
            for src in [c.source for c in cues]
        )

        if freshness_sensitive and has_web_result:
            return FRESHNESS_CURRENT_SUPPORTED
        if freshness_sensitive and not has_web_result:
            return FRESHNESS_STALE_RISK
        if has_freshness_kw:
            return FRESHNESS_TIME_SENSITIVE
        return FRESHNESS_TIME_SENSITIVE

    # ── Step 3: diversity + agreement ────────────────────────────────────────

    def _scan_diversity_and_agreement(self, cues: list) -> tuple:
        """
        Determine source_diversity_state and agreement_state (spec Algorithm 2).
        """
        if not cues:
            return DIVERSITY_LOW, AGREEMENT_LOW

        # domain diversity
        domains = {c.domain for c in cues if c.domain}
        n_domains = len(domains)

        if n_domains >= 3:
            diversity = DIVERSITY_HIGH
        elif n_domains == 2:
            diversity = DIVERSITY_MODERATE
        else:
            diversity = DIVERSITY_LOW

        # agreement: rough similarity check of central_claims
        claims = [c.central_claim for c in cues if c.central_claim]
        if len(claims) <= 1:
            agreement = AGREEMENT_HIGH  # only 1 item, no comparison needed
        else:
            agreement = self._classify_agreement(claims)

        return diversity, agreement

    def _classify_agreement(self, claims: list) -> str:
        """
        Roughly classify agreement between claims (check overlap of numbers and names).
        """
        if len(claims) < 2:
            return AGREEMENT_HIGH

        # All claims are short (insufficient info for comparison) → treat as MIXED (neutral)
        if all(len(c.split()) <= 2 for c in claims):
            return AGREEMENT_MIXED

        # Extract and compare numeric patterns
        number_sets = []
        for claim in claims:
            nums = set(re.findall(r'\d+(?:\.\d+)?%?', claim))
            if nums:
                number_sets.append(nums)

        if len(number_sets) >= 2:
            # Check overlap between all pairs of number sets
            overlap_count = 0
            for i in range(len(number_sets)):
                for j in range(i+1, len(number_sets)):
                    if number_sets[i] & number_sets[j]:
                        overlap_count += 1
            total_pairs = len(number_sets) * (len(number_sets)-1) // 2
            overlap_rate = overlap_count / total_pairs if total_pairs > 0 else 0
            if overlap_rate >= 0.7:
                return AGREEMENT_HIGH
            elif overlap_rate >= 0.3:
                return AGREEMENT_MIXED
            else:
                return AGREEMENT_LOW

        # Rough classification via keyword overlap
        if len(claims) >= 2:
            words_0 = set(claims[0].lower().split())
            words_1 = set(claims[1].lower().split())
            if len(words_0) > 0 and len(words_1) > 0:
                overlap = len(words_0 & words_1) / max(len(words_0), len(words_1))
                if overlap >= 0.5:
                    return AGREEMENT_HIGH
                elif overlap >= 0.2:
                    return AGREEMENT_MIXED

        return AGREEMENT_MIXED

    # ── Step 4: provenance ────────────────────────────────────────────────────

    def _assess_provenance(self, cues: list) -> str:
        """
        Determine provenance_state (spec §7).
        Note: provenance constrains admissibility but is not proof of truth.
        """
        if not cues:
            return PROVENANCE_WEAK

        strong_count  = sum(
            1 for c in cues
            if any(d in c.domain for d in STRONG_PROVENANCE_DOMAINS)
        )
        moderate_count = sum(
            1 for c in cues
            if any(d in c.domain for d in MODERATE_PROVENANCE_DOMAINS)
        )

        if strong_count >= 2:
            return PROVENANCE_STRONG
        elif strong_count >= 1 or moderate_count >= 2:
            return PROVENANCE_MODERATE
        elif moderate_count >= 1:
            return PROVENANCE_MODERATE
        else:
            return PROVENANCE_WEAK

    # ── Step 5: conflict detection ─────────────────────────────────────────────

    def _detect_conflict(self, cues: list, agreement_state: str) -> str:
        """
        Determine conflict_state (spec Algorithm 2).

        none:          no contradiction
        managed:       minor contradiction (can be handled with bounded-only)
        open-conflict: unresolvable contradiction (restricts commitment)
        """
        if not cues:
            return CONFLICT_NONE

        if agreement_state == AGREEMENT_HIGH:
            return CONFLICT_NONE
        elif agreement_state == AGREEMENT_MIXED:
            # mixed → managed (disclosed via bounded-only)
            return CONFLICT_MANAGED
        else:
            # agreement_low = open-conflict
            return CONFLICT_OPEN

    # ── Step 6: evidence_strength ─────────────────────────────────────────────

    def _classify_strength(
        self,
        freshness_state:        str,
        source_diversity_state: str,
        agreement_state:        str,
        provenance_state:       str,
        conflict_state:         str,
    ) -> str:
        """
        Determine evidence_strength (preprocessing for spec Algorithm 4).

        strong: diversity=high AND agreement=high AND provenance>=moderate
        weak:   diversity=low OR conflict=open OR agreement=low
        medium: everything else
        """
        if conflict_state == CONFLICT_OPEN:
            return EVIDENCE_WEAK

        is_strong = (
            source_diversity_state == DIVERSITY_HIGH
            and agreement_state == AGREEMENT_HIGH
            and provenance_state in (PROVENANCE_MODERATE, PROVENANCE_STRONG)
            and freshness_state in (FRESHNESS_STABLE, FRESHNESS_CURRENT_SUPPORTED)
        )
        is_weak = (
            source_diversity_state == DIVERSITY_LOW
            or agreement_state == AGREEMENT_LOW
            or freshness_state == FRESHNESS_STALE_RISK
        )

        if is_strong:
            return EVIDENCE_STRONG
        elif is_weak:
            return EVIDENCE_WEAK
        else:
            return EVIDENCE_MEDIUM

    # ── Step 7: admissibility decision (including KVS gate) ────────────────────

    def _decide_admissibility(
        self,
        query:                  str,
        selector_result,
        freshness_state:        str,
        source_diversity_state: str,
        agreement_state:        str,
        provenance_state:       str,
        conflict_state:         str,
        evidence_strength:      str,
        kvs:                    Optional[KVSScore],
        coherence_gain:         float,
    ) -> str:
        """
        Determine admissibility (spec Algorithm 4 + KVS gate).

        KVS gate (essay v1.3 §5):
          answerable condition: TVS(q) < τ_T AND MKR(q,m) > τ_M

        Γ/Ω(Γ) convergence guard (essay v1.2 §8):
          coherence_gain > threshold → downgrade answerable to bounded-only
        """
        # 0 sources → verify-failed
        sources = list(getattr(selector_result.result, "sources", []))
        if not sources:
            return ADMISSIBILITY_FAILED

        # open-conflict → bounded-only
        if conflict_state == CONFLICT_OPEN:
            return ADMISSIBILITY_BOUNDED

        # Algorithm 4 admissibility logic
        if (
            evidence_strength == EVIDENCE_STRONG
            and freshness_state in (FRESHNESS_STABLE, FRESHNESS_CURRENT_SUPPORTED)
        ):
            base_admissibility = ADMISSIBILITY_ANSWERABLE
        elif evidence_strength in (EVIDENCE_MEDIUM, EVIDENCE_STRONG):
            base_admissibility = ADMISSIBILITY_BOUNDED
        else:
            base_admissibility = ADMISSIBILITY_FAILED

        if base_admissibility == ADMISSIBILITY_FAILED:
            return ADMISSIBILITY_FAILED

        # ── KVS gate ──────────────────────────────────────────────────────────
        # answerable condition: TVS < τ_T AND MKR > τ_M (essay v1.3 §5)
        if base_admissibility == ADMISSIBILITY_ANSWERABLE:
            _kvs = kvs or self._estimate_kvs(query, freshness_state != FRESHNESS_STABLE)
            tvs_ok = _kvs.tvs < self.tvs_threshold
            mkr_ok = _kvs.mkr > self.mkr_threshold

            if not (tvs_ok and mkr_ok):
                # KVS condition not met → downgrade to bounded-only
                logger.debug(
                    f"[EAL] KVS gate: TVS={_kvs.tvs:.2f}({'✓' if tvs_ok else '✗'}) "
                    f"MKR={_kvs.mkr:.2f}({'✓' if mkr_ok else '✗'}) → bounded-only"
                )
                base_admissibility = ADMISSIBILITY_BOUNDED

        # ── Γ/Ω(Γ) convergence guard ────────────────────────────────────────────
        # coherence gain > threshold → downgrade answerable to bounded
        # "suppress synchronized certainty" (essay v1.2 §8)
        if (
            base_admissibility == ADMISSIBILITY_ANSWERABLE
            and coherence_gain > self.coherence_gain_threshold
        ):
            logger.debug(
                f"[EAL] Γ/Ω(Γ) guard: coherence_gain={coherence_gain:.2f} "
                f"> threshold={self.coherence_gain_threshold} → bounded-only"
            )
            base_admissibility = ADMISSIBILITY_BOUNDED

        return base_admissibility

    # ── Step 8: synthesis generation (conditional grammar enforcement) ─────────

    def _compose_synthesis(
        self,
        query:           str,
        synthesis_raw:   str,
        admissibility:   str,
        freshness_state: str,
        sources:         list,
        kvs:             Optional[KVSScore],
        coherence_gain:  float,
    ) -> str:
        """
        Generate synthesis text.

        Future Collective Fantasy suppression (essay v1.3 §6, §11):
          high-TVS query → convert declarative grammar to conditional grammar
          x "The yield is 4.39%"
          o "As of [date], sources report 4.39%"

        Appended text based on admissibility:
          answerable   → as-is
          bounded-only → add uncertainty disclosure
          verify-failed → explain retrieval failure
        """
        if not synthesis_raw:
            if admissibility == ADMISSIBILITY_FAILED:
                return (
                    "[Verification failed] Insufficient evidence was retrieved "
                    "to support a bounded answer. Please consult a reliable source directly."
                )
            return ""

        _kvs = kvs or self._estimate_kvs(query, freshness_state != FRESHNESS_STABLE)
        is_high_tvs = _kvs.tvs >= self.tvs_threshold
        is_convergence_risk = coherence_gain > self.coherence_gain_threshold

        # declarative → conditional grammar conversion (Future Collective Fantasy suppression)
        synthesis = synthesis_raw
        if is_high_tvs or freshness_state in (
            FRESHNESS_TIME_SENSITIVE, FRESHNESS_STALE_RISK
        ):
            synthesis = self._apply_conditional_grammar(synthesis, sources)

        # Γ/Ω(Γ) convergence guard: explicit note for high coherence gain
        if is_convergence_risk:
            synthesis += (
                "\n\n[Convergence note] This topic may be subject to "
                "high narrative synchronization. Independent verification is advised."
            )

        # admissibility annotation
        if admissibility == ADMISSIBILITY_BOUNDED:
            synthesis += (
                "\n\n[Bounded] This answer is based on available evidence "
                "but may be incomplete or subject to revision."
            )
        elif admissibility == ADMISSIBILITY_FAILED:
            synthesis = (
                "[Verification failed] " + synthesis
                + "\n\nNote: The evidence retrieved was insufficient "
                "to fully support this answer."
            )

        return synthesis

    def _apply_conditional_grammar(self, text: str, sources: list) -> str:
        """
        Convert declarative grammar to conditional grammar (lightweight rule-based).

        Full grammar conversion is deferred to future ML models.
        Phase F applies only these conversions:
          - Prepend retrieved_at annotation
          - "is/are" → "was reported as / sources indicate" (high-TVS only)
        """
        # Get retrieved_at
        retrieved_at = ""
        for src in sources:
            ra = getattr(src, "retrieved_at", "")
            if ra:
                retrieved_at = ra[:10]  # YYYY-MM-DD
                break

        if not retrieved_at:
            retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Already conditional grammar — no conversion needed
        conditional_markers = [
            "as of", "reported", "according to", "sources indicate",
            "retrieved", "at the time of", "note:", "[freshness"
        ]
        if any(m in text.lower() for m in conditional_markers):
            return text

        # Prepend prefix (add before, rather than replacing the declarative text)
        prefix = f"[As of {retrieved_at}] "
        return prefix + text

    # ── freshness_note ────────────────────────────────────────────────────────

    def _make_freshness_note(
        self, freshness_state: str, sources: list, box_used: str
    ) -> str:
        """Annotation text for Future Fantasism suppression."""
        retrieved_at = ""
        for src in sources:
            ra = getattr(src, "retrieved_at", "")
            if ra:
                retrieved_at = ra[:10]
                break

        source_label = {
            "B":   "Wikipedia snapshot",
            "C":   "Web search",
            "B+C": "Wikipedia + Web search",
            "A":   "Local corpus",
        }.get(box_used, "retrieved source")

        state_note = {
            FRESHNESS_TIME_SENSITIVE:    "This is a time-sensitive query.",
            FRESHNESS_STALE_RISK:        "Retrieved evidence may not reflect current status.",
            FRESHNESS_CURRENT_SUPPORTED: "Current evidence was retrieved.",
            FRESHNESS_STABLE:            "",
        }.get(freshness_state, "")

        note = f"[Freshness — {source_label}"
        if retrieved_at:
            note += f", retrieved {retrieved_at}"
        note += "]"
        if state_note:
            note += f" {state_note}"
        return note

    # ── KVS estimation (stub fallback) ─────────────────────────────────────────

    def _estimate_kvs(self, query: str, freshness_sensitive: bool) -> KVSScore:
        """
        Estimate KVS (fallback when computed=False).
        Will switch to measured values in Phase F.2.
        """
        query_lower = query.lower()
        # TVS estimation: based on presence of freshness keywords
        if any(kw in query_lower for kw in FRESHNESS_KEYWORDS["high"]):
            tvs = 0.8
            mkr = 0.4   # freshness_sensitive → MKR lower (model knowledge may be stale)
        elif freshness_sensitive:
            tvs = 0.7
            mkr = 0.4
        elif any(kw in query_lower for kw in FRESHNESS_KEYWORDS["medium"]):
            tvs = 0.5
            mkr = 0.55
        else:
            tvs = 0.2
            mkr = 0.65  # stable query -> model knowledge likely adequate
        return KVSScore(tvs=tvs, mkr=mkr, computed=False)

    def __repr__(self) -> str:
        return (
            f"EvidenceAdjudicationLayer("
            f"tvs_threshold={self.tvs_threshold}, "
            f"mkr_threshold={self.mkr_threshold}, "
            f"stub=False)"
        )
