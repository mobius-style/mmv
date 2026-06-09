#!/usr/bin/env python3
"""
carryover.py — Phase G.5: natural checkpoint-based carryover into Box P.

This module bridges Box M session state and Box P distilled continuity
WITHOUT forcing an end-of-session modal. The design:

  1. a lightweight `evaluate_checkpoint(...)` scores the current session
     against a natural-checkpoint bar every time the caller asks;
  2. when a checkpoint fires, a `CarryoverCandidate` is created; the
     candidate is distilled-only (no raw transcript);
  3. the candidate is only promoted into Box P if the session has NOT
     opted out of carryover — opt-out is a session-scoped flag that the
     UI can toggle at any time;
  4. promotion reuses `distill_from_user_map` so promotion rules stay
     in one place and can't drift.

The module is deliberately small and inspectable. No background threads,
no LLM calls, no network.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : "Phase G.5 — internal carryover / checkpoint hardening"
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .indexed_box_entry import (
    NOTE_CARRYOVER_CANDIDATE_CREATED,
    NOTE_CARRYOVER_CANDIDATE_LOW_CONF,
    NOTE_CARRYOVER_CANDIDATE_BLOCKED_OO,
    NOTE_CARRYOVER_CANDIDATE_PROMOTED,
    NOTE_CARRYOVER_DEFAULT_ALLOWED,
    NOTE_CARRYOVER_CHECKPOINT_DETECTED,
    NOTE_CARRYOVER_TOO_EARLY,
    NOTE_CARRYOVER_MANUAL_REQUEST,
    NOTE_CARRYOVER_AUTO_CHECKPOINT_FIRED,
    NOTE_CARRYOVER_AUTO_CHECKPOINT_SKIPPED,
    NOTE_CARRYOVER_PENDING_CREATED,
    NOTE_CARRYOVER_PENDING_REFRESHED,
    NOTE_CARRYOVER_PENDING_RESTORED,
    NOTE_CARRYOVER_PENDING_MALFORMED,
    NOTE_CARRYOVER_PENDING_CLEARED,
    NOTE_CARRYOVER_PENDING_REMAINS,
    NOTE_CARRYOVER_UI_ACTION_APPLIED,
    # Phase G.7 additions.
    NOTE_CARRYOVER_WAITING_CONFIRMATION,
    NOTE_CARRYOVER_WAITING_STABILITY,
    NOTE_CARRYOVER_AUTO_PROMOTED,
    NOTE_CARRYOVER_AUTO_PROMOTION_REJECTED_EPHEMERAL,
    NOTE_CARRYOVER_AUTO_PROMOTION_REJECTED_LOW_CONF,
    NOTE_CARRYOVER_AUTO_PROMOTION_REJECTED_OPT_OUT,
)
from .box_p import (
    PersonalContinuityProfile,
    DistillationResult,
    distill_from_user_map,
    MIN_CONTINUITY_CONFIDENCE,
    MIN_VALID_TURNS,
)


# ── Checkpoint thresholds (stricter than base promotion) ────────────────────
#
# Rationale: distill_from_user_map already enforces a promotion floor
# (MIN_CONTINUITY_CONFIDENCE=0.45, MIN_VALID_TURNS=3, no cold_start).
# A "natural checkpoint" sits ABOVE that floor — it's the moment where
# carryover starts to be clearly worthwhile, not just minimally safe.
CHECKPOINT_MIN_CONFIDENCE   = 0.55
CHECKPOINT_MIN_VALID_TURNS  = 5
CHECKPOINT_MIN_ADOPTED_FRAMES = 1
CHECKPOINT_MIN_THEMES       = 2

# Outcome enum-like constants (stringly typed for trace-friendliness).
OUTCOME_PROMOTABLE        = "promotable"
OUTCOME_BLOCKED_OPT_OUT   = "blocked_opt_out"
OUTCOME_LOW_CONFIDENCE    = "low_confidence"
OUTCOME_TOO_EARLY         = "too_early"
OUTCOME_PROMOTED          = "promoted"
OUTCOME_MANUAL_REQUEST    = "manual_request"

# Checkpoint trigger kinds.
CHECKPOINT_AUTOMATIC_STABLE = "automatic_stable"   # natural confidence/turn checkpoint
CHECKPOINT_MANUAL           = "manual"              # UI-requested explicit save


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Data model ──────────────────────────────────────────────────────────────


@dataclass
class CarryoverCandidate:
    """
    A distilled, non-raw snapshot of session signals that COULD be carried
    forward into Box P. Creation does NOT imply promotion; promotion is a
    separate gated step that respects `carryover_opt_out`.

    `signal_snapshot` holds only short tags / numerics (same gate as Box P
    promotion logic). The candidate intentionally carries NO raw turn
    content — enforced by how it is constructed.

    Phase G.7 additions:
      - `promotable_confirmations`: how many consecutive checkpoint fires
        have produced a PROMOTABLE outcome with a stable signal_snapshot.
        Used by the two-hit auto-promotion rule. Never decremented by the
        UI; reset only when the candidate is replaced by a non-promotable
        one or when the snapshot meaningfully changes.
      - `restored_from_import`: True iff this candidate was rehydrated by
        SessionState.import_json; cleared on the next refresh / clear.
    """
    checkpoint_kind:    str                       # CHECKPOINT_AUTOMATIC_STABLE | CHECKPOINT_MANUAL
    outcome:            str                       # OUTCOME_*
    created_at:         str                       = field(default_factory=_now_iso)
    confidence:         float                     = 0.0
    valid_turn_count:   int                       = 0
    signal_snapshot:    Dict[str, Any]            = field(default_factory=dict)
    reason:             str                       = ""
    notes:              List[str]                 = field(default_factory=list)
    # Phase G.7 fields. Defaults preserve G.6 backward compat.
    promotable_confirmations: int = 0
    restored_from_import:     bool = False

    def is_promotable(self) -> bool:
        return self.outcome == OUTCOME_PROMOTABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_kind":  self.checkpoint_kind,
            "outcome":          self.outcome,
            "created_at":       self.created_at,
            "confidence":       round(float(self.confidence), 4),
            "valid_turn_count": int(self.valid_turn_count),
            "signal_snapshot":  dict(self.signal_snapshot),
            "reason":           self.reason,
            "notes":            list(self.notes),
            "promotable_confirmations": int(self.promotable_confirmations),
            "restored_from_import":     bool(self.restored_from_import),
        }


@dataclass
class CheckpointEvaluation:
    """Return value of `evaluate_checkpoint`."""
    outcome:           str                      # OUTCOME_*
    candidate:         Optional[CarryoverCandidate] = None
    carryover_opt_out: bool                     = False
    notes:             List[str]                = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome":           self.outcome,
            "candidate":         self.candidate.to_dict() if self.candidate else None,
            "carryover_opt_out": self.carryover_opt_out,
            "notes":             list(self.notes),
        }


# ── Helpers ─────────────────────────────────────────────────────────────────


def _snapshot_signals(user_map: Any) -> Dict[str, Any]:
    """Extract ONLY distilled-safe signals from UserMap. Mirrors the
    fields that Box P is allowed to hold; never captures raw turn text."""
    def _short_list(seq, cap=16):
        out = []
        for x in (seq or []):
            if isinstance(x, str) and 0 < len(x) <= 240:
                out.append(x)
            if len(out) >= cap:
                break
        return out
    return {
        "confidence":           float(getattr(user_map, "confidence", 0.0) or 0.0),
        "valid_turn_count":     int(getattr(user_map, "valid_turn_count", 0) or 0),
        "cold_start":           bool(getattr(user_map, "cold_start", True)),
        "abstraction_baseline": float(getattr(user_map, "abstraction_baseline", 0.0) or 0.0),
        "comfort_zone":         float(getattr(user_map, "comfort_zone", 0.35) or 0.35),
        "adopted_frames":       _short_list(getattr(user_map, "adopted_frames", [])),
        "rejected_frames":      _short_list(getattr(user_map, "rejected_frames", [])),
        "active_themes":        _short_list(getattr(user_map, "active_themes", []),
                                            cap=16),
        "framing_preferences":  _short_list(getattr(user_map, "framing_preferences", []),
                                            cap=8),
    }


def _meets_natural_checkpoint(user_map: Any) -> bool:
    """True iff the session is stable enough for a NATURAL checkpoint
    (stricter than the minimum Box P promotion floor)."""
    if bool(getattr(user_map, "cold_start", True)):
        return False
    if float(getattr(user_map, "confidence", 0.0) or 0.0) < CHECKPOINT_MIN_CONFIDENCE:
        return False
    if int(getattr(user_map, "valid_turn_count", 0) or 0) < CHECKPOINT_MIN_VALID_TURNS:
        return False
    if len(getattr(user_map, "adopted_frames", []) or []) < CHECKPOINT_MIN_ADOPTED_FRAMES:
        return False
    if len(getattr(user_map, "active_themes", []) or []) < CHECKPOINT_MIN_THEMES:
        return False
    return True


# ── Public API ──────────────────────────────────────────────────────────────


def evaluate_checkpoint(
    *,
    user_map: Any,
    carryover_opt_out: bool = False,
    checkpoint_kind: str = CHECKPOINT_AUTOMATIC_STABLE,
) -> CheckpointEvaluation:
    """
    Evaluate the current session against the checkpoint bar and return a
    deterministic CheckpointEvaluation.

    Outcome order (evaluated top-down):
      - carryover_opt_out=True  → OUTCOME_BLOCKED_OPT_OUT  (candidate still
                                   created for inspectability, flagged blocked)
      - user_map cold_start or below floors → OUTCOME_LOW_CONFIDENCE
                                              / OUTCOME_TOO_EARLY
      - meets natural checkpoint bar → OUTCOME_PROMOTABLE
      - manual request (checkpoint_kind=CHECKPOINT_MANUAL) always
        produces at least a candidate; if opt-out on or floor not met,
        the candidate reflects that state honestly.

    This is a pure-Python function. No I/O. No network. Deterministic.
    """
    notes: List[str] = []
    snap = _snapshot_signals(user_map)

    # Always snapshot the natural bar result first; the outcome branches
    # compose on top.
    meets_bar = _meets_natural_checkpoint(user_map)

    # ── Opt-out branch: candidate is still created for inspection ────────
    if carryover_opt_out:
        notes.append(NOTE_CARRYOVER_CANDIDATE_BLOCKED_OO)
        if checkpoint_kind == CHECKPOINT_MANUAL:
            notes.append(NOTE_CARRYOVER_MANUAL_REQUEST)
        cand = CarryoverCandidate(
            checkpoint_kind=checkpoint_kind,
            outcome=OUTCOME_BLOCKED_OPT_OUT,
            confidence=snap["confidence"],
            valid_turn_count=snap["valid_turn_count"],
            signal_snapshot=snap,
            reason="session opted out of carryover",
            notes=list(notes),
        )
        return CheckpointEvaluation(
            outcome=OUTCOME_BLOCKED_OPT_OUT,
            candidate=cand,
            carryover_opt_out=True,
            notes=list(notes),
        )

    # ── Cold-start / floor branches ──────────────────────────────────────
    if snap["cold_start"]:
        notes.append(NOTE_CARRYOVER_TOO_EARLY)
        cand = CarryoverCandidate(
            checkpoint_kind=checkpoint_kind,
            outcome=OUTCOME_TOO_EARLY,
            confidence=snap["confidence"],
            valid_turn_count=snap["valid_turn_count"],
            signal_snapshot=snap,
            reason="cold_start",
            notes=list(notes),
        )
        return CheckpointEvaluation(
            outcome=OUTCOME_TOO_EARLY, candidate=cand,
            carryover_opt_out=False, notes=list(notes),
        )

    if not meets_bar:
        notes.append(NOTE_CARRYOVER_CANDIDATE_LOW_CONF)
        cand = CarryoverCandidate(
            checkpoint_kind=checkpoint_kind,
            outcome=OUTCOME_LOW_CONFIDENCE,
            confidence=snap["confidence"],
            valid_turn_count=snap["valid_turn_count"],
            signal_snapshot=snap,
            reason="below natural checkpoint bar",
            notes=list(notes),
        )
        # A manual request still gets a candidate (user asked explicitly)
        # but it is NOT promotable: distill_from_user_map would reject at
        # its own floor, so we mark it honestly here.
        return CheckpointEvaluation(
            outcome=OUTCOME_LOW_CONFIDENCE, candidate=cand,
            carryover_opt_out=False, notes=list(notes),
        )

    # ── Promotable branch ────────────────────────────────────────────────
    notes.append(NOTE_CARRYOVER_CHECKPOINT_DETECTED)
    notes.append(NOTE_CARRYOVER_CANDIDATE_CREATED)
    if checkpoint_kind == CHECKPOINT_MANUAL:
        notes.append(NOTE_CARRYOVER_MANUAL_REQUEST)
    cand = CarryoverCandidate(
        checkpoint_kind=checkpoint_kind,
        outcome=OUTCOME_PROMOTABLE,
        confidence=snap["confidence"],
        valid_turn_count=snap["valid_turn_count"],
        signal_snapshot=snap,
        reason="natural checkpoint bar met",
        notes=list(notes),
    )
    return CheckpointEvaluation(
        outcome=OUTCOME_PROMOTABLE, candidate=cand,
        carryover_opt_out=False, notes=list(notes),
    )


def promote_candidate(
    candidate: CarryoverCandidate,
    profile: PersonalContinuityProfile,
    *,
    user_map: Any,
    language: Optional[str] = None,
) -> DistillationResult:
    """
    Promote a promotable candidate into Box P by reusing the existing
    distillation logic. Refuses if the candidate is not promotable.

    Returns the underlying DistillationResult; also emits a
    NOTE_CARRYOVER_CANDIDATE_PROMOTED note in the candidate's `notes`.
    """
    if candidate is None or not candidate.is_promotable():
        return DistillationResult(
            promoted=[],
            rejected=["candidate_not_promotable"],
            notes=["candidate_not_promotable"],
        )
    result = distill_from_user_map(
        profile, user_map, language=language,
    )
    candidate.notes.append(NOTE_CARRYOVER_CANDIDATE_PROMOTED)
    candidate.outcome = OUTCOME_PROMOTED
    return result


def describe_default_policy() -> str:
    """Short description suitable for UI hover / debug output."""
    return (
        "Carryover is allowed by default. Signals distilled from stable "
        "sessions may contribute to future continuity (Box P). Raw "
        "transcripts are never carried forward."
    )


# ── Phase G.6 — pending candidate serialization / restore ───────────────────

# Schema version for the pending-candidate JSON shape. Bumping this when
# the shape changes tells `candidate_from_dict` to degrade to None for
# older/incompatible shapes rather than silently mis-decoding.
PENDING_CANDIDATE_SCHEMA_VERSION = 1


def candidate_to_dict(candidate: "CarryoverCandidate") -> Dict[str, Any]:
    """Serialize a CarryoverCandidate to a JSON-safe dict with a schema
    version tag. Pure projection — no hidden state."""
    if candidate is None:
        return {}
    d = candidate.to_dict()
    d["schema_version"] = PENDING_CANDIDATE_SCHEMA_VERSION
    return d


def candidate_from_dict(
    data: Optional[Dict[str, Any]],
) -> Optional["CarryoverCandidate"]:
    """Restore a CarryoverCandidate from a dict. Returns None for
    missing, non-dict, version-mismatched, or malformed inputs — never
    raises. Callers should treat None as "no pending candidate"."""
    if not isinstance(data, dict) or not data:
        return None
    if int(data.get("schema_version") or 0) != PENDING_CANDIDATE_SCHEMA_VERSION:
        return None
    try:
        kind = str(data.get("checkpoint_kind") or "")
        outcome = str(data.get("outcome") or "")
        if kind not in (CHECKPOINT_AUTOMATIC_STABLE, CHECKPOINT_MANUAL):
            return None
        if outcome not in (OUTCOME_PROMOTABLE, OUTCOME_BLOCKED_OPT_OUT,
                           OUTCOME_LOW_CONFIDENCE, OUTCOME_TOO_EARLY,
                           OUTCOME_PROMOTED, OUTCOME_MANUAL_REQUEST):
            return None
        snap = data.get("signal_snapshot") or {}
        if not isinstance(snap, dict):
            snap = {}
        notes = [n for n in (data.get("notes") or []) if isinstance(n, str)]
        return CarryoverCandidate(
            checkpoint_kind=kind,
            outcome=outcome,
            created_at=str(data.get("created_at") or _now_iso()),
            confidence=float(data.get("confidence") or 0.0),
            valid_turn_count=int(data.get("valid_turn_count") or 0),
            signal_snapshot=snap,
            reason=str(data.get("reason") or ""),
            notes=notes,
            promotable_confirmations=max(
                0, int(data.get("promotable_confirmations") or 0)
            ),
            restored_from_import=bool(data.get("restored_from_import") or False),
        )
    except (TypeError, ValueError):
        return None


# ── Phase G.6 — natural triggering helpers ──────────────────────────────────
#
# These helpers are invoked OUT OF the hot path (e.g. post-response in the
# UI, or by an explicit user action). They never call LLMs, never touch
# disk, and never mutate Box M semantics. They only:
#   - evaluate_checkpoint(...)
#   - create/refresh the pending candidate on SessionState
#   - (for manual promotion) invoke promote_candidate(...)
#   - honor carryover_opt_out
#
# Hot-path safety: each call is O(|adopted_frames| + |themes|), bounded by
# the caps Box P already enforces, and performs no I/O.


# Default automatic trigger gating: fire at most once per N turns, and
# require a minimum turn delta since the last fire. Callers may override.
AUTO_CHECKPOINT_TURN_INTERVAL  = 3      # check at most every 3 turns
AUTO_CHECKPOINT_MIN_TURNS_SINCE_LAST = 3


def maybe_checkpoint(
    session_state: Any,
    *,
    turn_interval: int = AUTO_CHECKPOINT_TURN_INTERVAL,
    force: bool = False,
) -> Optional[CheckpointEvaluation]:
    """
    Natural automatic checkpoint trigger. Invoked OUT OF the hot path
    (e.g. after the routing engine's response has already been rendered).

    Behavior:
      - skips if opt-out is active (opt-out invalidation is handled
        separately by the UI/sync; this is a soft skip so unnecessary
        work is avoided)
      - skips when not enough turns have elapsed since the last fire
      - skips when the session doesn't yet meet the natural checkpoint bar
      - otherwise, evaluates and writes a pending candidate onto
        `session_state.pending_carryover_candidate` (dict)

    Returns:
        CheckpointEvaluation when a checkpoint fires; None otherwise.

    Safe on any input: any missing attribute on `session_state` is
    treated as "skip" rather than an error.
    """
    if session_state is None:
        return None

    opt_out = bool(getattr(session_state, "carryover_opt_out", False))
    if opt_out and not force:
        _append_session_note(session_state, NOTE_CARRYOVER_AUTO_CHECKPOINT_SKIPPED)
        return None

    # Turn-interval gate: avoid firing every single turn.
    last_turn = int(getattr(session_state, "_last_checkpoint_turn", 0) or 0)
    current_turn = int(getattr(session_state, "current_turn", 0) or 0)
    if not force:
        if current_turn - last_turn < max(1, int(turn_interval)):
            _append_session_note(session_state, NOTE_CARRYOVER_AUTO_CHECKPOINT_SKIPPED)
            return None

    # Read UserMap via the SessionState lazy accessor if available;
    # otherwise skip (no UserMap → nothing distillable).
    um = None
    ensure_um = getattr(session_state, "ensure_user_map", None)
    if callable(ensure_um):
        try:
            um = ensure_um()
        except Exception:   # noqa: BLE001
            um = None
    if um is None:
        return None

    ev = evaluate_checkpoint(
        user_map=um,
        carryover_opt_out=opt_out,
        checkpoint_kind=CHECKPOINT_AUTOMATIC_STABLE,
    )

    # The automatic path never auto-promotes into Box P — it only
    # refreshes the pending candidate. Promotion is explicit only.
    _set_pending(session_state, ev.candidate, restore_source=False)
    _record_turn(session_state, current_turn)
    _append_session_note(session_state, NOTE_CARRYOVER_AUTO_CHECKPOINT_FIRED)
    # Persist evaluation for UI inspection.
    try:
        session_state.record_checkpoint_evaluation(ev)
    except Exception:   # noqa: BLE001
        pass
    return ev


def trigger_manual_checkpoint(
    session_state: Any,
    *,
    promote: bool = True,
    profile: Optional[PersonalContinuityProfile] = None,
    language: Optional[str] = None,
) -> CheckpointEvaluation:
    """
    Explicit/manual checkpoint trigger. Reuses evaluate_checkpoint — no
    logic fork. When the candidate is promotable AND `promote=True` AND
    a `profile` is provided, the candidate is promoted into Box P via
    `promote_candidate` (which itself reuses `distill_from_user_map`).

    Always returns a CheckpointEvaluation. Invariants:
      - opt-out blocks promotion (never bypassed)
      - non-promotable candidates are never promoted
      - no raw transcript flows into P (promote_candidate enforces this)
      - the pending candidate on SessionState is refreshed either way
        so the UI always shows the latest evaluated state
    """
    if session_state is None:
        # Degenerate case: no session → degenerate eval.
        return CheckpointEvaluation(
            outcome=OUTCOME_TOO_EARLY, candidate=None,
            carryover_opt_out=False, notes=["no_session_state"],
        )

    opt_out = bool(getattr(session_state, "carryover_opt_out", False))
    um = None
    ensure_um = getattr(session_state, "ensure_user_map", None)
    if callable(ensure_um):
        try:
            um = ensure_um()
        except Exception:   # noqa: BLE001
            um = None
    if um is None:
        # No UserMap → still produce a degenerate eval so UI has
        # something to display.
        return CheckpointEvaluation(
            outcome=OUTCOME_TOO_EARLY, candidate=None,
            carryover_opt_out=opt_out, notes=["no_user_map"],
        )

    ev = evaluate_checkpoint(
        user_map=um,
        carryover_opt_out=opt_out,
        checkpoint_kind=CHECKPOINT_MANUAL,
    )
    _set_pending(session_state, ev.candidate, restore_source=False)

    if promote and profile is not None and ev.candidate is not None \
            and ev.candidate.is_promotable():
        promote_candidate(ev.candidate, profile, user_map=um, language=language)
        # Refresh pending to reflect outcome=PROMOTED.
        _set_pending(session_state, ev.candidate, restore_source=False)
        _append_session_note(session_state, NOTE_CARRYOVER_UI_ACTION_APPLIED)

    try:
        session_state.record_checkpoint_evaluation(ev)
    except Exception:   # noqa: BLE001
        pass
    return ev


def promote_pending(
    session_state: Any,
    profile: PersonalContinuityProfile,
    *,
    user_map: Any = None,
    language: Optional[str] = None,
) -> DistillationResult:
    """
    Promote the SessionState's currently-pending candidate into Box P.
    Refuses when:
      - there is no pending candidate
      - the pending candidate is not promotable (opt-out / low-conf /
        too-early / already promoted)
    Never dumps raw transcript — promotion funnels through
    `promote_candidate` which reuses `distill_from_user_map`.
    """
    pending_raw = getattr(session_state, "pending_carryover_candidate", None)
    cand = candidate_from_dict(pending_raw) if isinstance(pending_raw, dict) else None
    if cand is None or not cand.is_promotable():
        return DistillationResult(
            promoted=[], rejected=["no_promotable_pending_candidate"],
            notes=["no_promotable_pending_candidate"],
        )

    if user_map is None:
        ensure_um = getattr(session_state, "ensure_user_map", None)
        if callable(ensure_um):
            try:
                user_map = ensure_um()
            except Exception:   # noqa: BLE001
                user_map = None
    if user_map is None:
        return DistillationResult(
            promoted=[], rejected=["no_user_map"], notes=["no_user_map"],
        )

    result = promote_candidate(cand, profile, user_map=user_map, language=language)
    _set_pending(session_state, cand, restore_source=False)
    _append_session_note(session_state, NOTE_CARRYOVER_UI_ACTION_APPLIED)
    return result


def invalidate_pending_on_opt_out(session_state: Any) -> bool:
    """
    When the user toggles opt-out ON, any currently-promotable pending
    candidate must be visibly invalidated: its outcome flips to
    OUTCOME_BLOCKED_OPT_OUT. The structure is preserved so the UI can
    still show "was ready; now blocked by your opt-out choice".

    Returns True if a pending candidate existed and was mutated; False
    otherwise. Never raises.
    """
    pending_raw = getattr(session_state, "pending_carryover_candidate", None)
    if not isinstance(pending_raw, dict) or not pending_raw:
        return False
    cand = candidate_from_dict(pending_raw)
    if cand is None:
        # Malformed; clear it and emit the fallback note.
        setattr(session_state, "pending_carryover_candidate", None)
        _append_session_note(session_state, NOTE_CARRYOVER_PENDING_MALFORMED)
        return False
    if cand.outcome != OUTCOME_PROMOTED and cand.outcome != OUTCOME_BLOCKED_OPT_OUT:
        cand.outcome = OUTCOME_BLOCKED_OPT_OUT
        if NOTE_CARRYOVER_CANDIDATE_BLOCKED_OO not in cand.notes:
            cand.notes.append(NOTE_CARRYOVER_CANDIDATE_BLOCKED_OO)
        _set_pending(session_state, cand, restore_source=False)
        return True
    return False


def restore_pending_from_dict(
    session_state: Any,
    data: Optional[Dict[str, Any]],
) -> Optional[CarryoverCandidate]:
    """
    Called from SessionState import / UI restore. Accepts arbitrary
    dict/None; restores a pending candidate onto session_state if valid,
    else clears the slot and emits an inspectable note.
    """
    cand = candidate_from_dict(data) if isinstance(data, dict) else None
    if cand is None:
        setattr(session_state, "pending_carryover_candidate", None)
        if data:   # something was there but malformed
            _append_session_note(session_state, NOTE_CARRYOVER_PENDING_MALFORMED)
        return None
    _set_pending(session_state, cand, restore_source=True)
    return cand


def pending_status_summary(session_state: Any) -> Dict[str, Any]:
    """
    Compact dict for UI/trace inspection of pending candidate state.
    Safe on any input.
    """
    opt_out = bool(getattr(session_state, "carryover_opt_out", False))
    raw = getattr(session_state, "pending_carryover_candidate", None)
    cand = candidate_from_dict(raw) if isinstance(raw, dict) else None
    return {
        "has_pending":       cand is not None,
        "outcome":           getattr(cand, "outcome", None),
        "checkpoint_kind":   getattr(cand, "checkpoint_kind", None),
        "confidence":        getattr(cand, "confidence", None),
        "valid_turn_count":  getattr(cand, "valid_turn_count", None),
        "carryover_opt_out": opt_out,
    }


# ── private internal helpers (module-scoped; pure mutators on state) ────────


def _signal_stability_key(cand: Optional[CarryoverCandidate]) -> tuple:
    """A compact, comparable key capturing the 'shape' of the candidate's
    distilled signals. Two candidates with matching keys are considered
    'same session state' for the two-hit rule."""
    if cand is None:
        return ()
    snap = cand.signal_snapshot or {}
    return (
        tuple(sorted(snap.get("adopted_frames", []) or [])),
        tuple(sorted(snap.get("active_themes", []) or [])),
        tuple(sorted(snap.get("framing_preferences", []) or [])),
    )


def _set_pending(
    session_state: Any,
    candidate: Optional[CarryoverCandidate],
    *,
    restore_source: bool,
) -> None:
    """Write/refresh pending_carryover_candidate on SessionState as a
    serialization-safe dict. Emits the right note: 'created' vs
    'refreshed' vs 'restored' vs 'cleared'.

    Phase G.7: carries `promotable_confirmations` forward across
    refreshes. When the new candidate is promotable AND the prior
    candidate was promotable AND the signal-stability key is unchanged,
    increment the counter. Any other transition resets it to the
    floor (1 when promotable, 0 otherwise)."""
    if candidate is None:
        had_any = bool(getattr(session_state, "pending_carryover_candidate", None))
        setattr(session_state, "pending_carryover_candidate", None)
        if had_any:
            _append_session_note(session_state, NOTE_CARRYOVER_PENDING_CLEARED)
        return

    # Read the prior candidate (if any) to thread the confirmation counter.
    prior_raw = getattr(session_state, "pending_carryover_candidate", None)
    prior = candidate_from_dict(prior_raw) if isinstance(prior_raw, dict) else None

    if candidate.outcome == OUTCOME_PROMOTABLE:
        if (prior is not None
                and prior.outcome == OUTCOME_PROMOTABLE
                and _signal_stability_key(prior) == _signal_stability_key(candidate)):
            candidate.promotable_confirmations = int(prior.promotable_confirmations) + 1
        else:
            candidate.promotable_confirmations = max(
                1, int(candidate.promotable_confirmations or 0)
            )
    else:
        # Any non-promotable outcome resets the counter.
        candidate.promotable_confirmations = 0

    # Restoration flag is transient — set on restore, cleared on refresh.
    candidate.restored_from_import = bool(restore_source)

    had_any = prior is not None
    setattr(
        session_state,
        "pending_carryover_candidate",
        candidate_to_dict(candidate),
    )
    if restore_source:
        _append_session_note(session_state, NOTE_CARRYOVER_PENDING_RESTORED)
    elif had_any:
        _append_session_note(session_state, NOTE_CARRYOVER_PENDING_REFRESHED)
    else:
        _append_session_note(session_state, NOTE_CARRYOVER_PENDING_CREATED)


def _record_turn(session_state: Any, turn: int) -> None:
    try:
        setattr(session_state, "_last_checkpoint_turn", int(turn))
    except Exception:   # noqa: BLE001
        pass


def _append_session_note(session_state: Any, note: str) -> None:
    """Forward to SessionState's capped note log; tolerate absence."""
    fn = getattr(session_state, "_append_carryover_note", None)
    if callable(fn):
        try:
            fn(note)
        except Exception:   # noqa: BLE001
            pass


# ── Phase G.7 — stricter automatic promotion policy ─────────────────────────
#
# Design (conservative combination of spec §5.3 options):
#   OPTION A (two-hit rule): a candidate must be PROMOTABLE on at least
#     AUTO_PROMOTION_MIN_CONFIRMATIONS separate checkpoint fires with a
#     stable signal snapshot (same adopted_frames / active_themes /
#     framing_preferences) before automatic promotion is allowed.
#   OPTION C (adopted-signal dominance): the stable snapshot must include
#     at least one adopted frame. Inference-only sessions cannot
#     auto-promote even when the turn / confidence bars are met.
#   Plus a stricter confidence floor (AUTO_PROMOTION_MIN_CONFIDENCE) sits
#   above the natural-checkpoint bar, so auto-promotion only fires on
#   clearly-stable sessions.
#
# Opt-out, cold_start, malformed candidates, and non-promotable outcomes
# can never auto-promote.

AUTO_PROMOTION_MIN_CONFIRMATIONS = 2      # two-hit rule
AUTO_PROMOTION_MIN_CONFIDENCE    = 0.65   # above checkpoint bar 0.55
AUTO_PROMOTION_REQUIRE_ADOPTED_FRAME = True


@dataclass
class AutoPromotionResult:
    """Outcome of a single `maybe_auto_promote` call."""
    promoted:      bool                 = False
    reason:        str                  = ""
    distillation:  Optional[DistillationResult] = None
    notes:         List[str]            = field(default_factory=list)


def maybe_auto_promote(
    session_state: Any,
    *,
    profile: Optional[PersonalContinuityProfile] = None,
    user_map: Any = None,
    language: Optional[str] = None,
) -> AutoPromotionResult:
    """
    Evaluate the auto-promotion policy and, if all gates pass, promote
    the currently-pending candidate into Box P.

    This function is called OUT OF the hot path (e.g. from the UI's
    post-response hook). It is safe to call every turn — most calls will
    short-circuit cheaply. Observability notes are appended to the
    session log regardless of outcome.

    Never raises on bad input.
    """
    notes: List[str] = []

    if session_state is None:
        return AutoPromotionResult(promoted=False, reason="no_session", notes=notes)

    # Opt-out: no automatic promotion. Ever.
    if bool(getattr(session_state, "carryover_opt_out", False)):
        notes.append(NOTE_CARRYOVER_AUTO_PROMOTION_REJECTED_OPT_OUT)
        for n in notes:
            _append_session_note(session_state, n)
        return AutoPromotionResult(
            promoted=False, reason="opt_out", notes=notes,
        )

    pending_raw = getattr(session_state, "pending_carryover_candidate", None)
    cand = candidate_from_dict(pending_raw) if isinstance(pending_raw, dict) else None
    if cand is None:
        return AutoPromotionResult(
            promoted=False, reason="no_pending", notes=notes,
        )

    # Non-promotable outcomes → nothing to do.
    if not cand.is_promotable():
        notes.append(NOTE_CARRYOVER_WAITING_CONFIRMATION)
        _append_session_note(session_state, NOTE_CARRYOVER_WAITING_CONFIRMATION)
        return AutoPromotionResult(
            promoted=False, reason="not_promotable",
            notes=notes,
        )

    # Two-hit rule.
    if cand.promotable_confirmations < AUTO_PROMOTION_MIN_CONFIRMATIONS:
        notes.append(NOTE_CARRYOVER_WAITING_CONFIRMATION)
        _append_session_note(session_state, NOTE_CARRYOVER_WAITING_CONFIRMATION)
        return AutoPromotionResult(
            promoted=False,
            reason=f"waiting_confirmation "
                   f"({cand.promotable_confirmations}/{AUTO_PROMOTION_MIN_CONFIRMATIONS})",
            notes=notes,
        )

    # Stricter confidence bar.
    if cand.confidence < AUTO_PROMOTION_MIN_CONFIDENCE:
        notes.append(NOTE_CARRYOVER_AUTO_PROMOTION_REJECTED_LOW_CONF)
        _append_session_note(session_state, NOTE_CARRYOVER_AUTO_PROMOTION_REJECTED_LOW_CONF)
        return AutoPromotionResult(
            promoted=False, reason="low_confidence",
            notes=notes,
        )

    # Adopted-signal dominance: auto-promotion needs at least one adopted
    # frame. Inference-only themes are not enough.
    if AUTO_PROMOTION_REQUIRE_ADOPTED_FRAME:
        snap = cand.signal_snapshot or {}
        adopted = snap.get("adopted_frames") or []
        if not adopted:
            notes.append(NOTE_CARRYOVER_AUTO_PROMOTION_REJECTED_EPHEMERAL)
            _append_session_note(
                session_state, NOTE_CARRYOVER_AUTO_PROMOTION_REJECTED_EPHEMERAL,
            )
            return AutoPromotionResult(
                promoted=False, reason="no_adopted_frame",
                notes=notes,
            )

    # Resolve profile + UserMap.
    if profile is None:
        ensure_p = getattr(session_state, "ensure_box_p", None)
        if callable(ensure_p):
            try:
                profile = ensure_p()
            except Exception:   # noqa: BLE001
                profile = None
    if profile is None:
        return AutoPromotionResult(
            promoted=False, reason="no_profile",
            notes=notes,
        )

    if user_map is None:
        ensure_um = getattr(session_state, "ensure_user_map", None)
        if callable(ensure_um):
            try:
                user_map = ensure_um()
            except Exception:   # noqa: BLE001
                user_map = None
    if user_map is None:
        return AutoPromotionResult(
            promoted=False, reason="no_user_map",
            notes=notes,
        )

    # All gates passed. Promote via the existing distilled-only path.
    result = promote_candidate(cand, profile, user_map=user_map, language=language)
    # promote_candidate flips outcome to PROMOTED on the candidate; mirror
    # that into the session store so the UI reflects the change.
    _set_pending(session_state, cand, restore_source=False)
    notes.append(NOTE_CARRYOVER_AUTO_PROMOTED)
    _append_session_note(session_state, NOTE_CARRYOVER_AUTO_PROMOTED)
    return AutoPromotionResult(
        promoted=True, reason="auto_promoted",
        distillation=result, notes=notes,
    )


# ── Phase G.7 — canonical user-facing presentation layer ────────────────────

# Canonical internal presentation-state names. UI code MUST derive labels
# from these; tests can assert exact label strings.
PRESENT_NONE              = "none"
PRESENT_PENDING_LOW_CONF  = "pending_low_confidence"
PRESENT_PENDING_READY     = "pending_ready"
PRESENT_PENDING_RESTORED  = "restored_pending"
PRESENT_BLOCKED_OPT_OUT   = "blocked_opt_out"
PRESENT_PROMOTED          = "promoted"
PRESENT_MALFORMED         = "malformed_fallback"


@dataclass
class CarryoverPresentationStatus:
    """
    Tiny, UI-oriented view of the current carryover state. Computed from
    SessionState at read-time; never cached. Safe to serialize.
    """
    state:         str         # one of PRESENT_*
    label:         str         # short user-facing text (chip)
    help_text:     str         # short one-line hint for tooltip/help
    can_save:      bool        # True iff the manual save button should be enabled
    carryover_allowed: bool    # mirror of (not opt_out), for convenience

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state":             self.state,
            "label":             self.label,
            "help_text":         self.help_text,
            "can_save":          self.can_save,
            "carryover_allowed": self.carryover_allowed,
        }


# Canonical labels + help text. Kept short, natural, non-technical.
_PRESENT_LABELS = {
    PRESENT_NONE:             ("Not ready",
                               "Nothing to carry forward yet."),
    PRESENT_PENDING_LOW_CONF: ("Not ready",
                               "Signals are still settling; nothing to save yet."),
    PRESENT_PENDING_READY:    ("Ready",
                               "Ready to save as future continuity."),
    PRESENT_PENDING_RESTORED: ("Ready (restored)",
                               "Restored from the previous saved session."),
    PRESENT_BLOCKED_OPT_OUT:  ("Blocked",
                               "This conversation is set not to carry forward."),
    PRESENT_PROMOTED:         ("Saved",
                               "Continuity from this conversation has been saved."),
    PRESENT_MALFORMED:        ("Not ready",
                               "The previous continuity record could not be read; starting fresh."),
}


def presentation_status(session_state: Any) -> CarryoverPresentationStatus:
    """
    Compute the canonical user-facing carryover status for the given
    SessionState. Never raises; any unexpected input falls back to
    PRESENT_NONE.

    Resolution order:
      - no session_state → PRESENT_NONE
      - opt-out → PRESENT_BLOCKED_OPT_OUT
      - no pending candidate → PRESENT_NONE
      - malformed pending candidate → PRESENT_MALFORMED
      - candidate outcome drives the rest:
          PROMOTED → PRESENT_PROMOTED
          PROMOTABLE + restored_from_import → PRESENT_PENDING_RESTORED
          PROMOTABLE → PRESENT_PENDING_READY
          BLOCKED_OPT_OUT → PRESENT_BLOCKED_OPT_OUT (e.g. candidate saved
                            before user opted out)
          else (LOW_CONFIDENCE / TOO_EARLY / MANUAL_REQUEST) → PRESENT_PENDING_LOW_CONF
    """
    if session_state is None:
        return _present(PRESENT_NONE, carryover_allowed=True)

    opt_out = bool(getattr(session_state, "carryover_opt_out", False))
    raw = getattr(session_state, "pending_carryover_candidate", None)

    # Opt-out takes precedence for presentation — the user's choice is
    # the most important thing to show; the underlying pending state is
    # preserved internally but presented as "Blocked".
    if opt_out:
        # If there is no pending candidate, still report "Blocked" so the
        # user understands the feature is off, not just "nothing to save".
        return _present(PRESENT_BLOCKED_OPT_OUT, carryover_allowed=False)

    if raw is None:
        return _present(PRESENT_NONE, carryover_allowed=True)
    if not isinstance(raw, dict) or not raw:
        return _present(PRESENT_NONE, carryover_allowed=True)

    cand = candidate_from_dict(raw)
    if cand is None:
        return _present(PRESENT_MALFORMED, carryover_allowed=True)

    if cand.outcome == OUTCOME_PROMOTED:
        return _present(PRESENT_PROMOTED, carryover_allowed=True)
    if cand.outcome == OUTCOME_BLOCKED_OPT_OUT:
        return _present(PRESENT_BLOCKED_OPT_OUT, carryover_allowed=False)
    if cand.outcome == OUTCOME_PROMOTABLE:
        if cand.restored_from_import:
            return _present(PRESENT_PENDING_RESTORED, carryover_allowed=True)
        return _present(PRESENT_PENDING_READY, carryover_allowed=True)

    # LOW_CONFIDENCE / TOO_EARLY / MANUAL_REQUEST without promotion.
    return _present(PRESENT_PENDING_LOW_CONF, carryover_allowed=True)


def _present(state: str, *, carryover_allowed: bool) -> CarryoverPresentationStatus:
    label, help_text = _PRESENT_LABELS.get(
        state, _PRESENT_LABELS[PRESENT_NONE]
    )
    can_save = (state == PRESENT_PENDING_READY
                or state == PRESENT_PENDING_RESTORED)
    return CarryoverPresentationStatus(
        state=state,
        label=label,
        help_text=help_text,
        can_save=can_save,
        carryover_allowed=carryover_allowed,
    )


__all__ = [
    "CarryoverCandidate",
    "CheckpointEvaluation",
    "evaluate_checkpoint",
    "promote_candidate",
    "describe_default_policy",
    # Phase G.6 operational surface.
    "maybe_checkpoint",
    "trigger_manual_checkpoint",
    "promote_pending",
    "invalidate_pending_on_opt_out",
    "restore_pending_from_dict",
    "pending_status_summary",
    "candidate_to_dict",
    "candidate_from_dict",
    "PENDING_CANDIDATE_SCHEMA_VERSION",
    "AUTO_CHECKPOINT_TURN_INTERVAL",
    "AUTO_CHECKPOINT_MIN_TURNS_SINCE_LAST",
    # Phase G.7 additions.
    "maybe_auto_promote",
    "AutoPromotionResult",
    "AUTO_PROMOTION_MIN_CONFIRMATIONS",
    "AUTO_PROMOTION_MIN_CONFIDENCE",
    "AUTO_PROMOTION_REQUIRE_ADOPTED_FRAME",
    "CarryoverPresentationStatus",
    "presentation_status",
    "PRESENT_NONE", "PRESENT_PENDING_LOW_CONF", "PRESENT_PENDING_READY",
    "PRESENT_PENDING_RESTORED", "PRESENT_BLOCKED_OPT_OUT",
    "PRESENT_PROMOTED", "PRESENT_MALFORMED",
    "OUTCOME_PROMOTABLE", "OUTCOME_BLOCKED_OPT_OUT",
    "OUTCOME_LOW_CONFIDENCE", "OUTCOME_TOO_EARLY",
    "OUTCOME_PROMOTED", "OUTCOME_MANUAL_REQUEST",
    "CHECKPOINT_AUTOMATIC_STABLE", "CHECKPOINT_MANUAL",
    "CHECKPOINT_MIN_CONFIDENCE", "CHECKPOINT_MIN_VALID_TURNS",
    "CHECKPOINT_MIN_ADOPTED_FRAMES", "CHECKPOINT_MIN_THEMES",
]
