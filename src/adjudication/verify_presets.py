"""
verify_presets.py — Lightweight presets for MMV Verify.

Presets change: max_results, boundedness bias, freshness weight, tone.
Presets do NOT change: constitutional routing, admissibility structure,
ask-before-verify, retrieval failure policy.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VerifyPreset:
    name: str
    max_results: int
    freshness_weight: str      # "high" | "normal"
    provenance_weight: str     # "high" | "normal"
    boundedness: str           # "strict" | "normal"
    tone_note: str             # injected into synthesis prompt


PRESETS: dict[str, VerifyPreset] = {
    "general": VerifyPreset(
        name="general",
        max_results=5,
        freshness_weight="normal",
        provenance_weight="normal",
        boundedness="normal",
        tone_note="",
    ),
    "policy": VerifyPreset(
        name="policy",
        max_results=7,
        freshness_weight="high",
        provenance_weight="high",
        boundedness="normal",
        tone_note=(
            "This is a policy or institutional query. "
            "Prefer official or authoritative sources. "
            "Note if any policy change appears recent."
        ),
    ),
    "legal": VerifyPreset(
        name="legal",
        max_results=5,
        freshness_weight="high",
        provenance_weight="high",
        boundedness="strict",
        tone_note=(
            "This is a legal or compliance query. "
            "Apply strict boundedness: do not go beyond what the sources clearly state. "
            "Always note that this is not legal advice."
        ),
    ),
    "educational": VerifyPreset(
        name="educational",
        max_results=5,
        freshness_weight="normal",
        provenance_weight="normal",
        boundedness="normal",
        tone_note=(
            "This is an educational or reflective query. "
            "Explain clearly and avoid jargon where possible. "
            "If the answer is uncertain, say so explicitly and invite follow-up."
        ),
    ),
}


def get_preset(name: str) -> VerifyPreset:
    return PRESETS.get(name, PRESETS["general"])
