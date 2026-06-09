from __future__ import annotations
from src.kernel.rgc import RGCState as _RGCState

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional


@dataclass
class Correction:
    turn:       int
    field:      str
    old_value:  Optional[str]
    new_value:  str
    applied_by: str = "user"   # "user" | "system"


# ── M-1: InstantMemory (session-scoped, volatile) ───────────────────────────

@dataclass
class InstantMemory:
    """
    Session-scoped volatile memory.
    Destroyed at session end / Clear.

    Purpose: coreference resolution for search query
    rewriting ONLY. Not injected into LLM prompts.
    conversation_turns handles LLM context separately.
    """
    entity_map: dict = field(default_factory=dict)
    entity_stack: list = field(default_factory=list)
    current_domain: str = ""

    def register_entity(self, entity: str) -> None:
        if entity not in self.entity_stack:
            self.entity_stack.insert(0, entity)
            self.entity_stack = self.entity_stack[:5]

    def register_reference(self, ref: str, entity: str) -> None:
        self.entity_map[ref] = entity

    def resolve_query(self, query: str) -> str:
        """
        Rewrite query by replacing pronouns with entities.
        Used ONLY for search query generation.
        """
        resolved = query
        for ref, entity in self.entity_map.items():
            resolved = resolved.replace(ref, entity)
        return resolved

    def clear(self) -> None:
        self.entity_map.clear()
        self.entity_stack.clear()
        self.current_domain = ""


# ── M-2: UserProfileMemory (long-term, adaptive) ────────────────────────────

@dataclass
class UserProfileMemory:
    """
    Long-term user profile memory. Persists across sessions.
    Scope: language and explanation depth only.
    Domain expertise scoring deferred to v4.
    """
    preferred_language: str = "ja"
    explanation_depth: str = "standard"  # "brief" | "standard" | "detailed"
    last_updated: str = ""

    def apply_to_prompt(self) -> str:
        depth_map = {
            "brief": "Keep response concise.",
            "standard": "",
            "detailed": "Provide detailed explanation.",
        }
        return depth_map.get(self.explanation_depth, "")


# ── M-3: VerifiedFactsMemory (long-term, near-permanent) ────────────────────

@dataclass
class VerifiedFact:
    """
    A single EAL-verified fact.
    Only facts with TVS < 0.3 are stored.
    """
    claim: str
    source_label: str
    tvs: float
    verified_at: str
    confidence: float


@dataclass
class VerifiedFactsMemory:
    """
    Long-term storage of EAL-verified stable facts.
    Constraint: TVS < 0.3 ONLY.
    """
    facts: list = field(default_factory=list)
    TVS_CEILING: float = field(default=0.3, init=False, repr=False)

    def store(self, claim: str, source_label: str, tvs: float, confidence: float) -> bool:
        if tvs >= self.TVS_CEILING:
            return False
        fact = VerifiedFact(
            claim=claim, source_label=source_label, tvs=tvs,
            verified_at=datetime.now(timezone.utc).isoformat(),
            confidence=confidence,
        )
        self.facts = [f for f in self.facts if f.claim != claim]
        self.facts.append(fact)
        return True

    def retrieve(self, query: str, threshold: float = 0.6):
        q_lower = query.lower()
        return [
            f for f in self.facts
            if any(w in q_lower for w in f.claim.lower().split() if len(w) > 3)
        ]


# ── SessionState ─────────────────────────────────────────────────────────────

@dataclass
class SessionState:
    session_id:          str             = field(default_factory=lambda: str(uuid.uuid4()))
    active_language:     str             = "en"
    facts:               List[str]       = field(default_factory=list)
    assumptions:         List[str]       = field(default_factory=list)
    open_questions:      List[str]       = field(default_factory=list)
    constraints:         List[str]       = field(default_factory=list)
    corrections:         List[Correction]= field(default_factory=list)
    route_history:       List[Dict[str, Any]] = field(default_factory=list)
    conversation_turns:  List[Dict[str, str]] = field(default_factory=list)
    rgc_state:           object          = field(default_factory=_RGCState)
    summary:             str             = ""
    # Memory layers
    instant_memory:      InstantMemory        = field(default_factory=InstantMemory)
    user_profile:        UserProfileMemory    = field(default_factory=UserProfileMemory)
    verified_facts:      VerifiedFactsMemory  = field(default_factory=VerifiedFactsMemory)

    # ── Phase E: L3 UserMap / Trajectory (lazy, session-scoped) ──────────────
    # Intentionally typed as Optional[Any] to avoid circular imports.
    # Populated on first access via ensure_user_map() / ensure_trajectory().
    user_map:            Optional[Any]   = None
    trajectory_state:    Optional[Any]   = None

    # ── Phase G foundation: AuthorityProfile / RetrievalProfile IDs ──────────
    # Internal carriers for future UI / API profile selection. Empty string
    # means "no explicit selection" → runtime resolves to balanced_default.
    # The *_effective_* fields are written by the runtime each turn so they
    # are inspectable even when the selected_* fields are left blank.
    #
    # Phase G.3: selected_* fields always hold a canonical value (empty str
    # or a registered preset id). Callers MUST go through
    # `apply_profile_selection()` to set these fields safely; direct writes
    # are tolerated but bypass validation and audit.
    selected_authority_profile_id:  str = ""
    selected_retrieval_profile_id:  str = ""
    effective_authority_profile_id: str = ""
    effective_retrieval_profile_id: str = ""

    # Phase G.3: compact, capped audit log of profile-selection events
    # (normalization / fallback). Session-scoped; survives export/import.
    profile_selection_notes: List[str] = field(default_factory=list)

    # ── Phase G.5: carryover / checkpoint state ──────────────────────────────
    # Default = carryover allowed. When opt-out is True, no promotion into
    # Box P is allowed from this session even if a natural checkpoint
    # fires. M continues to function normally inside the active session.
    carryover_opt_out:            bool        = False
    # Compact, capped audit log of carryover events. Session-scoped;
    # serialization-safe.
    carryover_notes:              List[str]   = field(default_factory=list)
    # Last checkpoint evaluation snapshot (small dict; no raw transcript).
    # Populated by the caller via record_checkpoint_evaluation().
    last_checkpoint_evaluation:   Optional[Dict[str, Any]] = None
    # Phase G.6: durable pending carryover candidate (JSON-safe dict form
    # produced by `carryover.candidate_to_dict`). Distilled-only. Never
    # holds raw transcript. None when no candidate is pending.
    pending_carryover_candidate:  Optional[Dict[str, Any]] = None
    # Phase G.6: turn number at which the last automatic checkpoint fired.
    # Used by `maybe_checkpoint` to debounce across turns. Persisted.
    _last_checkpoint_turn:        int = 0

    # ── Phase E lazy accessors ───────────────────────────────────────────────

    def ensure_user_map(self):
        """Return the session's UserMap, creating it if absent (lazy)."""
        if self.user_map is None:
            from src.memory.user_map import UserMap  # local import to avoid cycle
            self.user_map = UserMap()
        return self.user_map

    def ensure_trajectory(self):
        """Return the session's TrajectoryState, creating it if absent (lazy)."""
        if self.trajectory_state is None:
            from src.memory.trajectory_state import TrajectoryState  # local import
            self.trajectory_state = TrajectoryState(session_id=self.session_id)
        return self.trajectory_state

    # ── Phase G.5: carryover opt-out helpers ─────────────────────────────────

    _CARRYOVER_NOTES_CAP: ClassVar[int] = 64

    def enable_carryover(self) -> None:
        """Re-enable carryover for this session. Does NOT retroactively
        promote previously blocked candidates — only future checkpoints
        become eligible."""
        was = self.carryover_opt_out
        self.carryover_opt_out = False
        if was:
            from src.memory.indexed_box_entry import (
                NOTE_CARRYOVER_OPT_OUT_DISABLED,
            )
            self._append_carryover_note(NOTE_CARRYOVER_OPT_OUT_DISABLED)

    def disable_carryover(self) -> None:
        """Opt this session out of carryover. Future checkpoints will
        still be evaluated for inspectability but will NOT promote into
        Box P. Active-session M continuity is not affected.

        Phase G.6: also invalidates any currently-promotable pending
        candidate so the UI immediately reflects the opt-out choice."""
        was = self.carryover_opt_out
        self.carryover_opt_out = True
        if not was:
            from src.memory.indexed_box_entry import (
                NOTE_CARRYOVER_OPT_OUT_ENABLED,
            )
            self._append_carryover_note(NOTE_CARRYOVER_OPT_OUT_ENABLED)
        try:
            from src.memory.carryover import invalidate_pending_on_opt_out
            invalidate_pending_on_opt_out(self)
        except Exception:   # noqa: BLE001
            pass

    def set_carryover(self, allowed: bool) -> None:
        """Convenience: allowed=True → enable; allowed=False → opt out."""
        if allowed:
            self.enable_carryover()
        else:
            self.disable_carryover()

    def _append_carryover_note(self, note: str) -> None:
        if not isinstance(note, str) or not note:
            return
        self.carryover_notes.append(note)
        cap = self._CARRYOVER_NOTES_CAP
        if len(self.carryover_notes) > cap:
            self.carryover_notes = self.carryover_notes[-cap:]

    def record_checkpoint_evaluation(self, evaluation) -> None:
        """Record a CheckpointEvaluation on this session for inspection.
        Accepts either a CheckpointEvaluation dataclass or a dict.
        Never raises; unknown inputs are coerced to the safe default."""
        try:
            if hasattr(evaluation, "to_dict"):
                self.last_checkpoint_evaluation = evaluation.to_dict()
            elif isinstance(evaluation, dict):
                self.last_checkpoint_evaluation = dict(evaluation)
            else:
                return
            for n in self.last_checkpoint_evaluation.get("notes", []) or []:
                self._append_carryover_note(n)
        except Exception:   # noqa: BLE001
            return

    def carryover_status(self) -> Dict[str, Any]:
        """Compact status dict for UI/trace inspection. Always safe."""
        return {
            "carryover_opt_out":         bool(self.carryover_opt_out),
            "carryover_allowed":         (not bool(self.carryover_opt_out)),
            "last_checkpoint_outcome":   (
                (self.last_checkpoint_evaluation or {}).get("outcome")
                if self.last_checkpoint_evaluation is not None else None
            ),
            "carryover_notes_count":     len(self.carryover_notes),
        }

    # ── Phase G.4: Box P lazy accessor ───────────────────────────────────────

    def ensure_box_p(self, *, store=None):
        """
        Return the session's view of the PersonalContinuityProfile.

        Lazy and non-invasive: if a caller passes an explicit `store`
        (a `BoxPStore`), the profile is loaded from it; otherwise an
        empty in-memory profile is created. Box P persistence is
        optional and session-scoped by default; callers that want
        cross-session persistence pass an explicit BoxPStore.
        """
        if getattr(self, "_box_p_profile", None) is None:
            from src.memory.box_p import PersonalContinuityProfile
            if store is not None:
                try:
                    self._box_p_profile = store.load()
                except Exception:   # noqa: BLE001
                    self._box_p_profile = PersonalContinuityProfile()
            else:
                self._box_p_profile = PersonalContinuityProfile()
        return self._box_p_profile

    def build_memory_fit(
        self,
        *,
        meta_recall_mode: bool = False,
        topic_risk: float = 0.3,
    ):
        """
        Construct a MemoryFitState snapshot for synthesis.
        This is a read-only projection; SessionState remains the source of truth.
        """
        from src.memory.meta_recall import (
            MemoryFitState,
            compute_halfstep_strength,
            halfstep_policy_from_strength,
        )
        um = self.ensure_user_map()
        tr = self.ensure_trajectory()
        strength = compute_halfstep_strength(
            comfort_zone=um.comfort_zone,
            fit_confidence=um.confidence,
            topic_risk=topic_risk,
        )
        # Over-leading guard: damp strength when recent corrections dominate
        olr = tr.over_leading_rate()
        if olr >= 0.5:
            strength = max(0.0, strength - 0.15)
        policy = halfstep_policy_from_strength(strength, cold_start=um.cold_start)
        return MemoryFitState(
            user_map=um,
            trajectory=tr,
            meta_recall_mode=meta_recall_mode,
            cold_start=um.cold_start,
            fit_confidence=um.confidence,
            halfstep_strength=strength,
            halfstep_policy=policy,
        )

    # ── Route recording ──────────────────────────────────────────────────────

    def record_route(self, route_record: Dict[str, Any]) -> None:
        route_record.setdefault("turn", len(self.route_history) + 1)
        route_record.setdefault("active_language", self.active_language)
        self.route_history.append(route_record)

    @property
    def current_turn(self) -> int:
        return len(self.route_history)

    # ── Correction / repair ──────────────────────────────────────────────────

    def apply_correction(self, field_name: str, new_value: str, applied_by: str = "user") -> None:
        old_value: Optional[str] = None
        if field_name == "summary":
            old_value = self.summary
            self.summary = new_value
        elif field_name in ("facts", "assumptions", "open_questions", "constraints"):
            lst = getattr(self, field_name)
            old_value = None
            lst.append(new_value)
        else:
            raise ValueError(f"Unsupported correction field: {field_name}")
        self.corrections.append(Correction(
            turn=self.current_turn, field=field_name,
            old_value=old_value, new_value=new_value, applied_by=applied_by,
        ))

    # ── Verified correction ──────────────────────────────────────────────────

    def record_verified_correction(self, claim: str, source: str = "") -> None:
        entry = f"[verified] {claim}" + (f" (source: {source})" if source else "")
        if entry not in self.facts:
            self.facts.append(entry)

    # ── M-1: Entity extraction ───────────────────────────────────────────────

    def extract_entities_from_turn(self, user_text: str, assistant_text: str) -> None:
        """
        Extract named entities from a completed turn and register in M-1.
        Pattern-based only — no NLP libraries.
        """
        # Japanese katakana sequences (proper nouns)
        for k in re.findall(r'[ァ-ヴー]{2,}', assistant_text):
            self.instant_memory.register_entity(k)
        # English capitalized words (3+ chars)
        for c in re.findall(r'\b[A-Z][a-z]{2,}\b', assistant_text):
            self.instant_memory.register_entity(c)
        # Map common pronouns to latest entity
        if self.instant_memory.entity_stack:
            latest = self.instant_memory.entity_stack[0]
            for ref in ["彼", "彼女", "それ", "この人", "he", "she", "they", "it"]:
                self.instant_memory.register_reference(ref, latest)

    # ── Phase G.3: canonical profile selection helpers ──────────────────────

    _PROFILE_SELECTION_NOTES_CAP: ClassVar[int] = 64

    def apply_profile_selection(
        self,
        authority_profile_id: Any = None,
        retrieval_profile_id: Any = None,
    ):
        """
        Canonical internal entry point to set selected profile IDs.

        Policy (spec §6B, option 2 — normalize on write):
          - None / ""            → selected field left as "" (ordinary
                                   no-selection case; resolves to
                                   balanced_default at runtime).
          - Valid preset id      → stored as-is.
          - Unknown / malformed  → stored as `balanced_default` (canonical
                                   normalized value); the original request
                                   is preserved only via the returned
                                   `ProfileSelectionResult` and the
                                   `profile_selection_notes` audit log.

        Returns a `ProfileSelectionResult` describing the request + outcome.
        Never raises.
        """
        from src.kernel.profiles import (
            normalize_profile_selection, BALANCED_DEFAULT_ID as _BD,
        )
        sel = normalize_profile_selection(
            authority_profile_id, retrieval_profile_id, source="session",
        )
        # Policy 2: leave "" when no selection was requested, otherwise
        # store the normalized canonical id (valid or balanced_default).
        self.selected_authority_profile_id = (
            "" if (authority_profile_id is None or authority_profile_id == "")
            else sel.normalized_authority_profile_id
        )
        self.selected_retrieval_profile_id = (
            "" if (retrieval_profile_id is None or retrieval_profile_id == "")
            else sel.normalized_retrieval_profile_id
        )
        for note in sel.notes:
            self._append_profile_selection_note(note)
        return sel

    def clear_profile_selection(self) -> None:
        """Reset selected profile IDs to empty (→ balanced_default at resolve
        time). Emits an inspectable note."""
        self.selected_authority_profile_id = ""
        self.selected_retrieval_profile_id = ""
        self._append_profile_selection_note("profile_selection_cleared")

    def _append_profile_selection_note(self, note: str) -> None:
        """Append a note with a per-session cap to prevent unbounded growth."""
        if not isinstance(note, str) or not note:
            return
        self.profile_selection_notes.append(note)
        # Cap: keep the tail. Session-scoped audit, not a full history.
        cap = self._PROFILE_SELECTION_NOTES_CAP
        if len(self.profile_selection_notes) > cap:
            self.profile_selection_notes = self.profile_selection_notes[-cap:]

    # ── Export / import ──────────────────────────────────────────────────────

    def export_json(self) -> str:
        data = asdict(self)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @classmethod
    def import_json(cls, json_str: str) -> "SessionState":
        data = json.loads(json_str)
        corrections_raw = data.pop("corrections", [])
        # Phase E: drop serialized user_map/trajectory_state on import; they are
        # session-scoped and will be re-built lazily. Keeps round-trip stable
        # even if future upgrades change the UserMap schema.
        data.pop("user_map", None)
        data.pop("trajectory_state", None)
        # Phase G.3: sanitize profile fields before construction so malformed
        # values in older/foreign JSON do not poison the new SessionState.
        cls._sanitize_profile_fields_in_place(data)
        state = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        state.corrections = [Correction(**c) for c in corrections_raw]
        # Phase G.6: if a pending candidate survived the import, emit a
        # compact inspectable note. If it was malformed (coerced to None
        # above while a non-dict was present), emit the fallback note.
        try:
            from src.memory.carryover import (
                candidate_from_dict as _cand_from_dict,
            )
            from src.memory.indexed_box_entry import (
                NOTE_CARRYOVER_PENDING_RESTORED as _NR,
                NOTE_CARRYOVER_PENDING_MALFORMED as _NM,
            )
            raw_pend = state.pending_carryover_candidate
            if isinstance(raw_pend, dict) and raw_pend:
                if _cand_from_dict(raw_pend) is None:
                    state.pending_carryover_candidate = None
                    state._append_carryover_note(_NM)
                else:
                    state._append_carryover_note(_NR)
        except Exception:   # noqa: BLE001
            pass
        return state

    @staticmethod
    def _sanitize_profile_fields_in_place(data: Dict[str, Any]) -> None:
        """Phase G.3: coerce malformed profile fields to safe defaults.

        Called only on the import path. Older sessions without these fields
        (dataclass default picks up "") and sessions with garbage values
        (non-string, unknown id) both degrade cleanly. Non-fatal by design.
        """
        # String-typed profile id fields: non-strings → "" (→ balanced_default).
        for k in (
            "selected_authority_profile_id",
            "selected_retrieval_profile_id",
            "effective_authority_profile_id",
            "effective_retrieval_profile_id",
        ):
            v = data.get(k, None)
            if v is None:
                data.pop(k, None)   # let dataclass default take over
            elif not isinstance(v, str):
                data[k] = ""
        # Notes list: coerce to list[str]; drop non-string entries.
        raw_notes = data.get("profile_selection_notes", None)
        if raw_notes is None:
            data.pop("profile_selection_notes", None)
        elif not isinstance(raw_notes, list):
            data["profile_selection_notes"] = []
        else:
            data["profile_selection_notes"] = [
                n for n in raw_notes if isinstance(n, str)
            ]
        # Phase G.5: carryover fields safety.
        v = data.get("carryover_opt_out", None)
        if v is None:
            data.pop("carryover_opt_out", None)
        elif not isinstance(v, bool):
            data["carryover_opt_out"] = bool(v) if isinstance(v, (int, str)) else False
        raw_cnotes = data.get("carryover_notes", None)
        if raw_cnotes is None:
            data.pop("carryover_notes", None)
        elif not isinstance(raw_cnotes, list):
            data["carryover_notes"] = []
        else:
            data["carryover_notes"] = [
                n for n in raw_cnotes if isinstance(n, str)
            ]
        raw_ce = data.get("last_checkpoint_evaluation", None)
        if raw_ce is None:
            data.pop("last_checkpoint_evaluation", None)
        elif not isinstance(raw_ce, dict):
            data["last_checkpoint_evaluation"] = None
        # Phase G.6: pending_carryover_candidate must be a dict or None.
        raw_pending = data.get("pending_carryover_candidate", None)
        if raw_pending is None:
            data.pop("pending_carryover_candidate", None)
        elif not isinstance(raw_pending, dict):
            data["pending_carryover_candidate"] = None
        # Phase G.6: _last_checkpoint_turn must be a non-negative int.
        raw_lct = data.get("_last_checkpoint_turn", None)
        if raw_lct is None:
            data.pop("_last_checkpoint_turn", None)
        else:
            try:
                data["_last_checkpoint_turn"] = max(0, int(raw_lct))
            except (TypeError, ValueError):
                data["_last_checkpoint_turn"] = 0
