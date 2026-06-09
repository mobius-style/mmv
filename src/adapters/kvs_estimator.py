#!/usr/bin/env python3
"""
kvs_estimator.py — MOBIUS MMV Phase F.2: KVS Empirical Estimator
src/adapters/kvs_estimator.py

Inductively estimates TVS/MKR from audit_turns.jsonl
and updates KVSScore.computed=True.

Essay v1.3 section 5:
  TVS(q): Temporal volatility of the query (object-side)
  MKR(q,m): Model knowledge reliability (model-side)

Implementation approach:
  TVS estimation:
    - Keyword scoring (proxy for delta_E)
    - freshness_sensitive flag
    - Route statistics (classes with high verify rate -> high TVS)

  MKR estimation (inductive):
    - Essay v1.3 section 6: TVS-low yet routed to verify -> low MKR
    - Repeated eal_admissibility = bounded-only for a class -> low MKR
    - High verify_success for a class -> high MKR

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : knowledge_volatility_essay v1.3 §5-§6
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# -- TVS keyword scores -------------------------------------------------------

TVS_KEYWORD_SCORES: dict[str, float] = {
    # High volatility (high delta_E) -> high TVS
    "current":     0.8,
    "latest":      0.8,
    "today":       0.9,
    "now":         0.8,
    "recent":      0.7,
    "this week":   0.8,
    "this month":  0.7,
    "live":        0.9,
    "real-time":   0.9,
    "right now":   0.9,
    "as of":       0.7,
    "2026":        0.6,
    "2025":        0.5,
    "price":       0.7,
    "rate":        0.6,
    "yield":       0.7,
    "exchange":    0.6,
    "forecast":    0.6,
    "prediction":  0.6,
    "election":    0.6,
    "poll":        0.6,
    "breaking":    0.9,
    "update":      0.6,

    # Medium
    "last year":   0.4,
    "recently":    0.5,
    "changed":     0.4,
    "revised":     0.4,
    "appointed":   0.5,
    "resigned":    0.5,
    "announced":   0.5,
    "policy":      0.4,
    "regulation":  0.4,

    # Low volatility (low delta_E) -> low TVS (penalty)
    "history":    -0.2,
    "historical": -0.2,
    "founded":    -0.2,
    "invented":   -0.2,
    "born":       -0.2,
    "died":       -0.2,
    "established":-0.2,
    "constitution":-0.3,
    "formula":    -0.3,
    "theorem":    -0.3,
    "constant":   -0.3,
    "symbol":     -0.3,
    "definition": -0.2,
    "capital":    -0.1,
    "language":   -0.1,
}

TVS_BASE = 0.25    # Default baseline value
TVS_MIN  = 0.05
TVS_MAX  = 0.95

MKR_BASE = 0.55    # Default baseline value
MKR_MIN  = 0.10
MKR_MAX  = 0.95


@dataclass
class KVSEstimate:
    tvs:         float
    mkr:         float
    computed:    bool   = True
    tvs_basis:   str    = ""   # Estimation basis
    mkr_basis:   str    = ""   # Estimation basis
    confidence:  float  = 0.5  # Estimation confidence 0.0-1.0


@dataclass
class QueryClassStats:
    """Per-query-class statistics (used for MKR induction)"""
    query_class:      str
    total:            int   = 0
    verify_count:     int   = 0
    answer_count:     int   = 0
    bounded_count:    int   = 0   # eal_admissibility=bounded-only
    verify_success:   int   = 0   # eal_admissibility=answerable after verify
    avg_tvs:          float = 0.0

    @property
    def verify_rate(self) -> float:
        return self.verify_count / self.total if self.total > 0 else 0.0

    @property
    def mkr_signal(self) -> float:
        """
        MKR signal.
        High verify_success -> high MKR
        High bounded -> low MKR
        TVS-low yet high verify rate -> low MKR (essay v1.3 section 6)
        """
        if self.total == 0:
            return MKR_BASE
        success_rate  = self.verify_success / self.total
        bounded_rate  = self.bounded_count  / self.total
        # Low TVS yet high verify rate = low MKR signal
        low_tvs_verify_signal = (
            self.verify_rate * max(0, 0.4 - self.avg_tvs)
        )
        mkr = MKR_BASE + success_rate * 0.3 - bounded_rate * 0.2 - low_tvs_verify_signal
        return max(MKR_MIN, min(MKR_MAX, mkr))


class KVSEstimator:
    """
    Component for estimating TVS / MKR.

    TVS estimation:
      1. Keyword scoring (primary)
      2. freshness_sensitive flag
      3. Route statistics (auxiliary)

    MKR estimation (inductive):
      From accumulated data in audit_turns.jsonl,
      detects "classes that route to verify despite low TVS"
      and estimates low MKR for those classes.

    Usage:
        estimator = KVSEstimator()
        estimator.load_audit_log("logs/audit_turns.jsonl")
        estimate = estimator.estimate("What is the current rate?",
                                       freshness_sensitive=True)
        print(estimate.tvs, estimate.mkr, estimate.computed)
    """

    def __init__(self):
        self._class_stats: dict[str, QueryClassStats] = {}
        self._loaded = False

    def load_audit_log(self, path: str) -> int:
        """
        Load audit_turns.jsonl and build class statistics.

        Returns:
            Number of records loaded
        """
        log_path = Path(path)
        if not log_path.exists():
            return 0

        count = 0
        class_data: dict[str, list] = defaultdict(list)

        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Use Full Records only (skip Minimum Headers)
                if rec.get("record_type") != "turn_full":
                    continue

                route    = rec.get("route_decision", "")
                eal_adm  = rec.get("eal_admissibility", "")
                kvs      = rec.get("kvs") or {}
                tvs_val  = kvs.get("tvs", TVS_BASE)

                # Estimate query class from reason_codes
                reason_codes = rec.get("reason_codes", [])
                qclass = self._classify_query_class(reason_codes, route, tvs_val)

                class_data[qclass].append({
                    "route":   route,
                    "eal_adm": eal_adm,
                    "tvs":     tvs_val,
                })
                count += 1

        # Aggregate statistics
        for qclass, records in class_data.items():
            stats = QueryClassStats(query_class=qclass, total=len(records))
            tvs_sum = 0.0
            for rec in records:
                if rec["route"] == "verify":
                    stats.verify_count += 1
                elif rec["route"] == "answer":
                    stats.answer_count += 1
                if rec["eal_adm"] == "bounded-only":
                    stats.bounded_count += 1
                elif rec["eal_adm"] == "answerable":
                    stats.verify_success += 1
                tvs_sum += rec["tvs"]
            stats.avg_tvs = tvs_sum / len(records) if records else 0.0
            self._class_stats[qclass] = stats

        self._loaded = True
        return count

    def estimate(
        self,
        query:               str,
        freshness_sensitive: bool  = False,
        route_decision:      str   = "",
        eal_admissibility:   str   = "",
    ) -> KVSEstimate:
        """
        Estimate KVS for a query.

        Args:
            query              : Query string
            freshness_sensitive: L0 appraisal result
            route_decision     : Actual route (used as MKR signal)
            eal_admissibility  : EAL result (used as MKR signal)
        """
        # TVS estimation
        tvs, tvs_basis = self._estimate_tvs(query, freshness_sensitive)

        # MKR estimation
        mkr, mkr_basis = self._estimate_mkr(
            query, tvs, route_decision, eal_admissibility
        )

        # Confidence: higher if audit data is available
        confidence = 0.7 if self._loaded and self._class_stats else 0.4

        return KVSEstimate(
            tvs        = round(tvs, 3),
            mkr        = round(mkr, 3),
            computed   = True,
            tvs_basis  = tvs_basis,
            mkr_basis  = mkr_basis,
            confidence = confidence,
        )

    def get_tvs_low_mkr_low_quadrant(
        self, tvs_threshold: float = 0.4, mkr_threshold: float = 0.5
    ) -> list[QueryClassStats]:
        """
        Return classes in the TVS-low / MKR-low quadrant (evidence for essay v1.3 section 6).
        "Zone where facts appear stable but the model gets them wrong."
        """
        result = []
        for stats in self._class_stats.values():
            mkr_sig = stats.mkr_signal
            if stats.avg_tvs < tvs_threshold and mkr_sig < mkr_threshold:
                result.append(stats)
        return sorted(result, key=lambda s: s.mkr_signal)

    def summary(self) -> dict:
        """Return a statistics summary"""
        if not self._class_stats:
            return {"loaded": False}
        total = sum(s.total for s in self._class_stats.values())
        low_mkr = self.get_tvs_low_mkr_low_quadrant()
        return {
            "loaded":              True,
            "total_full_records":  total,
            "query_classes":       len(self._class_stats),
            "tvs_low_mkr_low":     len(low_mkr),
            "classes":             {
                k: {
                    "total":        s.total,
                    "verify_rate":  round(s.verify_rate, 2),
                    "avg_tvs":      round(s.avg_tvs, 2),
                    "mkr_signal":   round(s.mkr_signal, 2),
                }
                for k, s in sorted(
                    self._class_stats.items(),
                    key=lambda x: x[1].total, reverse=True
                )[:10]
            }
        }

    # -- Internal methods ------------------------------------------------------

    def _estimate_tvs(
        self, query: str, freshness_sensitive: bool
    ) -> tuple[float, str]:
        """Estimate TVS via keyword scoring"""
        query_lower = query.lower()
        score = TVS_BASE
        matched = []

        delta = 0.0
        for kw, kw_score in sorted(
            TVS_KEYWORD_SCORES.items(), key=lambda x: -abs(x[1])
        ):
            if kw in query_lower:
                delta += kw_score * 0.4   # dampening
                matched.append(f"{kw}({kw_score:+.1f})")
                if len(matched) >= 3:
                    break

        # Apply upper/lower bounds to delta (prevent single keyword dominance)
        delta = max(-0.20, min(0.45, delta))
        score += delta

        # freshness_sensitive flag correction
        if freshness_sensitive:
            score = max(score, 0.65)
            matched.append("freshness_sensitive")

        tvs = max(TVS_MIN, min(TVS_MAX, score))
        basis = ", ".join(matched) if matched else "base"
        return tvs, basis

    def _estimate_mkr(
        self,
        query:            str,
        tvs:              float,
        route_decision:   str,
        eal_admissibility: str,
    ) -> tuple[float, str]:
        """Estimate MKR (inductive)"""
        mkr = MKR_BASE
        basis_parts = []

        # Get MKR signal from audit statistics
        if self._loaded:
            query_lower = query.lower()
            reason_codes = []
            qclass = self._classify_query_class(reason_codes, route_decision, tvs)
            if qclass in self._class_stats:
                stats = self._class_stats[qclass]
                mkr = stats.mkr_signal
                basis_parts.append(
                    f"class={qclass}(verify_rate={stats.verify_rate:.0%})"
                )

        # TVS-low + verify -> low MKR signal (essay v1.3 section 6)
        if tvs < 0.4 and route_decision == "verify":
            penalty = (0.4 - tvs) * 0.3
            mkr -= penalty
            basis_parts.append(f"low_tvs_verify_penalty(-{penalty:.2f})")

        # EAL bounded-only -> slightly lower MKR
        if eal_admissibility == "bounded-only":
            mkr -= 0.05
            basis_parts.append("eal_bounded(-0.05)")
        elif eal_admissibility == "answerable":
            mkr += 0.05
            basis_parts.append("eal_answerable(+0.05)")

        mkr = max(MKR_MIN, min(MKR_MAX, mkr))
        basis = ", ".join(basis_parts) if basis_parts else "base"
        return mkr, basis

    def _classify_query_class(
        self, reason_codes: list, route: str, tvs: float
    ) -> str:
        """Classify a query into a class (unit for MKR statistics)"""
        # reason_codes based
        codes = set(reason_codes)
        if "FRESHNESS_SENSITIVE" in codes or "FRESHNESS" in str(codes):
            return "freshness"
        if "KVS_PASS" in codes:
            return "stable_kvs"
        if "RGC_BAND_ESCALATE_VERIFY" in codes or "VREGEN_UNSTABLE" in codes:
            return "unstable_rgc"
        if "SAFETY" in str(codes):
            return "safety"

        # route + TVS based
        if route == "verify" and tvs < 0.4:
            return "stable_verify"   # TVS-low / MKR-low candidate
        if route == "verify":
            return "freshness_verify"
        if route == "ask":
            return "clarification"
        if route == "abstain":
            return "abstain"
        return "answer_stable"
