#!/usr/bin/env python3
"""
memory_capsule.py — MOBIUS MMV Phase E: Memory Capsule Generator
src/memory/memory_capsule.py

"Audit logs are not memory itself, but the arbiter of memory generation" (spec §5)

Phase E E.0: MemoryCapsule dataclass + _classify() / _score() / _compose()
Phase E E.2: generate_capsule() is called after routing_engine.py integration

Design principles:
  - No LLM usage. Generate memory_text via templates.
  - Derive Capsule from Audit Log (FullTurnAuditRecord).
  - Audit logs and memory are separate layers (spec §7).

Connection with KVS (knowledge_volatility_essay v1.1 §14):
  - Low tvs (stable knowledge) -> Capsule promotion candidate (salience up)
  - High tvs (volatile knowledge) -> shorter ttl / generation suppression
  - Once computed=True, the decay policy becomes more precise

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : phase_e_memory_spec.docx §4, §5, §6, Appendix A/B
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

# ── Constants (spec Appendix A) ──────────────────────────────────────────────
SALIENCE_THRESHOLD = 0.35   # Capsules below this threshold are not generated

MEMORY_TYPES: dict[str, dict] = {
    "preference":  {"default_ttl": None},   # persistent
    "goal":        {"default_ttl": None},   # persistent
    "constraint":  {"default_ttl": None},   # persistent
    "open_loop":   {"default_ttl": "30d"},  # 30 days
    "stable_fact": {"default_ttl": "90d"},  # 90 days
}

# Salience addition values
SALIENCE_BASE              = 0.40
SALIENCE_LONGTERM_HIGH     = 0.30   # qk.longterm = high
SALIENCE_LONGTERM_OK       = 0.10   # qk.longterm = ok
SALIENCE_VERIFY_SUCCESS    = 0.15   # route_decision = verify_success
SALIENCE_TVS_LOW_BONUS     = 0.10   # kvs.tvs < 0.3 (stable knowledge)
SALIENCE_TVS_HIGH_PENALTY  = -0.10  # kvs.tvs > 0.7 (volatile knowledge)

# Shorten TTL when clamped
CLAMPED_TTL_DAYS           = 7


# ── MemoryCapsule dataclass (spec §4.1, Appendix A) ────────────────────────

@dataclass
class MemoryCapsule:
    """
    Minimum unit of Reflective Long-Term Memory.

    Attributes:
        capsule_id       : UUID
        session_id       : Source session
        source_turn_ids  : turn_id[] of turns used for generation
        memory_text      : Semantic summary text (embedding target)
        memory_type      : preference|goal|constraint|open_loop|stable_fact
        salience_score   : 0.0-1.0 (storage priority)
        ttl              : ISO 8601 or None (null=persistent)
        audit_ref        : Reference to FullTurnAuditRecord.turn_id
        embedding_vector : ME5-large (1024 dimensions), set after storage
        created_at       : ISO 8601 UTC
    """
    capsule_id:       str
    session_id:       str
    source_turn_ids:  list
    memory_text:      str
    memory_type:      str    # preference|goal|constraint|open_loop|stable_fact
    salience_score:   float
    audit_ref:        str    # FullTurnAuditRecord.turn_id
    created_at:       str
    ttl:              Optional[str] = None
    embedding_vector: Optional[list] = None  # Set after storage

    def __post_init__(self):
        if not self.created_at:
            self.created_at = _now_utc()

    def is_expired(self) -> bool:
        """Check whether TTL has been exceeded"""
        if self.ttl is None:
            return False
        try:
            expiry = datetime.fromisoformat(self.ttl)
            return datetime.now(timezone.utc) > expiry
        except ValueError:
            return False

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# ── Capsule Generator ───────────────────────────────────────────────────────

def generate_capsule(
    audit,                      # FullTurnAuditRecord
    session_state = None,       # SessionState (optional)
    response_summary: str = "", # Response summary text
) -> Optional[MemoryCapsule]:
    """
    Generate a MemoryCapsule from a FullTurnAuditRecord (spec §6.1).

    Processing flow:
      Step 1: Generation decision (_classify)
      Step 2: salience_score calculation (_score)
      Step 3: memory_text generation (_compose, no LLM)
      Step 4: Capsule object creation

    Args:
        audit           : FullTurnAuditRecord
        session_state   : SessionState (optional, for additional context)
        response_summary: Response summary text (used in _compose)

    Returns:
        MemoryCapsule or None (when not generating)
    """
    # Step 1: Generation decision
    memory_type = _classify(audit)
    if memory_type is None:
        return None

    # Step 2: salience_score calculation
    salience = _score(audit, memory_type)
    if salience < SALIENCE_THRESHOLD:
        return None

    # Step 3: memory_text generation (no LLM, template-based)
    memory_text = _compose(audit, memory_type, response_summary)
    if not memory_text.strip():
        return None

    # Step 4: TTL calculation
    ttl = _calc_ttl(audit, memory_type)

    return MemoryCapsule(
        capsule_id      = str(uuid.uuid4()),
        session_id      = audit.session_id,
        source_turn_ids = [audit.turn_id],
        memory_text     = memory_text,
        memory_type     = memory_type,
        salience_score  = round(salience, 4),
        audit_ref       = audit.turn_id,
        created_at      = _now_utc(),
        ttl             = ttl,
    )


# ── Internal methods ─────────────────────────────────────────────────────────

def _classify(audit) -> Optional[str]:
    """
    Determine memory_type from audit fields (spec §5).

    Returns:
        memory_type string, or None (do not generate)
    """
    route = audit.route_decision

    # clamped=True -> generation suppression (spec §5)
    if getattr(audit, "clamped", False):
        # SAFETY_CRITICAL is completely suppressed
        if "SAFETY_CRITICAL" in getattr(audit, "clamp_reasons", []):
            return None
        # Other clamps can be saved as short-term stable_fact
        return "stable_fact"

    # Get qk.longterm
    qk = getattr(audit, "qk", None)
    longterm = getattr(qk, "longterm", "ok") if qk else "ok"

    # Get primary_reason from decision_trace
    dt = getattr(audit, "decision_trace", None)
    primary_reason = getattr(dt, "primary_reason", "") if dt else ""
    primary_seat   = getattr(dt, "primary_seat",   "") if dt else ""

    # route_decision = ask -> open_loop (unresolved issue)
    if route == "ask":
        return "open_loop"

    # route_decision = verify (success/partial) -> stable_fact
    if route == "verify":
        eal_adm = getattr(audit, "eal_admissibility", "")
        if eal_adm in ("answerable", "bounded-only"):
            return "stable_fact"
        return None

    # qk.longterm = high -> goal / constraint / stable_fact
    if longterm == "high":
        if "CONSTRAINT" in primary_reason.upper() or primary_seat == "kernel":
            return "constraint"
        return "goal"

    # If reason_codes contains preference-related codes, return preference
    reason_codes = getattr(audit, "reason_codes", [])
    if any("PREFERENCE" in r.upper() for r in reason_codes):
        return "preference"

    # route = answer + longterm = ok -> stable_fact (delegate to salience scoring)
    if route == "answer" and longterm == "ok":
        return "stable_fact"

    return None


def _score(audit, memory_type: str) -> float:
    """
    Calculate salience_score (spec §5).

    Connection with KVS:
      - Low tvs (stable) -> salience up
      - High tvs (volatile) -> salience down
    """
    score = SALIENCE_BASE

    # Addition based on qk.longterm
    qk = getattr(audit, "qk", None)
    longterm = getattr(qk, "longterm", "ok") if qk else "ok"
    if longterm == "high":
        score += SALIENCE_LONGTERM_HIGH
    elif longterm == "ok":
        score += SALIENCE_LONGTERM_OK

    # verify_success -> verified facts have high reliability
    eal_adm = getattr(audit, "eal_admissibility", "")
    if eal_adm == "answerable" and audit.route_decision == "verify":
        score += SALIENCE_VERIFY_SUCCESS

    # KVS: adjustment by tvs (Future Fantasism suppression)
    kvs = getattr(audit, "kvs", None)
    if kvs is not None:
        tvs = getattr(kvs, "tvs", 0.5)
        if tvs < 0.3:
            score += SALIENCE_TVS_LOW_BONUS    # stable knowledge
        elif tvs > 0.7:
            score += SALIENCE_TVS_HIGH_PENALTY # volatile knowledge

    # Adjustment per memory_type
    if memory_type in ("goal", "constraint"):
        score += 0.05
    elif memory_type == "open_loop":
        score -= 0.05  # open_loop is set lower (temporary storage until resolved)

    # Lower salience when clamped
    if getattr(audit, "clamped", False):
        score -= 0.15

    return max(0.0, min(1.0, score))


def _compose(audit, memory_type: str, response_summary: str) -> str:
    """
    Generate memory_text using templates (no LLM).

    spec §6.1: Using an LLM would require ResourceLockManager's exclusive control, adding complexity.
    """
    route   = audit.route_decision
    session = audit.session_id[:8]  # Shortened ID
    turn    = audit.turn

    # Get primary_reason from decision_trace
    dt = getattr(audit, "decision_trace", None)
    primary_reason = getattr(dt, "primary_reason", "") if dt else ""
    notes = getattr(dt, "notes", []) if dt else []

    # qk
    qk = getattr(audit, "qk", None)
    longterm = getattr(qk, "longterm", "ok") if qk else "ok"
    intent   = getattr(qk, "intent",   "ok") if qk else "ok"

    eal_adm   = getattr(audit, "eal_admissibility", "")
    ret_src   = getattr(audit, "retrieval_source", "")

    templates = {
        "goal": (
            f"[Goal] Session {session} turn {turn}: "
            f"Long-term intent detected (longterm={longterm}, intent={intent}). "
            f"Route: {route}. "
            f"Reason: {primary_reason or 'unspecified'}. "
            f"{response_summary[:120] if response_summary else ''}"
        ).strip(),

        "constraint": (
            f"[Constraint] Session {session} turn {turn}: "
            f"Design constraint identified. "
            f"Route: {route}. "
            f"Reason: {primary_reason or 'unspecified'}. "
            f"Notes: {', '.join(notes[:3]) if notes else 'none'}. "
            f"{response_summary[:100] if response_summary else ''}"
        ).strip(),

        "preference": (
            f"[Preference] Session {session} turn {turn}: "
            f"User preference detected. "
            f"Route: {route}. "
            f"Reason: {primary_reason or 'unspecified'}. "
            f"{response_summary[:120] if response_summary else ''}"
        ).strip(),

        "open_loop": (
            f"[OpenLoop] Session {session} turn {turn}: "
            f"Unresolved question — clarification needed before proceeding. "
            f"Route: {route} (ask). "
            f"Reason: {primary_reason or 'unspecified'}. "
            f"{response_summary[:100] if response_summary else ''}"
        ).strip(),

        "stable_fact": (
            f"[StableFact] Session {session} turn {turn}: "
            f"Verified or stable information. "
            f"Route: {route}, EAL: {eal_adm or 'n/a'}, Source: {ret_src or 'n/a'}. "
            f"Reason: {primary_reason or 'unspecified'}. "
            f"{response_summary[:120] if response_summary else ''}"
        ).strip(),
    }

    return templates.get(memory_type, "")


def _calc_ttl(audit, memory_type: str) -> Optional[str]:
    """
    Calculate TTL.

    - If clamped=True, override with CLAMPED_TTL_DAYS days
    - If KVS.tvs is high, shorten ttl (Future Fantasism suppression)
    - Persistent types (goal/constraint/preference) return None
    """
    base_ttl_str = MEMORY_TYPES.get(memory_type, {}).get("default_ttl")

    # clamped -> forced short-term
    if getattr(audit, "clamped", False):
        expiry = datetime.now(timezone.utc) + timedelta(days=CLAMPED_TTL_DAYS)
        return expiry.isoformat()

    # High KVS.tvs -> shorten ttl (volatile knowledge is not retained long-term)
    kvs = getattr(audit, "kvs", None)
    if kvs is not None:
        tvs = getattr(kvs, "tvs", 0.5)
        if tvs > 0.7 and base_ttl_str is not None:
            # If volatility is high, shorten ttl by half
            days = _parse_ttl_days(base_ttl_str)
            if days:
                expiry = datetime.now(timezone.utc) + timedelta(days=days // 2)
                return expiry.isoformat()

    if base_ttl_str is None:
        return None  # persistent

    days = _parse_ttl_days(base_ttl_str)
    if days:
        expiry = datetime.now(timezone.utc) + timedelta(days=days)
        return expiry.isoformat()
    return None


def _parse_ttl_days(ttl_str: str) -> Optional[int]:
    """Parse strings like '30d' into 30"""
    if ttl_str and ttl_str.endswith("d"):
        try:
            return int(ttl_str[:-1])
        except ValueError:
            pass
    return None


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()
