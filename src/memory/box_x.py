#!/usr/bin/env python3
"""
box_x.py — Box X: curated external durable knowledge layer.

Box X is the new durable external-knowledge layer introduced after G.12.
It sits alongside — NOT inside — Box W (Wikipedia-pure reference) and
Box S (transient external-search quarantine).

Semantic invariants (non-negotiable):
  - Box X is **external-knowledge-derived** (not user workspace).
  - Box X is **durable / persistable** (JSON-backed on disk).
  - Box X is **provenance-aware** (every entry carries source_family,
    source_uri, retrieved_at, last_verified_at).
  - Box X is **freshness-aware** (static_reference | slow_changing |
    volatile), with inspectable staleness states.
  - Box X is **separate from Box W** (it never merges with Wikipedia
    curated seeds) and **separate from Box S** (it never caches raw
    search bodies).
  - Box X does NOT accept raw search snippets. Everything enters
    through the S → X promotion pipeline (see `s_to_x_promotion.py`).

What Box X does NOT do:
  - store raw weak external search content
  - index massive corpora at scale (that's Box W's territory)
  - replace Box P (distilled personal continuity)
  - interfere with routing decisions; it is a retrieval-side candidate
    only, subordinate to all hard invariants

Storage model:
  - JSON file at ``data/box_x/box_x.json`` (append-only in practice)
  - Index: in-memory title/canonical-term map for O(1) dedup lookup
  - Optional embedding_ref is stored for later vector search; the
    vector itself lives in a future index component

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .indexed_box_entry import (
    IndexedBoxEntry,
    STABILITY_EXTERNAL_CURATED,
    NOTE_BOX_X_ENTRY_STORED,
    NOTE_BOX_X_ENTRY_STALE,
    NOTE_BOX_X_ENTRY_DELETED,
    NOTE_BOX_X_ENTRY_DELETE_MISSING,
    NOTE_BOX_X_FRESHNESS_CHECK_DUE,
    NOTE_BOX_X_VERIFICATION_FAILED,
)

logger = logging.getLogger(__name__)


BOX_X_LABEL = "X"

# ── Freshness policy ────────────────────────────────────────────────────────

FRESHNESS_STATIC_REFERENCE = "static_reference"  # encyclopedic, long-lived
FRESHNESS_SLOW_CHANGING    = "slow_changing"     # updated over months
FRESHNESS_VOLATILE         = "volatile"          # frequently-changing

_VALID_FRESHNESS = {
    FRESHNESS_STATIC_REFERENCE,
    FRESHNESS_SLOW_CHANGING,
    FRESHNESS_VOLATILE,
}

# Staleness state is inspectable, not load-bearing on routing decisions.
STALENESS_FRESH               = "fresh"
STALENESS_CHECK_DUE           = "check_due"
STALENESS_STALE               = "stale"
STALENESS_VERIFICATION_FAILED = "verification_failed"

_VALID_STALENESS = {
    STALENESS_FRESH,
    STALENESS_CHECK_DUE,
    STALENESS_STALE,
    STALENESS_VERIFICATION_FAILED,
}

# Default recheck windows (in days). Tuned to be conservative; the
# model is an inspectable scaffold, not a production scheduler.
_RECHECK_WINDOW_DAYS: Dict[str, int] = {
    FRESHNESS_STATIC_REFERENCE: 365,
    FRESHNESS_SLOW_CHANGING:    90,
    FRESHNESS_VOLATILE:         7,
}

# A stale multiplier beyond which "check_due" escalates to "stale".
_STALE_MULTIPLIER = 2.0

# Minimum quality score that qualifies an entry for Box X storage.
# Anything below is treated as low-quality and must not be persisted.
BOX_X_MIN_QUALITY_SCORE = 0.55


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _fingerprint(canonical_term: str, domain: str, source_uri: str) -> str:
    """Deterministic short id for dedup. 12 hex chars."""
    payload = "|".join((
        (canonical_term or "").strip().lower(),
        (domain or "").strip().lower(),
        (source_uri or "").strip().lower(),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ── Data model ─────────────────────────────────────────────────────────────


@dataclass
class BoxXEntry:
    """A single Box X entry — curated external durable knowledge.

    Mapped onto the canonical ``IndexedBoxEntry`` shape when exported
    (``to_indexed_entry``). Stored as structured JSON on disk.
    """
    entry_id:          str
    title:             str
    canonical_terms:   List[str]                 = field(default_factory=list)
    domain:            str                       = "uncategorized"
    source_family:     str                       = ""
    source_uri:        str                       = ""
    source_path:       str                       = ""
    content:           str                       = ""
    metadata:          Dict[str, Any]            = field(default_factory=dict)
    retrieved_at:      str                       = field(default_factory=_now_iso)
    last_verified_at:  str                       = field(default_factory=_now_iso)
    freshness_policy:  str                       = FRESHNESS_STATIC_REFERENCE
    embedding_ref:     Optional[str]             = None
    quality_score:     float                     = 0.0
    staleness_state:   str                       = STALENESS_FRESH
    provenance:        Dict[str, Any]            = field(default_factory=dict)
    notes:             List[str]                 = field(default_factory=list)

    def __post_init__(self):
        if self.freshness_policy not in _VALID_FRESHNESS:
            self.freshness_policy = FRESHNESS_STATIC_REFERENCE
        if self.staleness_state not in _VALID_STALENESS:
            self.staleness_state = STALENESS_FRESH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id":         self.entry_id,
            "title":            self.title,
            "canonical_terms":  list(self.canonical_terms),
            "domain":           self.domain,
            "source_family":    self.source_family,
            "source_uri":       self.source_uri,
            "source_path":      self.source_path,
            "content":          self.content,
            "metadata":         dict(self.metadata),
            "retrieved_at":     self.retrieved_at,
            "last_verified_at": self.last_verified_at,
            "freshness_policy": self.freshness_policy,
            "embedding_ref":    self.embedding_ref,
            "quality_score":    round(float(self.quality_score), 4),
            "staleness_state":  self.staleness_state,
            "provenance":       dict(self.provenance),
            "notes":            list(self.notes),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "BoxXEntry":
        return cls(
            entry_id         = str(raw.get("entry_id") or ""),
            title            = str(raw.get("title") or ""),
            canonical_terms  = list(raw.get("canonical_terms") or []),
            domain           = str(raw.get("domain") or "uncategorized"),
            source_family    = str(raw.get("source_family") or ""),
            source_uri       = str(raw.get("source_uri") or ""),
            source_path      = str(raw.get("source_path") or ""),
            content          = str(raw.get("content") or ""),
            metadata         = dict(raw.get("metadata") or {}),
            retrieved_at     = str(raw.get("retrieved_at") or _now_iso()),
            last_verified_at = str(raw.get("last_verified_at") or _now_iso()),
            freshness_policy = str(raw.get("freshness_policy") or FRESHNESS_STATIC_REFERENCE),
            embedding_ref    = raw.get("embedding_ref"),
            quality_score    = float(raw.get("quality_score") or 0.0),
            staleness_state  = str(raw.get("staleness_state") or STALENESS_FRESH),
            provenance       = dict(raw.get("provenance") or {}),
            notes            = list(raw.get("notes") or []),
        )

    def to_indexed_entry(self) -> IndexedBoxEntry:
        """Map Box X entry onto the canonical indexed-box shape."""
        return IndexedBoxEntry(
            box_label       = BOX_X_LABEL,
            entry_id        = self.entry_id,
            raw_content     = self.content,
            metadata        = {
                "title":            self.title,
                "canonical_terms":  list(self.canonical_terms),
                "domain":           self.domain,
                "source_family":    self.source_family,
                "source_uri":       self.source_uri,
                "source_path":      self.source_path,
                "freshness_policy": self.freshness_policy,
                "staleness_state":  self.staleness_state,
                "retrieved_at":     self.retrieved_at,
                "last_verified_at": self.last_verified_at,
                **dict(self.metadata),
            },
            summary_capsule = self.title,
            embedding_ref   = self.embedding_ref,
            created_at      = self.retrieved_at,
            updated_at      = self.last_verified_at,
            confidence      = self.quality_score,
            stability       = STABILITY_EXTERNAL_CURATED,
            notes           = list(self.notes),
        )

    def update_staleness(self, *, now: Optional[datetime] = None) -> str:
        """Recompute staleness based on freshness policy and
        last_verified_at. Sets ``self.staleness_state`` and returns it.
        """
        now = now or _now()
        verified_at = _parse_iso(self.last_verified_at) or now
        window_days = _RECHECK_WINDOW_DAYS.get(self.freshness_policy, 365)
        window = timedelta(days=window_days)
        elapsed = now - verified_at
        if elapsed <= window:
            self.staleness_state = STALENESS_FRESH
        elif elapsed <= window * _STALE_MULTIPLIER:
            self.staleness_state = STALENESS_CHECK_DUE
        else:
            self.staleness_state = STALENESS_STALE
        return self.staleness_state


# ── Store ──────────────────────────────────────────────────────────────────


@dataclass
class BoxXPromotionRecord:
    """Compact record of one S → X promotion attempt.

    Kept alongside entries so the history of what was promoted,
    rejected, deferred is inspectable without scanning the quarantine."""
    timestamp:          str
    outcome:            str           # promoted | rejected | deferred | duplicate
    reason:             str
    candidate_hash:     str
    canonical_term:     str           = ""
    domain:             str           = ""
    source_family:      str           = ""
    source_uri:         str           = ""
    quality_score:      float         = 0.0
    notes:              List[str]     = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BoxXStore:
    """Durable store for Box X entries.

    Thread-safe. Persists to ``<store_dir>/box_x.json`` on every write.
    The indexing layer is an in-memory map from
    ``fingerprint(canonical_term, domain, source_uri)`` → entry_id for
    O(1) dedup.
    """

    STORE_FILENAME = "box_x.json"
    PROMOTION_LOG_FILENAME = "box_x_promotion_log.jsonl"
    DELETION_LOG_FILENAME = "box_x_deletion_log.jsonl"

    def __init__(
        self,
        store_dir: str | Path = "data/box_x",
        *,
        auto_load: bool = True,
    ) -> None:
        self.store_dir = Path(store_dir)
        self._store_path = self.store_dir / self.STORE_FILENAME
        self._promotion_log_path = self.store_dir / self.PROMOTION_LOG_FILENAME
        self._deletion_log_path = self.store_dir / self.DELETION_LOG_FILENAME
        self._lock = threading.RLock()
        self._entries: Dict[str, BoxXEntry] = {}
        self._fingerprint_index: Dict[str, str] = {}   # fp → entry_id
        self._canonical_index: Dict[str, List[str]] = {}  # canonical-term → [entry_id]
        self._loaded = False
        if auto_load:
            self.load()

    # -- IO -----------------------------------------------------------------

    def load(self) -> None:
        with self._lock:
            self._entries.clear()
            self._fingerprint_index.clear()
            self._canonical_index.clear()
            if not self._store_path.exists():
                self._loaded = True
                return
            try:
                raw = json.loads(self._store_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(
                    "[BoxX] store file unreadable, starting empty: %s", exc,
                )
                self._loaded = True
                return
            for obj in raw.get("entries", []) or []:
                try:
                    entry = BoxXEntry.from_dict(obj)
                except Exception:
                    continue
                self._index_entry_locked(entry)
            self._loaded = True
            logger.info(
                "[BoxX] loaded %d entries from %s",
                len(self._entries), self._store_path,
            )

    def _persist_locked(self) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "box_label":  BOX_X_LABEL,
            "updated_at": _now_iso(),
            "entries":    [e.to_dict() for e in self._entries.values()],
        }
        tmp = self._store_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self._store_path)

    def _index_entry_locked(self, entry: BoxXEntry) -> None:
        self._entries[entry.entry_id] = entry
        fp = _fingerprint(
            _pick_canonical_term(entry), entry.domain, entry.source_uri,
        )
        self._fingerprint_index[fp] = entry.entry_id
        for term in entry.canonical_terms + [entry.title]:
            if not term:
                continue
            key = term.strip().lower()
            if not key:
                continue
            self._canonical_index.setdefault(key, [])
            if entry.entry_id not in self._canonical_index[key]:
                self._canonical_index[key].append(entry.entry_id)

    # -- Public API ---------------------------------------------------------

    def is_loaded(self) -> bool:
        return self._loaded

    def is_empty(self) -> bool:
        return len(self._entries) == 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def snapshot(self) -> List[BoxXEntry]:
        with self._lock:
            return list(self._entries.values())

    def get(self, entry_id: str) -> Optional[BoxXEntry]:
        with self._lock:
            return self._entries.get(entry_id)

    def find_by_canonical_term(self, term: str) -> List[BoxXEntry]:
        key = (term or "").strip().lower()
        if not key:
            return []
        with self._lock:
            ids = list(self._canonical_index.get(key, []))
            return [self._entries[i] for i in ids if i in self._entries]

    def exists(
        self, *, canonical_term: str, domain: str, source_uri: str,
    ) -> bool:
        fp = _fingerprint(canonical_term, domain, source_uri)
        with self._lock:
            return fp in self._fingerprint_index

    def add(self, entry: BoxXEntry, *, persist: bool = True) -> BoxXEntry:
        """Add or replace an entry. Caller is responsible for quality
        checks (see ``evaluate_x_promotion_candidate`` in
        ``s_to_x_promotion.py``)."""
        with self._lock:
            entry.notes = list(entry.notes) + [NOTE_BOX_X_ENTRY_STORED]
            self._index_entry_locked(entry)
            if persist:
                self._persist_locked()
        return entry

    def remove(
        self,
        entry_id: str,
        *,
        persist: bool = True,
        reason: str = "",
        actor: str = "user",
    ) -> bool:
        """Delete a single entry by id.

        Returns True on success, False when the id is unknown. On
        success: removes the in-memory entry, rebuilds the canonical
        term index entries that pointed at it, drops the fingerprint
        mapping, persists the store, and writes a deletion log line.

        The rebuild is bounded (touches only the keys that contained
        the deleted id) so a single deletion cannot corrupt unrelated
        entries. Thread-safe.
        """
        with self._lock:
            entry = self._entries.pop(entry_id, None)
            if entry is None:
                self._append_deletion_record_locked({
                    "timestamp":     _now_iso(),
                    "outcome":       "missing",
                    "entry_id":      entry_id,
                    "reason":        reason or "entry_id_not_found",
                    "actor":         actor,
                    "note":          NOTE_BOX_X_ENTRY_DELETE_MISSING,
                })
                return False
            fp = _fingerprint(
                _pick_canonical_term(entry),
                entry.domain,
                entry.source_uri,
            )
            self._fingerprint_index.pop(fp, None)
            # Rebuild canonical index entries that mentioned this id,
            # and drop keys that become empty.
            empty_keys: List[str] = []
            for key, lst in self._canonical_index.items():
                if entry_id in lst:
                    lst.remove(entry_id)
                    if not lst:
                        empty_keys.append(key)
            for k in empty_keys:
                self._canonical_index.pop(k, None)
            if persist:
                self._persist_locked()
            self._append_deletion_record_locked({
                "timestamp":       _now_iso(),
                "outcome":         "deleted",
                "entry_id":        entry_id,
                "title":           entry.title,
                "domain":          entry.domain,
                "source_family":   entry.source_family,
                "source_uri":      entry.source_uri,
                "reason":          reason or "user_requested_deletion",
                "actor":           actor,
                "note":            NOTE_BOX_X_ENTRY_DELETED,
            })
            return True

    def delete_by_entry_id(
        self,
        entry_id: str,
        *,
        reason: str = "",
        actor: str = "user",
    ) -> bool:
        """Public alias for ``remove`` — named for UI/API ergonomics.

        Returns True when an entry was deleted, False otherwise.
        """
        return self.remove(entry_id, reason=reason, actor=actor)

    def list_entries_for_ui(self) -> List[Dict[str, Any]]:
        """Compact per-entry summary for UI display.

        Intentionally does NOT include raw content — the UI is kept
        calm and usable. Each row has enough signal to let a human
        decide whether to delete that entry.
        """
        with self._lock:
            rows: List[Dict[str, Any]] = []
            for e in self._entries.values():
                rows.append({
                    "entry_id":         e.entry_id,
                    "title":            e.title,
                    "canonical_terms":  list(e.canonical_terms),
                    "domain":           e.domain,
                    "source_family":    e.source_family,
                    "source_uri":       e.source_uri,
                    "freshness_policy": e.freshness_policy,
                    "staleness_state":  e.staleness_state,
                    "retrieved_at":     e.retrieved_at,
                    "last_verified_at": e.last_verified_at,
                    "quality_score":    round(float(e.quality_score), 4),
                    "content_chars":    len(e.content),
                })
            # Stable order: most recent first, then by title.
            rows.sort(key=lambda r: (r["retrieved_at"] or "", r["title"]), reverse=True)
            return rows

    def _append_deletion_record_locked(self, rec: Dict[str, Any]) -> None:
        """Append one JSON line to the deletion log. Must be called
        while holding the store lock."""
        try:
            self.store_dir.mkdir(parents=True, exist_ok=True)
            with self._deletion_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as exc:   # noqa: BLE001
            logger.debug("[BoxX] deletion log write failed: %s", exc)

    def read_deletion_records(self) -> List[Dict[str, Any]]:
        """Inspection helper — read the JSONL deletion log."""
        if not self._deletion_log_path.exists():
            return []
        out: List[Dict[str, Any]] = []
        for line in self._deletion_log_path.read_text(
            encoding="utf-8",
        ).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out

    def refresh_staleness(self) -> Dict[str, int]:
        """Recompute staleness for every entry; returns counts by state.
        Does not modify data beyond the per-entry staleness_state.
        """
        counts = {k: 0 for k in _VALID_STALENESS}
        with self._lock:
            for e in self._entries.values():
                state = e.update_staleness()
                counts[state] = counts.get(state, 0) + 1
                if state == STALENESS_STALE and NOTE_BOX_X_ENTRY_STALE not in e.notes:
                    e.notes.append(NOTE_BOX_X_ENTRY_STALE)
                elif state == STALENESS_CHECK_DUE and NOTE_BOX_X_FRESHNESS_CHECK_DUE not in e.notes:
                    e.notes.append(NOTE_BOX_X_FRESHNESS_CHECK_DUE)
            self._persist_locked()
        return counts

    def mark_verification_failed(
        self, entry_id: str, *, reason: str = "",
    ) -> bool:
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                return False
            entry.staleness_state = STALENESS_VERIFICATION_FAILED
            if reason:
                entry.notes.append(
                    f"{NOTE_BOX_X_VERIFICATION_FAILED}:{reason}"
                )
            else:
                entry.notes.append(NOTE_BOX_X_VERIFICATION_FAILED)
            self._persist_locked()
            return True

    # -- Inspectability ------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Compact machine-readable summary for diagnostics/UI."""
        with self._lock:
            by_domain: Dict[str, int] = {}
            by_family: Dict[str, int] = {}
            by_staleness: Dict[str, int] = {k: 0 for k in _VALID_STALENESS}
            for e in self._entries.values():
                by_domain[e.domain] = by_domain.get(e.domain, 0) + 1
                fam = e.source_family or "unknown"
                by_family[fam] = by_family.get(fam, 0) + 1
                by_staleness[e.staleness_state] = (
                    by_staleness.get(e.staleness_state, 0) + 1
                )
            return {
                "box_label":      BOX_X_LABEL,
                "entry_count":    len(self._entries),
                "store_path":     str(self._store_path),
                "by_domain":      by_domain,
                "by_family":      by_family,
                "by_staleness":   by_staleness,
            }

    def append_promotion_record(
        self, record: BoxXPromotionRecord,
    ) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        with self._lock, self._promotion_log_path.open(
            "a", encoding="utf-8",
        ) as f:
            f.write(
                json.dumps(record.to_dict(), ensure_ascii=False) + "\n"
            )

    def read_promotion_records(self) -> List[Dict[str, Any]]:
        """Inspection helper — read the JSONL promotion log."""
        if not self._promotion_log_path.exists():
            return []
        out: List[Dict[str, Any]] = []
        for line in self._promotion_log_path.read_text(
            encoding="utf-8",
        ).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out

    # -- Search (title / canonical-term exact match) -------------------------
    # Box X does not ship its own vector search in this pass; it is
    # consulted by canonical-term matching so a future retrieval layer
    # can decide to hydrate X entries. This is intentional — scope
    # limits prevent reintroducing a third vector store.

    def search_terms(
        self, terms: Iterable[str], *, top_k: int = 5,
    ) -> List[BoxXEntry]:
        hits: List[BoxXEntry] = []
        seen: set[str] = set()
        for t in terms:
            for e in self.find_by_canonical_term(t):
                if e.entry_id in seen:
                    continue
                seen.add(e.entry_id)
                hits.append(e)
                if len(hits) >= top_k:
                    return hits
        return hits

    def diagnostics(self) -> Dict[str, Any]:
        """Public diagnostic surface for APIs/UI. Read-only."""
        base = self.stats()
        recent: List[Dict[str, Any]] = []
        log = self.read_promotion_records()
        for r in log[-10:]:
            recent.append({
                "timestamp":      r.get("timestamp"),
                "outcome":        r.get("outcome"),
                "canonical_term": r.get("canonical_term"),
                "domain":         r.get("domain"),
                "reason":         r.get("reason"),
            })
        base["recent_promotion_log"] = recent
        del_log = self.read_deletion_records()
        recent_del: List[Dict[str, Any]] = []
        for r in del_log[-10:]:
            recent_del.append({
                "timestamp":     r.get("timestamp"),
                "outcome":       r.get("outcome"),
                "entry_id":      r.get("entry_id"),
                "title":         r.get("title"),
                "domain":        r.get("domain"),
                "reason":        r.get("reason"),
                "actor":         r.get("actor"),
            })
        base["recent_deletion_log"] = recent_del
        return base


def _pick_canonical_term(entry: BoxXEntry) -> str:
    if entry.canonical_terms:
        return entry.canonical_terms[0]
    return entry.title


# ── Entry construction helper ──────────────────────────────────────────────


def new_entry_id(*, canonical_term: str, domain: str, source_uri: str) -> str:
    return _fingerprint(canonical_term, domain, source_uri)
