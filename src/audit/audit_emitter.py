#!/usr/bin/env python3
"""
audit_emitter.py — MOBIUS MMV Phase D: Audit Emitter
src/audit/audit_emitter.py

The single entry point called from Layer 1 (Model Adapter) (spec §3).
Three methods: emit_turn_record() / emit_session_summary() / emit_incident().

Only two hook insertions into routing_engine.py (spec §7.2):
  # Hook 1: emit_minimum_header (required every turn)
  # Hook 2: emit_turn_record (subject to sampling)

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : phase_d_audit_spec.docx §3, §4, §7
"""

from __future__ import annotations

import collections
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from audit_schema import (
    AUDIT_MODE_SHADOW,
    POLICY_VERSION,
    RECORD_TYPE_HEADER,
    RECORD_TYPE_TURN_FULL,
    DecisionTrace,
    FullTurnAuditRecord,
    IncidentRecord,
    KVSScoreRecord,
    QKSnapshot,
    SessionTraceSummary,
)
from audit_sampler import AuditSampler
from audit_store import AuditStore

logger = logging.getLogger(__name__)


class AuditEmitter:
    """
    The single entry point for audit emit. Just call from Layer 1. No knowledge of internal implementation.

    Usage:
        emitter = AuditEmitter(
            store   = AuditStore("logs"),
            sampler = AuditSampler(audit_mode="shadow"),
        )
        emitter.open()

        # routing_engine.py Hook 1 (required every turn)
        emitter.emit_minimum_header(
            session_id     = state.session_id,
            turn           = state.turn,
            route_decision = decision.route,
        )

        # routing_engine.py Hook 2 (subject to sampling)
        emitter.emit_turn_record(
            session_id     = state.session_id,
            turn           = state.turn,
            route_decision = decision.route,
            user_input     = query,     # stored as hash only
            output_text    = response,  # stored as hash only
            ...
        )

        # At session end
        emitter.emit_session_summary(session_id)

        emitter.close()
    """

    def __init__(
        self,
        store:      Optional[AuditStore]   = None,
        sampler:    Optional[AuditSampler] = None,
        audit_mode: str = AUDIT_MODE_SHADOW,
        log_dir:    str = "logs",
    ):
        self._store   = store   or AuditStore(log_dir)
        self._sampler = sampler or AuditSampler(audit_mode=audit_mode)
        self.audit_mode = audit_mode
        self._open    = False

    # ── Lifecycle ────────────────────────────────────────────────────────

    def open(self) -> None:
        self._store.open()
        self._open = True
        logger.info(f"[AuditEmitter] Ready. mode={self.audit_mode}")

    def close(self) -> None:
        self._store.close()
        self._open = False

    def start_session(self, session_id: str) -> None:
        self._sampler.start_session(session_id)

    # ── emit_minimum_header (required every turn, not subject to sampling) ──

    def emit_minimum_header(
        self,
        session_id:     str,
        turn:           int,
        route_decision: str,
        turn_id:        Optional[str] = None,
    ) -> str:
        """
        Emit a Minimum Header every turn unconditionally (not subject to sampling).
        Guarantees that the existence of the turn itself is never lost (spec §4.1a).

        Returns:
            turn_id (reused in subsequent emit_turn_record calls)
        """
        tid = turn_id or str(uuid.uuid4())
        record = FullTurnAuditRecord(
            turn_id        = tid,
            session_id     = session_id,
            turn           = turn,
            route_decision = route_decision,
            audit_mode     = self.audit_mode,
            sampled        = False,
            record_type    = RECORD_TYPE_HEADER,
        )
        if self._open:
            self._store.enqueue(record)
        return tid

    # ── emit_turn_record (subject to sampling) ─────────────────────────────

    def emit_turn_record(
        self,
        session_id:      str,
        turn:            int,
        route_decision:  str,
        user_input:      str          = "",
        output_text:     str          = "",
        requested_config: dict        = None,
        effective_config: dict        = None,
        clamped:         bool         = False,
        clamp_reasons:   list         = None,
        reason_codes:    list         = None,
        oracle_used:     bool         = False,
        oracle_level:    str          = "",
        micro_decision:  str          = "",
        appraisal_ms:    int          = 0,
        generation_ms:   int          = 0,
        total_ms:        int          = 0,
        qk:              Optional[QKSnapshot]    = None,
        decision_trace:  Optional[DecisionTrace] = None,
        kvs:             Optional[KVSScoreRecord] = None,
        eal_admissibility: str        = "",
        retrieval_source: str         = "",
        retrieval_score: float        = 0.0,
        phi_t:           float        = 0.0,
        turn_id:         Optional[str] = None,
    ) -> Optional[str]:
        """
        Emit a Full Turn Audit Record (subject to sampling).

        Performs sampling decision internally; does nothing if should_record=False.
        Raw text (user_input / output_text) is stored as SHA-256 hash only.

        Returns:
            turn_id if recorded, None if skipped
        """
        # Update sampler state
        self._sampler.update(
            route_decision = route_decision,
            clamped        = clamped,
            phi_t          = phi_t,
            oracle_used    = oracle_used,
            reason_codes   = reason_codes or [],
        )

        # Sampling decision
        if not self._sampler.should_record(
            route_decision = route_decision,
            clamped        = clamped,
            clamp_reasons  = clamp_reasons or [],
            phi_t          = phi_t,
        ):
            return None

        t_emit_start = time.time()
        tid = turn_id or str(uuid.uuid4())

        record = FullTurnAuditRecord(
            turn_id                = tid,
            session_id             = session_id,
            turn                   = turn,
            route_decision         = route_decision,
            audit_mode             = self.audit_mode,
            sampled                = True,
            record_type            = RECORD_TYPE_TURN_FULL,
            # Raw text stored as hash only (Principle B)
            user_input_hash        = FullTurnAuditRecord.hash_text(user_input),
            output_hash            = FullTurnAuditRecord.hash_text(output_text),
            requested_config       = requested_config or {},
            effective_config       = effective_config or {},
            clamped                = clamped,
            clamp_reasons          = clamp_reasons or [],
            reason_codes           = reason_codes or [],
            oracle_used            = oracle_used,
            oracle_level_effective = oracle_level,
            micro_auditor_decision = micro_decision,
            policy_version         = POLICY_VERSION,
            latency_ms             = {
                "appraisal_ms":  appraisal_ms,
                "generation_ms": generation_ms,
                "audit_emit_ms": 0,   # updated later
                "total_ms":      total_ms,
            },
            qk                     = qk,
            decision_trace         = decision_trace,
            kvs                    = kvs,
            eal_admissibility      = eal_admissibility,
            retrieval_source       = retrieval_source,
            retrieval_score        = retrieval_score,
        )

        # Measure and fill in audit_emit_ms
        emit_ms = int((time.time() - t_emit_start) * 1000)
        record.latency_ms["audit_emit_ms"] = emit_ms

        if self._open:
            self._store.enqueue(record)

        return tid

    # ── emit_session_summary (session end) ────────────────────────────────

    def emit_session_summary(
        self,
        session_id:         str,
        phi_t_final:        float = 0.0,
        final_risk_posture: str   = "",
        calibration_events: int   = 0,
    ) -> SessionTraceSummary:
        """
        Emit exactly one record at session end (spec §4.4).

        Returns:
            The generated SessionTraceSummary
        """
        state = self._sampler.end_session()
        if state is None:
            # Session not started (e.g. tests)
            state_turn_count   = 0
            state_clamp_count  = 0
            state_verify_count = 0
            state_ask_count    = 0
            state_oracle_count = 0
            dominant_codes     = []
        else:
            state_turn_count   = state.turn_count
            state_clamp_count  = state.clamp_count
            state_verify_count = state.verify_count
            state_ask_count    = state.ask_count
            state_oracle_count = state.oracle_count
            # Most frequent reason_codes (top 5)
            counter = collections.Counter(state.reason_code_hist)
            dominant_codes = [code for code, _ in counter.most_common(5)]

        summary = SessionTraceSummary(
            session_id            = session_id,
            turn_count            = state_turn_count,
            clamp_count           = state_clamp_count,
            verify_count          = state_verify_count,
            ask_count             = state_ask_count,
            oracle_count          = state_oracle_count,
            dominant_reason_codes = dominant_codes,
            final_risk_posture    = final_risk_posture,
            calibration_events    = calibration_events,
            phi_t_final           = phi_t_final,
            audit_mode            = self.audit_mode,
        )

        if self._open:
            self._store.enqueue(summary)

        logger.info(
            f"[AuditEmitter] Session summary: "
            f"session={session_id} turns={state_turn_count} "
            f"verify={state_verify_count} clamp={state_clamp_count}"
        )
        return summary

    # ── emit_incident (anomalies only) ───────────────────────────────────────

    def emit_incident(
        self,
        session_id:       str,
        turn:             int,
        expected_route:   str,
        actual_route:     str,
        failure_type:     str,
        phi_t:            float = 0.0,
        correction_applied: bool = False,
        rollback_id:      Optional[str] = None,
    ) -> IncidentRecord:
        """
        Emit an Incident Record (anomalies only).

        Emits even when audit_mode=off (minimum safety guarantee).

        Returns:
            The generated IncidentRecord
        """
        record = IncidentRecord(
            session_id          = session_id,
            turn                = turn,
            expected_route      = expected_route,
            actual_route        = actual_route,
            failure_type        = failure_type,
            phi_t_at_incident   = phi_t,
            correction_applied  = correction_applied,
            rollback_id         = rollback_id,
        )

        if self._open:
            self._store.enqueue(record)

        logger.warning(
            f"[AuditEmitter] Incident: "
            f"session={session_id} turn={turn} "
            f"expected={expected_route} actual={actual_route} "
            f"type={failure_type}"
        )
        return record

    def status(self) -> dict:
        return {
            "audit_mode": self.audit_mode,
            "open":       self._open,
            "sampler":    self._sampler.status(),
            "store":      self._store.stats() if self._open else {},
        }
