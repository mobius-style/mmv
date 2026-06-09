"""
prompt_builder.py — MOBIUS governance prompt injection.

Provides structured governance instructions for LLM prompts.
Used by app.py for RAW mode and by the compose layer for MOBIUS mode.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

FORBIDDEN_PATTERNS = """
FORBIDDEN output patterns — never use these:
- Any phrase equivalent to "If you can share more context..."
- Any phrase equivalent to "There may be an unstated assumption here..."
- Any phrase equivalent to "This answer assumes the most common interpretation..."
- Any self-explanation of MOBIUS architecture or design principles
  (unless the query is explicitly self-referential about MOBIUS)
- Any mention of TVS, MKR, KVS, EAL, or admissibility
  in the user-facing response body
  (these are internal governance parameters, not content)
"""

KVS_GOVERNANCE_TEMPLATE = """
Response governance parameters (internal — do not mention in output):
  TVS (Temporal Volatility Score) = {tvs:.2f}
    Range: 0.0 (timeless) to 1.0 (changes daily)
    Rule: TVS >= 0.6 → use conditional grammar only
          TVS < 0.3 and MKR > 0.5 → direct answer permitted

  MKR (Model Knowledge Reliability) = {mkr:.2f}
    Range: 0.0 (unreliable) to 1.0 (fully reliable for this query class)
    Rule: MKR < 0.5 → do not rely on model knowledge alone

  KVS Gate: direct factual commitment requires BOTH:
    TVS < {tvs_threshold:.1f}  [current: {tvs_pass}]
    MKR > {mkr_threshold:.1f}  [current: {mkr_pass}]
    Gate: {gate_result}
"""

HALFSTEP_GOVERNANCE_TEMPLATE = """
HalfStep principle (constitutional rule — apply to this response):
  Selected type: {kind}
  Conceptual distance: exactly 1 unit
  Mathematical basis: the system performs the twist;
                      the leap belongs to the user

  RULE: Do NOT append HalfStep as a separate sentence at the end.
  RULE: Embed it within the answer structure itself.
"""


def build_raw_mode_instruction(explore_on: bool) -> str:
    """
    Build governance instruction for MOBIUS OFF (RAW LLM) mode.
    TVS/MKR are not available; use structural rules only.
    """
    base = FORBIDDEN_PATTERNS.strip()
    if explore_on:
        return (
            f"{base}\n\n"
            "Mode: Explore (thinking enabled).\n"
            "Think step by step. Show your reasoning process.\n"
            "After reasoning, provide a clear answer."
        )
    return (
        f"{base}\n\n"
        "Mode: Direct answer.\n"
        "Answer concisely and accurately.\n"
        "Do not add unnecessary caveats or meta-commentary."
    )


def build_kvs_block(
    tvs: float,
    mkr: float,
    tvs_threshold: float = 0.6,
    mkr_threshold: float = 0.5,
) -> str:
    """Format KVS governance block with computed values."""
    tvs_pass = "PASS" if tvs < tvs_threshold else "FAIL"
    mkr_pass = "PASS" if mkr > mkr_threshold else "FAIL"
    gate_result = "OPEN (direct answer)" if tvs_pass == "PASS" and mkr_pass == "PASS" else "CLOSED (bounded only)"
    return KVS_GOVERNANCE_TEMPLATE.format(
        tvs=tvs, mkr=mkr,
        tvs_threshold=tvs_threshold, mkr_threshold=mkr_threshold,
        tvs_pass=tvs_pass, mkr_pass=mkr_pass,
        gate_result=gate_result,
    )


def build_halfstep_block(kind: str) -> str:
    """Format HalfStep governance block with selected kind."""
    return HALFSTEP_GOVERNANCE_TEMPLATE.format(kind=kind)
