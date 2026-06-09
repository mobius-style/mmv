#!/usr/bin/env python3
"""
audit_sampler.py — MOBIUS MMV Phase D: Audit Sampler
src/audit/audit_sampler.py

Manages audit_mode and firing rate.
"By separating, the audit rate can be changed during operation" (spec §3).

Sampling rates (spec §6.2):
  cold_start : 30% (immediately after session start)
  warm       : 10% (normal operation)
  steady     : 5%  (long-term stable session)
  risk_boost : 100% (high risk / new domain / clamp triggered)

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : phase_d_audit_spec.docx §6
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from audit_schema import (
    AUDIT_MODE_FULL,
    AUDIT_MODE_INCIDENT_ONLY,
    AUDIT_MODE_OFF,
    AUDIT_MODE_SHADOW,
    IncidentRecord,
)

logger = logging.getLogger(__name__)

# ── Sampling rate constants ────────────────────────────────────────────────────
RATE_COLD_START  = 0.30
RATE_WARM        = 0.10
RATE_STEADY      = 0.05
RATE_RISK_BOOST  = 1.00   # Always record during high risk

# Session state transition thresholds
COLD_START_TURNS = 3    # Turns at or below this count are cold_start
WARM_TURNS       = 20   # Turns at or below this count are warm
PHI_T_HIGH       = 0.90  # Trigger threshold for risk_boost


@dataclass
class SamplerState:
    """
    Holds sampling state within a session.
    Managed internally by AuditSampler.
    """
    session_id:       str   = ""
    turn_count:       int   = 0
    clamp_count:      int   = 0
    verify_count:     int   = 0
    ask_count:        int   = 0
    oracle_count:     int   = 0
    phi_t_prev:       float = 0.0
    phi_t_current:    float = 0.0
    reason_code_hist: list  = field(default_factory=list)


class AuditSampler:
    """
    Component responsible for audit firing decisions.

    Only 2 lines of changes required on the routing_engine.py side (spec §7.2).
    All decision logic is consolidated here.

    Usage:
        sampler = AuditSampler(audit_mode="shadow")
        sampler.start_session(session_id)

        # Per-turn decision
        should_full = sampler.should_record(
            route_decision="verify",
            clamped=False,
            clamp_reasons=[],
            phi_t=0.45,
        )

        # Incident decision
        should_inc = sampler.should_emit_incident(
            expected_route="answer",
            actual_route="abstain",
            clamp_reasons=[],
            phi_t=0.45,
            has_exception=False,
        )
    """

    def __init__(
        self,
        audit_mode:  str   = AUDIT_MODE_SHADOW,
        seed:        Optional[int] = None,
    ):
        self.audit_mode = audit_mode
        self._rng       = random.Random(seed)
        self._state:    Optional[SamplerState] = None

    # ── Session management ────────────────────────────────────────────────────

    def start_session(self, session_id: str) -> None:
        """Start a new session"""
        self._state = SamplerState(session_id=session_id)
        logger.debug(f"[AuditSampler] Session started: {session_id}")

    def end_session(self) -> Optional[SamplerState]:
        """End the session and return the final state"""
        state = self._state
        self._state = None
        return state

    def update(
        self,
        route_decision: str,
        clamped:        bool,
        phi_t:          float,
        oracle_used:    bool  = False,
        reason_codes:   list  = None,
    ) -> None:
        """Update sampler state with turn information"""
        if self._state is None:
            return
        s = self._state
        s.turn_count    += 1
        s.phi_t_prev     = s.phi_t_current
        s.phi_t_current  = phi_t
        if clamped:
            s.clamp_count += 1
        if route_decision == "verify":
            s.verify_count += 1
        elif route_decision == "ask":
            s.ask_count += 1
        if oracle_used:
            s.oracle_count += 1
        if reason_codes:
            s.reason_code_hist.extend(reason_codes)

    # ── Decision methods ─────────────────────────────────────────────────────

    def should_record(
        self,
        route_decision: str,
        clamped:        bool,
        clamp_reasons:  list,
        phi_t:          float,
    ) -> bool:
        """
        Determine whether a Full Turn Audit Record should be generated.

        audit_mode:
          off          -> always False
          shadow       -> sampling rate + risk_boost
          full         -> always True
          incident_only-> always False (Incident only)

        Returns:
            True: should generate Full Record
            False: Minimum Header only
        """
        if self.audit_mode == AUDIT_MODE_OFF:
            return False
        if self.audit_mode == AUDIT_MODE_FULL:
            return True
        if self.audit_mode == AUDIT_MODE_INCIDENT_ONLY:
            return False

        # SHADOW mode: risk_boost + sampling
        if self._is_risk_boost(route_decision, clamped, clamp_reasons, phi_t):
            logger.debug("[AuditSampler] risk_boost=True → Full Record")
            return True

        rate = self._current_sample_rate()
        result = self._rng.random() < rate
        logger.debug(f"[AuditSampler] sample_rate={rate:.0%} → {result}")
        return result

    def should_emit_incident(
        self,
        expected_route:  str,
        actual_route:    str,
        clamp_reasons:   list,
        phi_t:           float,
        has_exception:   bool,
    ) -> bool:
        """
        Determine whether an Incident Record should be generated.

        Even when audit_mode=off, Incidents are recorded (minimum safety guarantee).
        """
        phi_t_prev = self._state.phi_t_prev if self._state else 0.0
        return IncidentRecord.should_emit(
            expected_route  = expected_route,
            actual_route    = actual_route,
            clamp_reasons   = clamp_reasons,
            phi_t           = phi_t,
            phi_t_prev      = phi_t_prev,
            has_exception   = has_exception,
        )

    def current_session_state(self) -> Optional[SamplerState]:
        return self._state

    # ── Internal methods ─────────────────────────────────────────────────────

    def _is_risk_boost(
        self,
        route_decision: str,
        clamped:        bool,
        clamp_reasons:  list,
        phi_t:          float,
    ) -> bool:
        """risk_boost conditions (spec §6.2)"""
        if clamped:
            return True
        if route_decision in ("abstain",):
            return True
        if phi_t > PHI_T_HIGH:
            return True
        critical = {"SAFETY_CRITICAL", "POLICY_VIOLATION"}
        if any(r in critical for r in clamp_reasons):
            return True
        return False

    def _current_sample_rate(self) -> float:
        """Sampling rate based on current session state (spec §6.2)"""
        if self._state is None:
            return RATE_COLD_START
        n = self._state.turn_count
        if n <= COLD_START_TURNS:
            return RATE_COLD_START
        elif n <= WARM_TURNS:
            return RATE_WARM
        else:
            return RATE_STEADY

    def status(self) -> dict:
        """Return current state (for debugging and health checks)"""
        return {
            "audit_mode":    self.audit_mode,
            "has_session":   self._state is not None,
            "turn_count":    self._state.turn_count if self._state else 0,
            "sample_rate":   f"{self._current_sample_rate():.0%}",
            "phi_t_current": self._state.phi_t_current if self._state else 0.0,
        }
