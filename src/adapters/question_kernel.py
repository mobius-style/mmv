"""
question_kernel.py — Question Kernel (QK) selection and formatting.

Selects metacognitive QK items based on empirical fire policy
(qk_fire_policy.json) and formats them as system prompt injections.

The QK catalogue contains 42 items across 11 dimensions.
Fire policy is determined by Phase 1 pilot measurement (n=920).

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent

# ── QK Catalogue (42 items) ──────────────────────────────────────────────────

ALL_QK = [
    {"id":"QK_01","category":"intent","dimension":1,"dimension_name":"intent_alignment","priority":"high","tier":"core","applies_to_zones":["light","standard","pro"],"prompt":"Am I clearly answering the user's true underlying question or goal, or did I get stuck on a surface interpretation?"},
    {"id":"QK_02","category":"intent","dimension":1,"dimension_name":"intent_alignment","priority":"high","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"If I had to restate the user's request in one sentence, would that restatement be accurate and complete?"},
    {"id":"QK_06","category":"intent","dimension":1,"dimension_name":"intent_alignment","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Am I relying on information the user did not provide? If so, should I flag it as a guess or ask for clarification?"},
    {"id":"QK_27","category":"user_context","dimension":1,"dimension_name":"intent_alignment","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Have I taken into account any constraints the user mentioned (time, resources, skills, location), or did I ignore them?"},
    {"id":"QK_16","category":"safety","dimension":2,"dimension_name":"safety","priority":"high","tier":"core","applies_to_zones":["standard","pro"],"prompt":"Could following this answer cause harm, legal trouble, social damage, or serious negative consequences, and have I guarded against that?"},
    {"id":"QK_33","category":"safety","dimension":2,"dimension_name":"safety","priority":"high","tier":"core","applies_to_zones":["standard","pro"],"prompt":"Could my answer be misused or applied in a harmful context I have not explicitly considered?"},
    {"id":"QK_03","category":"clarity","dimension":3,"dimension_name":"clarity","priority":"high","tier":"core","applies_to_zones":["light","standard","pro"],"prompt":"Have I directly answered the main question in the first part of my response, or did I bury the answer in explanation?"},
    {"id":"QK_12","category":"scope","dimension":3,"dimension_name":"clarity","priority":"medium","tier":"core","applies_to_zones":["light","standard","pro"],"prompt":"Am I answering too broadly or too narrowly compared to what the user seems to want?"},
    {"id":"QK_13","category":"clarity","dimension":3,"dimension_name":"clarity","priority":"medium","tier":"extended","applies_to_zones":["light","standard","pro"],"prompt":"Is my explanation at an appropriate level for this user, and have I avoided unnecessary jargon or explained it when needed?"},
    {"id":"QK_14","category":"structure","dimension":3,"dimension_name":"clarity","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"If the user skimmed my answer, would the key points and takeaways still be obvious?"},
    {"id":"QK_24","category":"structure","dimension":3,"dimension_name":"clarity","priority":"medium","tier":"core","applies_to_zones":["light","standard","pro"],"prompt":"Is my answer overloaded with details, or have I chosen a small number of high-impact points to emphasize?"},
    {"id":"QK_28","category":"structure","dimension":3,"dimension_name":"clarity","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Could this answer stand on its own if the user reread it later, or does it rely too much on hidden context?"},
    {"id":"QK_29","category":"clarity","dimension":3,"dimension_name":"clarity","priority":"high","tier":"core","applies_to_zones":["light","standard","pro"],"prompt":"If I had to compress the core of my answer into one or two sentences, are those sentences already present and clear?"},
    {"id":"QK_17","category":"ethics","dimension":4,"dimension_name":"fairness","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Does my answer treat people and groups fairly, or could it reinforce harmful bias, unfair stereotypes, or exploit hidden curvature?"},
    {"id":"QK_18","category":"user_context","dimension":4,"dimension_name":"fairness","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Is my tone appropriate for the user's emotional state and topic sensitivity, or do I risk sounding dismissive, cold, or alarmist?"},
    {"id":"QK_26","category":"ethics","dimension":4,"dimension_name":"fairness","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Have I unintentionally pushed a single viewpoint as the truth, or have I fairly represented major alternative views where relevant?"},
    {"id":"QK_15","category":"next_step","dimension":5,"dimension_name":"actionability","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"If the user wants to act on this answer, do they know what to do next, or have I left them with only vague ideas?"},
    {"id":"QK_23","category":"next_step","dimension":5,"dimension_name":"actionability","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"If the user reads this answer, what is the most likely follow-up question they will have, and did I preemptively address part of it?"},
    {"id":"QK_34","category":"next_step","dimension":5,"dimension_name":"actionability","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Is there a gap between what I have explained and what the user needs to actually do something with this answer?"},
    {"id":"QK_04","category":"scope","dimension":6,"dimension_name":"cognitive_advance","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Which parts of my answer are truly necessary for this question, and which parts are off-topic or tangential?"},
    {"id":"QK_08","category":"coherence","dimension":6,"dimension_name":"cognitive_advance","priority":"medium","tier":"extended","applies_to_zones":["pro"],"prompt":"Are there important counterexamples, edge cases, or failure modes that could make my current answer misleading?"},
    {"id":"QK_30","category":"scope","dimension":6,"dimension_name":"cognitive_advance","priority":"high","tier":"core","applies_to_zones":["light","standard","pro"],"prompt":"Would adding more detail meaningfully improve the user's understanding or decision, or is this a good point to stop and keep things simple?"},
    {"id":"QK_31","category":"cognitive_advance","dimension":6,"dimension_name":"cognitive_advance","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Does my answer leave the user with meaningful thinking to do, or have I completed their reasoning for them?"},
    {"id":"QK_09","category":"clarity","dimension":7,"dimension_name":"emergence","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Is there a different framing or perspective that might help the user see the issue more clearly?"},
    {"id":"QK_21","category":"evidence","dimension":7,"dimension_name":"emergence","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Have I clearly stated the main trade-offs or limitations, instead of pretending there is a single perfect solution?"},
    {"id":"QK_22","category":"clarity","dimension":7,"dimension_name":"emergence","priority":"medium","tier":"extended","applies_to_zones":["light","standard","pro"],"prompt":"Would a short example, analogy, or concrete scenario significantly improve the user's understanding here?"},
    {"id":"QK_32","category":"emergence","dimension":7,"dimension_name":"emergence","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Does my response generate a connection, reframing, or insight that the user could not have anticipated from the question alone?"},
    {"id":"QK_05","category":"coherence","dimension":8,"dimension_name":"epistemic_integrity","priority":"high","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"What key assumptions am I silently making, and should I make any of them explicit for the user?"},
    {"id":"QK_07","category":"evidence","dimension":8,"dimension_name":"epistemic_integrity","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Which claims in my answer would benefit from explicit justification, examples, or references, and did I provide them?"},
    {"id":"QK_11","category":"safety","dimension":8,"dimension_name":"epistemic_integrity","priority":"high","tier":"core","applies_to_zones":["standard","pro"],"prompt":"Where am I at risk of sounding more certain than I should, and have I clearly indicated uncertainty where it matters?"},
    {"id":"QK_19","category":"evidence","dimension":8,"dimension_name":"epistemic_integrity","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Is any part of my answer likely to be outdated or time-sensitive, and have I signaled that to the user?"},
    {"id":"QK_25","category":"safety","dimension":8,"dimension_name":"epistemic_integrity","priority":"high","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Am I inventing specific facts (numbers, names, citations) that I cannot reliably support, and should I soften or remove them?"},
    {"id":"QK_10","category":"coherence","dimension":9,"dimension_name":"coherence","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Is my answer consistent with what has already been said in this conversation, or am I contradicting earlier content?"},
    {"id":"QK_20","category":"coherence","dimension":9,"dimension_name":"coherence","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Does my answer contain internal contradictions or tensions that I should resolve or explicitly acknowledge?"},
    # ── QK_35–40: Corpus-derived kernels (Sprint 2) ──
    {"id":"QK_35","category":"premise_validity","dimension":10,"dimension_name":"premise_validity","priority":"high","tier":"core","applies_to_zones":["standard","pro"],"prompt":"Does the user's question contain assumptions that may be incorrect or outdated, and if so, have I addressed them before answering?"},
    {"id":"QK_36","category":"epistemic_integrity","dimension":8,"dimension_name":"epistemic_integrity","priority":"medium","tier":"core","applies_to_zones":["light","standard","pro"],"prompt":"Have I calibrated my language's certainty level to match my actual confidence — hedging where genuinely uncertain and asserting only where well-supported?"},
    {"id":"QK_37","category":"epistemic_integrity","dimension":8,"dimension_name":"epistemic_integrity","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"When I state or imply a causal relationship, is it genuinely supported — or am I presenting correlation, sequence, or assumption as causation?"},
    {"id":"QK_38","category":"coherence","dimension":9,"dimension_name":"coherence","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"When I present conflicting viewpoints or information, have I made the tension illuminating — helping the user see why the disagreement matters — rather than leaving it as unresolved confusion?"},
    {"id":"QK_39","category":"cognitive_advance","dimension":6,"dimension_name":"cognitive_advance","priority":"medium","tier":"extended","applies_to_zones":["standard","pro"],"prompt":"Does my answer open a productive path forward — enabling the user to go deeper, explore a related angle, or question an assumption — rather than dead-ending the conversation?"},
    {"id":"QK_40","category":"epistemic_integrity","dimension":8,"dimension_name":"epistemic_integrity","priority":"medium","tier":"core","applies_to_zones":["standard","pro"],"prompt":"Have I provided adequate justification for my key claims, or am I asking the user to accept conclusions without visible reasoning?"},
    # ── QK_41: Box A behavioral compliance (fires only when Box A RULE/CRITERIA mode active) ──
    {"id":"QK_41","category":"behavioral_compliance","dimension":11,"dimension_name":"rule_compliance","priority":"high","tier":"context_dependent","applies_to_zones":["light","standard","pro"],"prompt":"Have I followed the operational rules from the user's reference document as behavioral constraints, or have I merely described or cited them? If the document says 'respond with one word' and I wrote a paragraph, I have violated the rule."},
    # ── QK_42: Creative Presentation Mode (fires only for creative_request intent) ──
    {"id":"QK_42","category":"clarity","dimension":3,"dimension_name":"clarity","priority":"high","tier":"always_fire","applies_to_zones":["light","standard","pro"],"prompt":"When the intent is creative or exploratory, have I integrated retrieved knowledge naturally into the response rather than presenting it in citation format? Wikipedia citation markers, source attributions, academic reference styles, and bracketed source tags break the flow of creative context. Use the knowledge. Dissolve the presentation."},
]

QK_MAP = {qk["id"]: qk for qk in ALL_QK}

# ── Load fire policy ─────────────────────────────────────────────────────────

_POLICY_PATH = ROOT / "data" / "measurement" / "qk_fire_policy.json"
_POLICY = {}
if _POLICY_PATH.exists():
    with open(_POLICY_PATH, encoding="utf-8") as f:
        _POLICY = json.load(f)

_ALWAYS_FIRE = set(_POLICY.get("always_fire", []))
_CONTEXT_DEP = set(_POLICY.get("context_dependent", []))
_SUPPRESSED  = set(_POLICY.get("suppress_default", []))
_ZONE_OVERRIDE = _POLICY.get("zone_override", {})

# ── Intent-to-zone mapping ───────────────────────────────────────────────────

INTENT_TO_ZONE = {
    "casual_greeting": "light",
    "game_move": "light",
    "creative_request": "light",
    "factual_query": "standard",
    "translation_request": "standard",
    "instruction_request": "standard",
    "topic_continuation": "standard",
    "clarification": "standard",
    "correction": "pro",
    "meta_question": "pro",
}

INTENT_TO_CATEGORY = {
    "factual_query":       ["intent", "evidence", "scope"],
    "casual_greeting":     ["intent", "clarity"],
    "correction":          ["intent", "coherence", "evidence"],
    "meta_question":       ["evidence", "ethics", "scope"],
    "creative_request":    ["clarity", "next_step"],
    "translation_request": ["intent", "clarity", "user_context"],
    "instruction_request": ["intent", "structure", "next_step"],
    "topic_continuation":  ["coherence", "scope", "clarity"],
    "clarification":       ["intent", "scope", "user_context"],
    "game_move":           ["intent", "clarity"],
}


# ── Public API ───────────────────────────────────────────────────────────────

def get_zone_for_intent(intent_type: str) -> str:
    return INTENT_TO_ZONE.get(intent_type, "standard")


def select_kernels(
    intent_type: str,
    zone: str | None = None,
    route: str = "answer",
    max_items: int | None = None,
) -> list[dict]:
    """ISM-integrated QK selection — 3-layer filter."""
    if route in ("abstain", "ask"):
        return []

    if zone is None:
        zone = get_zone_for_intent(intent_type)

    ism = _POLICY.get("ism_integration", {})
    suppress_map = ism.get("intent_suppress", {})
    tier_corrections = ism.get("tier_corrections", {})

    # Layer 1: translation_request override (zone-independent)
    tr_override = ism.get("translation_request_override", {})
    if intent_type == "translation_request" and tr_override.get("zone_independent"):
        override_ids = set(tr_override.get("active_qks", []))
        return [qk for qk in ALL_QK if qk["id"] in override_ids]

    # Layer 2: always_fire + intent_suppress filter
    candidates = []
    for qk in ALL_QK:
        qk_id = qk["id"]

        if qk_id not in _ALWAYS_FIRE:
            continue
        if qk_id in _SUPPRESSED:
            continue
        if intent_type in suppress_map.get(qk_id, []):
            continue

        # Check zone override
        if qk_id in _ZONE_OVERRIDE:
            if zone not in _ZONE_OVERRIDE[qk_id]:
                continue

        if zone not in qk["applies_to_zones"]:
            continue

        candidates.append(qk)

    # Layer 3: pro zone adds context_dependent (with tier_corrections)
    if zone == "pro":
        for qk in ALL_QK:
            qk_id = qk["id"]
            if qk_id not in _CONTEXT_DEP:
                continue
            if qk_id in _SUPPRESSED:
                continue
            if zone not in qk["applies_to_zones"]:
                continue
            if intent_type in suppress_map.get(qk_id, []):
                continue

            # Tier corrections: QK_09 etc. only fire for specific intents
            correction = tier_corrections.get(qk_id)
            if correction:
                if intent_type not in correction.get("effective_intents", []):
                    continue

            candidates.append(qk)

    if max_items is not None:
        candidates = candidates[:max_items]

    return candidates


def format_kernel_block(kernels: list[dict]) -> str:
    """Format selected QKs as system prompt injection block."""
    if not kernels:
        return ""

    lines = [
        "[INTERNAL METACOGNITIVE CHECK — do not mention to user]",
        "Before generating your response, silently verify:",
    ]
    for i, k in enumerate(kernels, 1):
        lines.append(f"{i}. {k['prompt']}")

    return "\n".join(lines)
