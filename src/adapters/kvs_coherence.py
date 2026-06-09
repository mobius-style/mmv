#!/usr/bin/env python3
"""
kvs_coherence.py — MOBIUS MMV Phase F.2.5: Gamma/Omega(Gamma) Convergence Guard
src/adapters/kvs_coherence.py

Implementation of essay v1.2/v1.3 section 8.

future collective fantasy = volatility + bounded ignorance + synchronized coherence gain

"observer convergence becomes dangerous when coherence gain outpaces
 institutional and epistemic damping"

Gamma (expectation kernel): Structure of socially circulating expectations
Omega(Gamma): Coherence gain when multiple agents synchronize
Phi(K): Friction/damping (institutional and epistemic damping)

Threshold where convergence becomes dangerous: Omega(Gamma) > Phi(K)

Implementation approach:
  Fully measuring Omega(Gamma) is impossible (social phenomenon).
  Instead, we use a proxy: "whether this query type tends to elicit
  confident answers from the model."

  Coherence gain proxy:
    1. Prediction/forecast/future/assertion keywords (narrative lock-in)
    2. High TVS x high evidence_strength (strong evidence despite high volatility)
    3. Classes with high verify_success rate in audit stats (answered confidently in the past)

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : knowledge_volatility_essay v1.3 §8
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# -- Convergence risk keywords (topics where Gamma tends to synchronize) -------
# Query patterns likely to produce high coherence gain
CONVERGENCE_RISK_KEYWORDS: dict[str, float] = {
    # Prediction/assertion (stating the future as certain)
    "will":          0.3,
    "definitely":    0.5,
    "certainly":     0.5,
    "inevitable":    0.6,
    "must":          0.3,
    "prediction":    0.4,
    "forecast":      0.4,
    "going to":      0.3,
    "expected to":   0.3,
    "destined":      0.6,

    # Social convergence (many people seeking the same information)
    "market will":   0.5,
    "price will":    0.5,
    "stock":         0.3,
    "crash":         0.4,
    "bubble":        0.4,
    "collapse":      0.4,
    "revolution":    0.3,
    "crisis":        0.3,
    "consensus":     0.4,
    "everyone":      0.3,
    "all experts":   0.4,
    "most analysts": 0.4,

    # Politics/elections (election predictions have especially high convergence risk)
    "will win":      0.5,
    "will lose":     0.4,
    "elected":       0.3,
    "polls show":    0.4,
    "leading":       0.3,

    # AI's own predictions
    "ai will":       0.5,
    "artificial intelligence will": 0.5,
    "technology will": 0.3,
}

# Low convergence risk (fact-checking queries)
LOW_CONVERGENCE_KEYWORDS = {
    "how many", "when was", "what is the", "who is the",
    "definition", "explain", "describe", "history of",
    "founded", "established", "chemical symbol",
}

COHERENCE_GAIN_BASE     = 0.0
COHERENCE_GAIN_MAX      = 1.0
DAMPING_BASE            = 0.4   # Phi(K) baseline value


@dataclass
class CoherenceGainResult:
    """Gamma/Omega(Gamma) estimation result"""
    coherence_gain:    float        # Omega(Gamma) proxy value 0.0-1.0
    damping:           float        # Phi(K) proxy value
    net_gain:          float        # Omega(Gamma) - Phi(K)
    is_dangerous:      bool         # net_gain > 0
    triggered_keywords: list[str]   # Convergence risk keywords
    reason:            str


class CoherenceGuard:
    """
    Gamma/Omega(Gamma) convergence guard.

    Calculates coherence_gain before EAL admissibility decision
    to detect synchronized certainty.

    Usage:
        guard = CoherenceGuard()
        result = guard.assess(
            query="Will the market crash?",
            tvs=0.7,
            evidence_strength="strong",
        )
        if result.is_dangerous:
            # Pass coherence_gain to EAL and downgrade to bounded-only
            admissibility = "bounded-only"
    """

    def __init__(self, danger_threshold: float = 0.5):
        self.danger_threshold = danger_threshold

    def assess(
        self,
        query:            str,
        tvs:              float = 0.5,
        evidence_strength: str  = "medium",
        source_count:     int   = 1,
    ) -> CoherenceGainResult:
        """
        Evaluate the convergence risk of a query.

        Args:
            query            : Query string
            tvs              : TVS (higher volatility = higher convergence risk)
            evidence_strength: EAL evidence strength
            source_count     : Number of sources (more sources = higher convergence risk)

        Returns:
            CoherenceGainResult
        """
        query_lower = query.lower()

        # Low convergence keyword check (early return)
        if any(kw in query_lower for kw in LOW_CONVERGENCE_KEYWORDS):
            return CoherenceGainResult(
                coherence_gain=0.1, damping=DAMPING_BASE,
                net_gain=0.1 - DAMPING_BASE, is_dangerous=False,
                triggered_keywords=[], reason="low_convergence_query"
            )

        # Omega(Gamma) calculation
        gain = COHERENCE_GAIN_BASE
        triggered = []

        for kw, kw_score in CONVERGENCE_RISK_KEYWORDS.items():
            if kw in query_lower:
                gain += kw_score
                triggered.append(kw)

        # Higher TVS increases convergence risk (volatility x confidence = danger)
        if tvs > 0.6:
            tvs_boost = (tvs - 0.6) * 0.5
            gain += tvs_boost

        # Stronger evidence tilts toward "confident answer" -> higher convergence risk
        if evidence_strength == "strong":
            gain += 0.1
        elif evidence_strength == "weak":
            gain -= 0.1

        # Phi(K) calculation (damping)
        # More sources = higher diversity = more effective damping
        damping = DAMPING_BASE + min(0.2, source_count * 0.05)

        # net_gain
        gain = max(0.0, min(COHERENCE_GAIN_MAX, gain))
        net_gain = gain - damping
        is_dangerous = gain > self.danger_threshold

        reason_parts = []
        if triggered:
            reason_parts.append(f"keywords={triggered[:3]}")
        if tvs > 0.6:
            reason_parts.append(f"high_tvs={tvs:.2f}")
        if evidence_strength == "strong":
            reason_parts.append("strong_evidence")
        reason = ", ".join(reason_parts) if reason_parts else "baseline"

        return CoherenceGainResult(
            coherence_gain   = round(gain, 3),
            damping          = round(damping, 3),
            net_gain         = round(net_gain, 3),
            is_dangerous     = is_dangerous,
            triggered_keywords = triggered,
            reason           = reason,
        )

    def coherence_gain_for(
        self,
        query:            str,
        tvs:              float = 0.5,
        evidence_strength: str  = "medium",
        source_count:     int   = 1,
    ) -> float:
        """Return coherence_gain value to pass to EAL (simple interface)"""
        return self.assess(query, tvs, evidence_strength, source_count).coherence_gain
