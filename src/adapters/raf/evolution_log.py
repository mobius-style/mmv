"""
evolution_log.py — EAL feedback structured log

EAL_REWARD_MAP:
  answerable:       +1.0
  bounded-only:      0.0
  verify-failed:    -1.0
  user_correction:  -2.0

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

EAL_REWARD_MAP = {
    "answerable":      1.0,
    "bounded-only":    0.0,
    "verify-failed":  -1.0,
    "user_correction": -2.0,
}


def record_feedback(
    log_path: str,
    query: str,
    intent_type: str,
    eal_result: str,
    ism_confidence: float,
) -> None:
    """Append one feedback record to the evolution log."""
    reward = EAL_REWARD_MAP.get(eal_result, 0.0)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query[:200],
        "intent_type": intent_type,
        "eal_result": eal_result,
        "reward": reward,
        "ism_confidence": round(ism_confidence, 3),
    }
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
