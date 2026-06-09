"""
schema.py — ISM + QK integrated data schema

Theoretical basis:
  formal_type  : Question form layer (QK corpus, 7 types)
  intent_type  : Question intent layer (ISM, 10 types)
  qk_*         : Question entitlement layer (QK)

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List

FORMAL_TYPES = [
    "yesno", "what", "how", "why", "selection", "comparison", "other",
]

INTENT_TYPES = [
    "factual_query", "game_move", "topic_continuation",
    "translation_request", "correction", "meta_question",
    "casual_greeting", "creative_request", "instruction_request",
    "clarification",
]

QK_ENTITLEMENT = ["answerable", "verify", "abstain"]
QK_TVS_LEVELS  = ["low", "medium", "high"]
QK_MKR_RISK    = ["low", "medium", "high"]
QK_HALFSTEP    = [
    "hidden_assumption", "adjacent_contrast",
    "missing_constraint", "teaching_scaffold", "none",
]


@dataclass
class TeacherLabel:
    id: str
    created_at: str
    language: str
    query: str
    context: str
    formal_type: str
    intent_type: str
    response_type: str
    wiki_lookup: bool
    conv_override: bool
    qk_entitlement: str
    qk_tvs_estimate: str
    qk_mkr_risk: str
    qk_halfstep_type: str
    qk_reanchor_needed: bool
    confidence: float
    source: str
    tier: int


@dataclass
class RawLog:
    id: str
    created_at: str
    session_id: str
    language: str
    topic: str
    context_turns: list
    query: str
    worker_port: int
    tier1_pass: bool
    tier2_score: float
    tier2_raw: str
    tier3_label: dict
    tier3_raw: str
    groq_model: str
    groq_latency_ms: float
    groq_tokens: int


@dataclass
class ISMState:
    intent_type: str = "factual_query"
    formal_type: str = "what"
    response_type: str = "direct_answer"
    halfstep_type: Optional[str] = None
    wiki_lookup: bool = True
    explanation_needed: bool = True
    conv_override: bool = False
    qk_entitlement: str = "answerable"
    qk_tvs_estimate: str = "low"
    confidence: float = 0.0
    source: str = "default"
    neighbor_count: int = 0
