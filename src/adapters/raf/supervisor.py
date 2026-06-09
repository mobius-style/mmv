"""
supervisor.py — Wall-ball session supervisor (AIOS 2.6.3 lineage)

OBJ = a*(1-verify_failed_rate) + b*(1-user_correction_rate)
    + g*intent_accuracy + d*wiki_hit_rate - l*conv_override_error

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations
import json
from pathlib import Path

NOVELTY_THRESHOLD   = 0.05
CONVERGENCE_CYCLES  = 3
BATCH_SIZE          = 100
OVERFIT_THRESHOLD   = 0.40


def check_convergence(stats_path: str) -> bool:
    """Check if novelty_rate < threshold for N consecutive cycles."""
    try:
        with open(stats_path) as f:
            stats = json.load(f)
        recent = stats.get("novelty_history", [])[-CONVERGENCE_CYCLES:]
        if len(recent) < CONVERGENCE_CYCLES:
            return False
        return all(r < NOVELTY_THRESHOLD for r in recent)
    except Exception:
        return False


def check_overfit(labels: list[dict]) -> dict[str, float]:
    """Return intent_type distribution. Flag any > OVERFIT_THRESHOLD."""
    from collections import Counter
    if not labels:
        return {}
    counts = Counter(l.get("intent_type", "unknown") for l in labels)
    total = sum(counts.values())
    dist = {k: v / total for k, v in counts.items()}
    return dist


def get_suppressed_topics(dist: dict[str, float]) -> list[str]:
    """Return intent_types that exceed OVERFIT_THRESHOLD."""
    return [k for k, v in dist.items() if v > OVERFIT_THRESHOLD]
