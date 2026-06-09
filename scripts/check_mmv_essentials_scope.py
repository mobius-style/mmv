#!/usr/bin/env python3
"""Check the observed scope of L0 Essentials in the current workspace.

This is intentionally a metadata/code-path check, not a model call:
- Condition I records L0 Essentials as a qwen 9B / structural-governance
  experiment.
- Current Small RC3.3 uses the 9B mobius_engine path plus a Small Routing
  Stabilizer, but current policy warns not to stack Essentials injection onto
  that structural governance path without a new evaluation.
- Current Medium/Large profiles use the route-transformer / post-validator
  path and do not reference L0 Essentials.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE_YAML = ROOT / "operate-fr-bench" / "configs" / "model_profiles.example.yaml"
CLAUDE = ROOT / "CLAUDE.md"
COND_I = ROOT / "data" / "evaluation" / "eval_v8_essentials_v1_2_500q_cond_I_summary.md"

SMALL_PROFILE = "mmv_small_rc3_3_stabilized"
MEDIUM_PROFILE = "gemma4_26b_route_transformer_plus_validator_v3_1"
LARGE_PROFILE = "120b_route_transformer_plus_validator_v3_1"

ESSENTIALS_TOKENS = (
    "L0_Essentials",
    "Essentials",
    "L0 Essentials",
    "answer_entitlement_essentials",
)


def _profile_block(name: str) -> str:
    text = PROFILE_YAML.read_text(encoding="utf-8")
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  \S|\Z)", text)
    return match.group(1) if match else ""


def _contains_essentials(text: str) -> bool:
    return any(token in text for token in ESSENTIALS_TOKENS)


def main() -> int:
    small = _profile_block(SMALL_PROFILE)
    medium = _profile_block(MEDIUM_PROFILE)
    large = _profile_block(LARGE_PROFILE)
    claude_text = CLAUDE.read_text(encoding="utf-8")
    cond_i_text = COND_I.read_text(encoding="utf-8") if COND_I.exists() else ""

    checks = [
        (
            "Condition I records Essentials on qwen 9B structural governance",
            "qwen 9B + Structural Governance + L0 Essentials" in cond_i_text,
        ),
        (
            "Current policy warns not to stack Essentials with structural governance",
            "Do not combine L0 Essentials prompt injection with v2.1 structural governance"
            in claude_text,
        ),
        (
            "Small RC3.3 is the 9B mobius_engine path",
            "backend: mobius_engine" in small and "model_id: qwen3.5:9b" in small,
        ),
        (
            "Small RC3.3 has Small Routing Stabilizer enabled",
            "small_routing_stabilizer: true" in small,
        ),
        (
            "Small RC3.3 profile does not directly inject Essentials",
            bool(small) and not _contains_essentials(small),
        ),
        (
            "Large RC3.3 profile does not reference Essentials",
            bool(large) and not _contains_essentials(large),
        ),
        (
            "Medium RC3.3 profile does not reference Essentials",
            bool(medium) and not _contains_essentials(medium),
        ),
    ]

    ok = True
    for label, passed in checks:
        mark = "OK" if passed else "FAIL"
        print(f"[{mark}] {label}")
        ok = ok and passed

    print()
    print("Interpretation:")
    print("- Essentials was evaluated as a qwen 9B / Small-line injection experiment.")
    print("- Current Small RC3.3 does not directly inject it; it uses structural governance + stabilizer.")
    print("- Current Medium/Large RC profiles do not reference Essentials.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
