"""
diversity_guard.py — Overfit guard (AIOS 2.6.3 lineage)

Suppresses topics that exceed OVERFIT_THRESHOLD (0.40).

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

OVERFIT_THRESHOLD = 0.40


def should_suppress(intent_type: str, distribution: dict[str, float]) -> bool:
    """Return True if this intent_type exceeds the threshold."""
    return distribution.get(intent_type, 0.0) > OVERFIT_THRESHOLD


def select_topic(language: str, topics: list[str],
                 suppressed: list[str], rng=None) -> str:
    """Select a topic, avoiding suppressed ones."""
    import random
    _rng = rng or random
    available = [t for t in topics if t not in suppressed]
    if not available:
        available = topics
    return _rng.choice(available)
