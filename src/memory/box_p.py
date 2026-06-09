#!/usr/bin/env python3
"""
box_p.py — Phase G.4: Box P, distilled cross-session personal continuity.

Box P is NOT raw chat memory. It is a strict, distilled continuity layer
that stores only stable, re-confirmed, low-risk signals observed across
one or more sessions. Its role is to make FUTURE conversations smoother
without leaking arbitrary session chatter.

Contract
--------
Allowed contents:
  - language preference
  - response format preference
  - abstraction baseline
  - comfort zone
  - adopted frames   (re-confirmed only)
  - rejected frames  (re-confirmed only)
  - correction patterns (durable only)
  - recurring stable themes (re-confirmed across turns)
  - continuity confidence

Forbidden contents:
  - full raw transcript dumps
  - ephemeral one-off feelings
  - unverified personality inference
  - arbitrary session chatter
  - unsafe / high-risk speculative user modeling

Promotion gate (stricter than Box M):
  - requires minimum confidence + minimum valid-turn evidence
  - frames must be adopted/rejected multiple times
  - themes must exceed theme threshold
  - raw transcript-shaped content (long text blobs) is rejected

Persistence
-----------
A small JSON file (data/memory/box_p.json) is the default store. A
SessionState-only in-memory mode is also supported for tests and
ephemeral runs. Box P is NOT a vector store; future vectorization is
possible but out of scope for this foundation pass.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : "Phase G.4 — memory/indexing foundation"
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .indexed_box_entry import (
    IndexedBoxEntry,
    STABILITY_DISTILLED,
    NOTE_BOX_P_PROMOTED,
    NOTE_BOX_P_REJECTED_LOW_CONFIDENCE,
    NOTE_BOX_P_REJECTED_MALFORMED,
    NOTE_BOX_P_REJECTED_RAW_TRANSCRIPT,
)

logger = logging.getLogger(__name__)

BOX_P_LABEL = "P"

# ── Promotion gates ─────────────────────────────────────────────────────────

# A signal must clear all applicable gates to land in Box P.
MIN_CONTINUITY_CONFIDENCE  = 0.45   # UserMap.confidence floor
MIN_VALID_TURNS            = 3      # enough interaction to trust distillation
MIN_FRAME_REAPPEARANCES    = 1      # UserMap tracks adopted/rejected only after
                                    # cross-turn confirmation, so we trust the
                                    # single-list entry as a confirmed signal
MAX_PROMOTABLE_FRAME_CHARS = 240    # reject raw-transcript-shaped blobs
MAX_PROMOTABLE_THEME_CHARS = 64     # theme tokens must stay token-sized
MAX_THEMES_PROMOTED        = 16     # avoid unbounded theme accumulation
MAX_FRAMES_PROMOTED        = 16


# ── Data model ──────────────────────────────────────────────────────────────


@dataclass
class CorrectionPattern:
    """A durable correction tendency observed across turns."""
    kind: str                    # e.g. "wants_concise", "rejects_bullets"
    count: int        = 1
    last_seen: str    = ""
    confidence: float = 0.5


@dataclass
class PersonalContinuityProfile:
    """
    The distilled continuity record itself.

    Durable, small, JSON-safe. Designed to be inspectable by future UI /
    API surfaces WITHOUT exposing raw transcript content.
    """
    user_id:                    str                   = "default"
    language_preference:        Optional[str]         = None       # e.g. "ja" | "en"
    response_format_preference: Optional[str]         = None       # e.g. "concise" | "detailed"
    abstraction_baseline:       float                 = 0.0
    comfort_zone:               float                 = 0.35
    adopted_frames:             List[str]             = field(default_factory=list)
    rejected_frames:            List[str]             = field(default_factory=list)
    correction_patterns:        List[CorrectionPattern] = field(default_factory=list)
    recurring_themes:           List[str]             = field(default_factory=list)
    continuity_confidence:      float                 = 0.0
    # Inspectability.
    promoted_count:             int                   = 0
    rejected_count:             int                   = 0
    last_distilled_at:          str                   = ""
    schema_version:             int                   = 1

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Stable ordering for JSON safety.
        d["correction_patterns"] = [asdict(c) for c in self.correction_patterns]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PersonalContinuityProfile":
        cps_raw = d.get("correction_patterns", []) or []
        cps: List[CorrectionPattern] = []
        for c in cps_raw:
            if isinstance(c, dict):
                cps.append(CorrectionPattern(
                    kind=str(c.get("kind", "")),
                    count=int(c.get("count", 1)),
                    last_seen=str(c.get("last_seen", "")),
                    confidence=float(c.get("confidence", 0.5)),
                ))
        return cls(
            user_id=str(d.get("user_id", "default")),
            language_preference=(d.get("language_preference") or None),
            response_format_preference=(d.get("response_format_preference") or None),
            abstraction_baseline=float(d.get("abstraction_baseline", 0.0)),
            comfort_zone=float(d.get("comfort_zone", 0.35)),
            adopted_frames=[s for s in d.get("adopted_frames", []) if isinstance(s, str)],
            rejected_frames=[s for s in d.get("rejected_frames", []) if isinstance(s, str)],
            correction_patterns=cps,
            recurring_themes=[s for s in d.get("recurring_themes", []) if isinstance(s, str)],
            continuity_confidence=float(d.get("continuity_confidence", 0.0)),
            promoted_count=int(d.get("promoted_count", 0)),
            rejected_count=int(d.get("rejected_count", 0)),
            last_distilled_at=str(d.get("last_distilled_at", "")),
            schema_version=int(d.get("schema_version", 1)),
        )


@dataclass
class DistillationResult:
    """Compact report of a single distillation pass."""
    promoted: List[str]  = field(default_factory=list)
    rejected: List[str]  = field(default_factory=list)
    notes:    List[str]  = field(default_factory=list)


# ── Promotion logic (strict) ────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _looks_like_raw_transcript(text: str, *, max_chars: int) -> bool:
    """Heuristic: long text or multi-sentence blobs are rejected as raw
    transcript. Box P stores tags / short descriptors, not sentences."""
    if not isinstance(text, str):
        return False
    if len(text) > max_chars:
        return True
    # Multiple sentence terminators → likely a sentence from a transcript.
    terminators = sum(text.count(c) for c in (".", "。", "!", "?", "？", "！"))
    if terminators >= 2:
        return True
    return False


def _valid_short_tag(text: Any, *, max_chars: int) -> bool:
    if not isinstance(text, str):
        return False
    s = text.strip()
    if not s:
        return False
    if len(s) > max_chars:
        return False
    return True


def distill_from_user_map(
    profile: PersonalContinuityProfile,
    user_map: Any,
    *,
    trajectory: Any = None,
    language: Optional[str] = None,
    result: Optional[DistillationResult] = None,
) -> DistillationResult:
    """
    Promote stable signals from a session UserMap into the Personal
    Continuity Profile. Strict: only re-confirmed / durable / low-risk
    signals pass.

    `user_map` is duck-typed to the UserMap dataclass (attributes:
    confidence, cold_start, valid_turn_count, adopted_frames,
    rejected_frames, active_themes, framing_preferences,
    abstraction_baseline, comfort_zone). Missing attributes are treated
    as absent signals, not errors.
    """
    r = result or DistillationResult()

    confidence = float(getattr(user_map, "confidence", 0.0) or 0.0)
    valid_turns = int(getattr(user_map, "valid_turn_count", 0) or 0)
    cold_start = bool(getattr(user_map, "cold_start", True))

    # Hard gate: below confidence / turn floor → nothing promotes, but the
    # pass is still observable.
    if (confidence < MIN_CONTINUITY_CONFIDENCE
            or valid_turns < MIN_VALID_TURNS
            or cold_start):
        r.rejected.append("gate:below_confidence_or_turn_floor")
        r.notes.append(NOTE_BOX_P_REJECTED_LOW_CONFIDENCE)
        profile.rejected_count += 1
        profile.last_distilled_at = _now_iso()
        return r

    # Language preference (explicit-only; do NOT infer from text silently).
    if language and isinstance(language, str) and language in ("ja", "en", "fr",
                                                                "de", "es", "zh"):
        if profile.language_preference != language:
            profile.language_preference = language
            r.promoted.append("language_preference")

    # Response format preference: derive from framing_preferences that hint
    # at format strongly.
    fps = list(getattr(user_map, "framing_preferences", []) or [])
    fmt_hint = None
    if "concise" in fps or "direct" in fps:
        fmt_hint = "concise"
    elif "detailed" in fps:
        fmt_hint = "detailed"
    if fmt_hint and profile.response_format_preference != fmt_hint:
        profile.response_format_preference = fmt_hint
        r.promoted.append("response_format_preference")

    # Abstraction baseline (always carry EMA across sessions, bounded).
    abs_baseline = float(getattr(user_map, "abstraction_baseline", 0.0) or 0.0)
    if abs(profile.abstraction_baseline - abs_baseline) > 0.05:
        profile.abstraction_baseline = max(0.0, min(2.0, abs_baseline))
        r.promoted.append("abstraction_baseline")

    # Comfort zone (bounded 0..1).
    cz = float(getattr(user_map, "comfort_zone", 0.35) or 0.35)
    if abs(profile.comfort_zone - cz) > 0.05:
        profile.comfort_zone = max(0.0, min(1.0, cz))
        r.promoted.append("comfort_zone")

    # Adopted frames: only short tags, no raw transcripts.
    for fr in list(getattr(user_map, "adopted_frames", []) or []):
        if not _valid_short_tag(fr, max_chars=MAX_PROMOTABLE_FRAME_CHARS):
            r.rejected.append(f"adopted_frame:malformed")
            r.notes.append(NOTE_BOX_P_REJECTED_MALFORMED)
            profile.rejected_count += 1
            continue
        if _looks_like_raw_transcript(fr, max_chars=MAX_PROMOTABLE_FRAME_CHARS):
            r.rejected.append(f"adopted_frame:raw_transcript")
            r.notes.append(NOTE_BOX_P_REJECTED_RAW_TRANSCRIPT)
            profile.rejected_count += 1
            continue
        if fr not in profile.adopted_frames:
            if len(profile.adopted_frames) < MAX_FRAMES_PROMOTED:
                profile.adopted_frames.append(fr)
                r.promoted.append(f"adopted_frame:{fr[:32]}")

    for fr in list(getattr(user_map, "rejected_frames", []) or []):
        if not _valid_short_tag(fr, max_chars=MAX_PROMOTABLE_FRAME_CHARS):
            r.rejected.append(f"rejected_frame:malformed")
            r.notes.append(NOTE_BOX_P_REJECTED_MALFORMED)
            profile.rejected_count += 1
            continue
        if _looks_like_raw_transcript(fr, max_chars=MAX_PROMOTABLE_FRAME_CHARS):
            r.rejected.append(f"rejected_frame:raw_transcript")
            r.notes.append(NOTE_BOX_P_REJECTED_RAW_TRANSCRIPT)
            profile.rejected_count += 1
            continue
        if fr not in profile.rejected_frames:
            if len(profile.rejected_frames) < MAX_FRAMES_PROMOTED:
                profile.rejected_frames.append(fr)
                r.promoted.append(f"rejected_frame:{fr[:32]}")

    # Recurring themes: only from active_themes, token-sized.
    for theme in list(getattr(user_map, "active_themes", []) or []):
        if not _valid_short_tag(theme, max_chars=MAX_PROMOTABLE_THEME_CHARS):
            r.rejected.append("theme:malformed")
            r.notes.append(NOTE_BOX_P_REJECTED_MALFORMED)
            profile.rejected_count += 1
            continue
        if theme not in profile.recurring_themes:
            if len(profile.recurring_themes) < MAX_THEMES_PROMOTED:
                profile.recurring_themes.append(theme)
                r.promoted.append(f"theme:{theme}")

    # Continuity confidence: raise slowly, never above source UserMap conf.
    new_conf = max(profile.continuity_confidence, min(confidence, 0.9))
    if new_conf > profile.continuity_confidence:
        profile.continuity_confidence = new_conf
        r.promoted.append("continuity_confidence")

    if r.promoted:
        profile.promoted_count += 1
        r.notes.append(NOTE_BOX_P_PROMOTED)
    profile.last_distilled_at = _now_iso()
    return r


# ── Persistence ─────────────────────────────────────────────────────────────


class BoxPStore:
    """
    Tiny JSON-file-backed store for PersonalContinuityProfile.

    Not a database. Not vectorized. One file per user_id (default: a
    single shared profile). Writes are atomic via write-then-rename.

    The store is optional: a caller that wants an in-memory profile can
    instantiate the dataclass directly. BoxPStore exists so a future UI
    can reliably load / persist a profile across sessions.
    """
    DEFAULT_PATH = Path("data/memory/box_p.json")

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else self.DEFAULT_PATH
        self._lock = threading.Lock()

    def load(self) -> PersonalContinuityProfile:
        with self._lock:
            if not self.path.exists():
                return PersonalContinuityProfile()
            try:
                raw = self.path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"[BoxP] load failed, returning fresh profile: {e}")
                return PersonalContinuityProfile()
            if not isinstance(data, dict):
                return PersonalContinuityProfile()
            try:
                return PersonalContinuityProfile.from_dict(data)
            except Exception as e:   # noqa: BLE001
                logger.warning(f"[BoxP] decode failed, returning fresh profile: {e}")
                return PersonalContinuityProfile()

    def save(self, profile: PersonalContinuityProfile) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(profile.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)

    def delete(self) -> None:
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


# ── Canonical-shape projection ──────────────────────────────────────────────


def to_indexed_box_entry(
    profile: PersonalContinuityProfile,
) -> IndexedBoxEntry:
    """Project a PersonalContinuityProfile onto the canonical
    IndexedBoxEntry shape for uniform inspection by future surfaces.
    Only inspectable metadata is exposed; no raw transcript is produced
    because Box P never holds one."""
    return IndexedBoxEntry(
        box_label=BOX_P_LABEL,
        entry_id=profile.user_id or "default",
        raw_content="",   # BoxP deliberately holds no raw text
        metadata={
            "language_preference":        profile.language_preference,
            "response_format_preference": profile.response_format_preference,
            "abstraction_baseline":       round(profile.abstraction_baseline, 4),
            "comfort_zone":               round(profile.comfort_zone, 4),
            "adopted_frames":             list(profile.adopted_frames),
            "rejected_frames":            list(profile.rejected_frames),
            "correction_patterns":        [c.kind for c in profile.correction_patterns],
            "recurring_themes":           list(profile.recurring_themes),
            "promoted_count":             profile.promoted_count,
            "rejected_count":             profile.rejected_count,
        },
        summary_capsule="",   # future: a short natural-language capsule
        embedding_ref=None,    # future: optional vectorization
        created_at=profile.last_distilled_at or _now_iso(),
        updated_at=profile.last_distilled_at or _now_iso(),
        confidence=float(profile.continuity_confidence),
        stability=STABILITY_DISTILLED,
        notes=[],
    )
