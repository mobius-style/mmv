#!/usr/bin/env python3
"""
audit_schema.py — MOBIUS MMV Phase D: Audit Log Schema
src/audit/audit_schema.py

Audit schema and dataclass definitions. Immutable core (Principle B: minimum trace).
Change with caution.

Phase D implementation (phase_d_audit_spec.docx §4, Appendix A/B/C):
  - FullTurnAuditRecord (2-layer structure: Minimum Header + Full fields)
  - QKSnapshot (QK decision bucket)
  - DecisionTrace (short decision summary)
  - SessionTraceSummary (one record at session end)
  - IncidentRecord (anomalies only)

KVS integration (eal.py / knowledge_volatility essay):
  - Added kvs field to FullTurnAuditRecord (Phase D addition)
  - When KVSScore.computed=True, actual TVS/MKR values flow in

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : phase_d_audit_spec.docx §4, §8, Appendix A/B/C
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ── Version constants ─────────────────────────────────────────────────────────
# Appendix B: policy_version format
# Format: mmv-{semver}-{phase_tag}
POLICY_VERSION  = "mmv-v7.5.0-phase_d_qk21"   # QK v2.1 dual-pass
RUNTIME_BUILD   = "phase_d_dev"           # git short hash (replaced in production)

# ── audit_mode constants ─────────────────────────────────────────────────────
AUDIT_MODE_OFF           = "off"
AUDIT_MODE_SHADOW        = "shadow"
AUDIT_MODE_FULL          = "full"
AUDIT_MODE_INCIDENT_ONLY = "incident_only"

# ── record_type constants ────────────────────────────────────────────────────
RECORD_TYPE_HEADER    = "header"
RECORD_TYPE_TURN_FULL = "turn_full"

# ── QK bucket conversion thresholds (spec §4.2) ───────────────────────────────
QK_INTENT_LOW_THRESHOLD  = 0.40
QK_INTENT_HIGH_THRESHOLD = 0.70
QK_UNCERTAINTY_HIGH      = 0.70   # uncertainty >= 0.70 -> risk=low (inverted)
QK_UNCERTAINTY_LOW       = 0.30   # uncertainty < 0.30 -> risk=high


# ── Utilities ──────────────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def _sha256(text: str) -> str:
    """Record only SHA-256 hash without storing raw text (Principle B)"""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# ── QKSnapshot ──────────────────────────────────────────────────────────────

@dataclass
class QKSnapshot:
    """
    Question Kernel decision bucket (spec §4.2).

    Raw E_sem is not needed. Buckets alone provide sufficient audit value.
    Central to explaining "what was lacking that caused the shift to ask/verify/abstain".

    Attributes:
        intent     : Converted from intent_clarity score (low|ok|high)
        risk       : Converted from uncertainty score (inverted) (low|ok|high)
        longterm   : Future impact level (low|ok|high) -- Phase D placeholder
        meta_frame : Converted from safety_relevant (low|ok|high)
    """
    intent:     str = "ok"   # low|ok|high
    risk:       str = "ok"   # low|ok|high
    longterm:   str = "ok"   # low|ok|high  (Phase D: placeholder)
    meta_frame: str = "ok"   # low|ok|high

    @classmethod
    def from_appraisal(
        cls,
        intent_clarity:    float,
        uncertainty:       float,
        freshness_sensitive: bool,
        safety_relevant:   bool,
    ) -> "QKSnapshot":
        """
        Generate QKSnapshot from appraisal.py scores.
        Follows bucket conversion rules in spec §4.2.
        """
        # intent_clarity -> intent
        if intent_clarity < QK_INTENT_LOW_THRESHOLD:
            intent = "low"
        elif intent_clarity >= QK_INTENT_HIGH_THRESHOLD:
            intent = "high"
        else:
            intent = "ok"

        # uncertainty -> risk (inverted)
        if uncertainty >= QK_UNCERTAINTY_HIGH:
            risk = "low"
        elif uncertainty < QK_UNCERTAINTY_LOW:
            risk = "high"
        else:
            risk = "ok"

        # freshness_sensitive -> risk override
        if freshness_sensitive:
            risk = "high"

        # safety_relevant -> meta_frame override
        meta_frame = "high" if safety_relevant else "low"

        return cls(
            intent     = intent,
            risk       = risk,
            longterm   = "ok",   # Phase D: placeholder
            meta_frame = meta_frame,
        )


# ── DecisionTrace ───────────────────────────────────────────────────────────

@dataclass
class DecisionTrace:
    """
    Short decision summary (spec §4.3).

    Records only which decisions were effective, not the full text.
    Provides very strong audit value when reviewed later.

    Attributes:
        primary_reason  : Primary cause (reason code string)
        primary_seat    : Source of primary cause (supervisor|oracle|auditor|kernel)
        secondary_reason: Secondary cause
        secondary_seat  : Source of secondary cause
        notes           : Supplementary notes e.g. ["verify_required", "oracle_throttled"]
    """
    primary_reason:   str
    primary_seat:     str        # supervisor|oracle|auditor|kernel
    secondary_reason: str  = ""
    secondary_seat:   str  = ""
    notes:            list = field(default_factory=list)


# ── KVSScore (EAL integration) ───────────────────────────────────────────────

@dataclass
class KVSScoreRecord:
    """
    Audit record copy of Knowledge Volatility Score.

    Type for embedding eal.py's KVSScore into the audit log.
    When computed=True in Phase D, actual TVS/MKR values are populated.

    Refs: knowledge_volatility_future_fantasism_essay §5
    """
    tvs:      float = 0.5    # Temporal Volatility Score (0.0-1.0)
    mkr:      float = 0.5    # Model Knowledge Reliability (0.0-1.0)
    computed: bool  = False  # False=stub, True=actual measured value


# ── FullTurnAuditRecord ──────────────────────────────────────────────────────

@dataclass
class FullTurnAuditRecord:
    """
    Turn Audit Record (2-layer structure) (spec §4.1 / Appendix A).

    Integrates Minimum Header fields (required every turn, not subject to sampling)
    and Full fields (subject to sampling) into a single class.
    Distinguished by record_type (spec §8).

    Raw text is not stored (Principle B). SHA-256 hash only.
    """

    # ── Minimum Header fields (required every turn) ────────────────────────────
    turn_id:         str   = ""         # UUID
    session_id:      str   = ""         # UUID
    timestamp_utc:   str   = ""         # ISO 8601
    turn:            int   = 0          # Turn number
    route_decision:  str   = "answer"   # answer|ask|verify|abstain
    audit_mode:      str   = AUDIT_MODE_SHADOW
    sampled:         bool  = False
    record_type:     str   = RECORD_TYPE_HEADER  # header|turn_full

    # ── Full fields (meaningful only when sampled=True) ────────────────────────
    user_input_hash:         str  = ""
    requested_config:        dict = field(default_factory=dict)
    effective_config:        dict = field(default_factory=dict)
    clamped:                 bool = False
    clamp_reasons:           list = field(default_factory=list)
    reason_codes:            list = field(default_factory=list)
    oracle_used:             bool = False
    oracle_level_effective:  str  = ""
    micro_auditor_decision:  str  = ""
    output_hash:             str  = ""
    policy_version:          str  = POLICY_VERSION
    runtime_build:           str  = RUNTIME_BUILD
    latency_ms:              dict = field(default_factory=dict)
    qk:                      Optional[QKSnapshot]    = None
    decision_trace:          Optional[DecisionTrace] = None
    meta_note_available:     bool = False
    capability_status:       str  = "supported"

    # ── Phase D addition: EAL / KVS integration ─────────────────────────────────
    kvs:              Optional[KVSScoreRecord] = None   # TVS/MKR
    eal_admissibility: str = ""   # answerable|bounded-only|verify-failed

    # ── Retrieval info (Phase C integration) ──────────────────────────────────
    retrieval_source: str  = ""   # A|B|C|B+C|none
    retrieval_score:  float = 0.0

    # ── QK v2.1 fields (dual-pass Question Kernel) ──────────────────────────
    qk_fired:         list  = field(default_factory=list)
    qk_zone:          str   = ""
    qk_count:         int   = 0
    qk_passes:        int   = 0
    qk_mode:          str   = ""   # single_pass / pipeline
    pass1_latency_ms: float = 0.0
    pass2_latency_ms: float = 0.0

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = _now_utc()
        if not self.turn_id:
            import uuid
            self.turn_id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL output"""
        import dataclasses
        d = dataclasses.asdict(self)
        # Remove None values (Full fields are None in Minimum Header)
        return {k: v for k, v in d.items() if v is not None}

    @staticmethod
    def hash_text(text: str) -> str:
        return _sha256(text)


# ── SessionTraceSummary ─────────────────────────────────────────────────────

@dataclass
class SessionTraceSummary:
    """
    Generated once at session end (spec §4.4).

    An at-a-glance summary of "what kind of conversation this was".
    Lightweight to implement yet highly useful.
    """
    session_id:           str   = ""
    timestamp_utc:        str   = ""
    turn_count:           int   = 0
    clamp_count:          int   = 0
    verify_count:         int   = 0
    ask_count:            int   = 0
    oracle_count:         int   = 0
    dominant_reason_codes: list = field(default_factory=list)
    final_risk_posture:   str   = ""
    calibration_events:   int   = 0
    phi_t_final:          float = 0.0   # phi_t of the final turn
    audit_mode:           str   = AUDIT_MODE_SHADOW
    record_type:          str   = "session_summary"

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = _now_utc()

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# ── IncidentRecord ──────────────────────────────────────────────────────────

@dataclass
class IncidentRecord:
    """
    Generated only during anomalies (spec §4.5).

    Stored separately only for routing failures, unexpected clamps, and model errors.
    Full ReproPack items are not included here (reference pointer only).
    """
    incident_id:          str   = ""
    session_id:           str   = ""
    timestamp_utc:        str   = ""
    turn:                 int   = 0
    expected_route:       str   = ""
    actual_route:         str   = ""
    failure_type:         str   = ""
    correction_applied:   bool  = False
    rollback_id:          Optional[str] = None
    repro_pack_pointer:   Optional[str] = None   # Extended in Phase E
    phi_t_at_incident:    float = 0.0
    record_type:          str   = "incident"

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = _now_utc()
        if not self.incident_id:
            import uuid
            self.incident_id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def should_emit(
        cls,
        expected_route:  str,
        actual_route:    str,
        clamp_reasons:   list,
        phi_t:           float,
        phi_t_prev:      float,
        has_exception:   bool,
    ) -> bool:
        """
        Trigger conditions for Incident Record (spec §4.5).

        Returns True if one or more of the following are true:
          - expected_route != actual_route
          - SAFETY_CRITICAL / POLICY_VIOLATION present in clamp_reasons
          - RuntimeError / Exception occurred and fallback was triggered
          - phi_t > 0.90 and route in {ask, abstain}
          - phi_t > 0.90 sustained for 2 or more consecutive turns
        """
        if expected_route != actual_route:
            return True
        critical = {"SAFETY_CRITICAL", "POLICY_VIOLATION"}
        if any(r in critical for r in clamp_reasons):
            return True
        if has_exception:
            return True
        if phi_t > 0.90 and actual_route in ("ask", "abstain"):
            return True
        if phi_t > 0.90 and phi_t_prev > 0.90:
            return True
        return False
