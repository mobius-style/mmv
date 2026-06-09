#!/usr/bin/env python3
"""
box_s_quarantine.py — Phase G.4: Box S as an ephemeral quarantine workspace.

Box S is **not a cache**. It is a quarantine layer that holds compact
judgment metadata about external-search results so the runtime can:
  - recall "we already saw this and rejected it" within a short window
  - avoid re-promoting known-weak results
  - expose inspectable accept/reject reasons to future UI surfaces

What Box S does NOT do:
  - persist raw search result bodies as long-lived knowledge
  - vectorize external search content
  - feed "cache hits" back into the retrieval pipeline as trusted sources
  - share any space with Box W (Wikipedia) or Box A (user workspace)

Storage model:
  - bounded in-memory ring buffer (FIFO)
  - short default TTL (minutes, not hours)
  - acceptance/rejection is the primary durable signal; body is transient
  - no disk persistence by default (future UI may opt-in)

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : "Phase G.4 — memory/indexing foundation"
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional

from .indexed_box_entry import (
    NOTE_BOX_S_QUARANTINE_RECORDED,
    NOTE_BOX_S_RESULT_REJECTED,
    NOTE_BOX_S_QUARANTINE_EXPIRED,
)

logger = logging.getLogger(__name__)

BOX_S_LABEL = "S"

# Defaults: quarantine-scoped, not cache-scoped.
DEFAULT_TTL_SECONDS = 15 * 60       # 15 minutes — short-lived by design
DEFAULT_MAX_ENTRIES = 128           # bounded ring buffer


# Judgment enum-like strings.
JUDGMENT_ACCEPTED = "accepted"      # used in this turn (still transient)
JUDGMENT_REJECTED = "rejected"      # explicitly discarded
JUDGMENT_USEFUL   = "useful"        # compact meta-useful, did not need body
JUDGMENT_USELESS  = "useless"       # low quality, must not be re-promoted


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _fingerprint_query(query: str) -> str:
    """Short deterministic fingerprint; avoids storing raw query body
    when inspected in external tooling. 12 hex chars (~48 bits) is
    enough for collision-free dedup within a single session ring."""
    h = hashlib.sha256((query or "").strip().lower().encode("utf-8")).hexdigest()
    return h[:12]


@dataclass
class SearchResultMeta:
    """Per-result metadata only — deliberately no body text.

    Stored as a short descriptor so a future UI can show "we saw this URL
    and rejected it" without rehydrating weak external content."""
    url:   str = ""
    title: str = ""
    score: Optional[float] = None


@dataclass
class SearchQuarantineEntry:
    """
    Compact judgment record for one external-search call.

    Holds enough to identify "we've seen this query/result" and why we
    judged it the way we did. Does NOT hold raw synthesis or full body
    text — those are explicitly ephemeral.
    """
    query_fingerprint: str
    judgment:          str                       # accepted | rejected | useful | useless
    created_at:        str                       = field(default_factory=lambda: _iso(_now()))
    ttl_seconds:       int                       = DEFAULT_TTL_SECONDS
    result_meta:       List[SearchResultMeta]    = field(default_factory=list)
    reason:            str                       = ""       # short reason tag
    notes:             List[str]                 = field(default_factory=list)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or _now()
        try:
            created = datetime.fromisoformat(self.created_at)
        except Exception:   # noqa: BLE001
            return True
        return (now - created) > timedelta(seconds=max(0, int(self.ttl_seconds)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_fingerprint": self.query_fingerprint,
            "judgment":          self.judgment,
            "created_at":        self.created_at,
            "ttl_seconds":       int(self.ttl_seconds),
            "result_meta":       [asdict(r) for r in self.result_meta],
            "reason":            self.reason,
            "notes":             list(self.notes),
        }


class BoxSQuarantineStore:
    """
    Bounded, TTL-aware in-memory ring for SearchQuarantineEntry.

    Thread-safe for concurrent read/write. No disk persistence: Box S is
    a quarantine workspace, not a durable knowledge box.
    """
    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        default_ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._ring: Deque[SearchQuarantineEntry] = deque(maxlen=max_entries)
        self._default_ttl = int(default_ttl_seconds)
        self._lock = threading.Lock()

    # ── Recording ────────────────────────────────────────────────────────────

    def record(
        self,
        *,
        query: str,
        judgment: str,
        result_meta: Optional[List[SearchResultMeta]] = None,
        reason: str = "",
        ttl_seconds: Optional[int] = None,
    ) -> SearchQuarantineEntry:
        """Record a judgment event for an external-search call.

        Never raises on bad input. Unknown judgments are coerced to
        'rejected' with an inspectable reason tag."""
        if judgment not in (JUDGMENT_ACCEPTED, JUDGMENT_REJECTED,
                            JUDGMENT_USEFUL, JUDGMENT_USELESS):
            reason = (reason + " " if reason else "") + f"unknown_judgment:{judgment!r}"
            judgment = JUDGMENT_REJECTED
        notes: List[str] = [NOTE_BOX_S_QUARANTINE_RECORDED]
        if judgment in (JUDGMENT_REJECTED, JUDGMENT_USELESS):
            notes.append(NOTE_BOX_S_RESULT_REJECTED)
        entry = SearchQuarantineEntry(
            query_fingerprint=_fingerprint_query(query),
            judgment=judgment,
            ttl_seconds=self._default_ttl if ttl_seconds is None else int(ttl_seconds),
            result_meta=list(result_meta or []),
            reason=reason,
            notes=notes,
        )
        with self._lock:
            self._ring.append(entry)
        return entry

    # ── Lookup ───────────────────────────────────────────────────────────────

    def find(self, query: str) -> List[SearchQuarantineEntry]:
        """Return non-expired entries for this query fingerprint. Does
        NOT rehydrate raw content — there is none."""
        fp = _fingerprint_query(query)
        out: List[SearchQuarantineEntry] = []
        with self._lock:
            for e in self._ring:
                if e.query_fingerprint == fp and not e.is_expired():
                    out.append(e)
        return out

    def has_rejected(self, query: str) -> bool:
        """True iff a recent rejected/useless entry exists for this query.
        Callers can use this to avoid re-firing a known-weak query within
        the TTL window — WITHOUT promoting the original result."""
        for e in self.find(query):
            if e.judgment in (JUDGMENT_REJECTED, JUDGMENT_USELESS):
                return True
        return False

    # ── Maintenance ──────────────────────────────────────────────────────────

    def prune_expired(self) -> int:
        """Remove expired entries. Returns the count of expired records
        pruned. Safe to call from a flush hook or a test."""
        pruned = 0
        with self._lock:
            fresh: Deque[SearchQuarantineEntry] = deque(maxlen=self._ring.maxlen)
            for e in self._ring:
                if e.is_expired():
                    pruned += 1
                else:
                    fresh.append(e)
            self._ring = fresh
        if pruned:
            logger.debug(f"[BoxS] pruned {pruned} expired quarantine entries; "
                         f"note={NOTE_BOX_S_QUARANTINE_EXPIRED}")
        return pruned

    def __len__(self) -> int:
        with self._lock:
            return sum(1 for e in self._ring if not e.is_expired())

    def snapshot(self) -> List[SearchQuarantineEntry]:
        """Inspection helper — returns a copy of live (non-expired) entries."""
        with self._lock:
            return [e for e in self._ring if not e.is_expired()]

    def clear(self) -> None:
        with self._lock:
            self._ring.clear()
