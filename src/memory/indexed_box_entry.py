#!/usr/bin/env python3
"""
indexed_box_entry.py — Phase G.4: canonical indexed-box entry shape.

A small, explicit internal contract that applicable boxes (M / P / A — not
0, not W, not S) can be mapped onto for inspection, serialization, and
future UI surfaces.

This module intentionally does NOT:
  - replace the existing MemoryIndexer or CustomRagAdapter index paths
  - introduce a new vector store
  - force every box through a single ingestion engine

It only provides:
  - IndexedBoxEntry        : canonical dataclass
  - DeferredIndexingTask   : envelope for write-behind indexing
  - DeferredIndexingQueue  : bounded in-memory queue for deferred work
  - observability note constants

Boxes keep their own concrete stores; this module offers a common shape.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : "Phase G.4 — memory/indexing foundation"
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional


# ── Observability note constants (compact, machine-readable) ────────────────

NOTE_BOX_M_INDEX_UPDATED            = "box_m_index_updated"
NOTE_BOX_A_INDEX_UPDATED            = "box_a_index_updated"
NOTE_BOX_P_PROMOTED                 = "box_p_promoted_distilled_signal"
NOTE_BOX_P_REJECTED_LOW_CONFIDENCE  = "box_p_promotion_rejected_low_confidence"
NOTE_BOX_P_REJECTED_MALFORMED       = "box_p_promotion_rejected_malformed"
NOTE_BOX_P_REJECTED_RAW_TRANSCRIPT  = "box_p_promotion_rejected_raw_transcript"
NOTE_BOX_S_QUARANTINE_RECORDED      = "box_s_quarantine_recorded"
NOTE_BOX_S_RESULT_REJECTED          = "box_s_result_rejected_not_promoted"
NOTE_BOX_S_QUARANTINE_EXPIRED       = "box_s_quarantine_expired"

# ── Box X (curated external durable knowledge) notes ────────────────────────
NOTE_BOX_X_PROMOTED_FROM_S          = "box_x_promoted_from_s"
NOTE_BOX_X_PROMOTION_REJECTED       = "box_x_promotion_rejected"
NOTE_BOX_X_PROMOTION_DEFERRED       = "box_x_promotion_deferred"
NOTE_BOX_X_DUPLICATE_EXISTING       = "box_x_duplicate_existing_entry"
NOTE_BOX_X_LOW_QUALITY              = "box_x_promotion_rejected_low_quality"
NOTE_BOX_X_MISSING_PROVENANCE       = "box_x_promotion_rejected_missing_provenance"
NOTE_BOX_X_ENTRY_STORED             = "box_x_entry_stored"
NOTE_BOX_X_ENTRY_STALE              = "box_x_entry_stale"
NOTE_BOX_X_VERIFICATION_FAILED      = "box_x_entry_verification_failed"
NOTE_BOX_X_FRESHNESS_CHECK_DUE      = "box_x_freshness_check_due"
NOTE_BOX_X_ENTRY_DELETED            = "box_x_entry_deleted"
NOTE_BOX_X_ENTRY_DELETE_MISSING     = "box_x_entry_delete_missing"
NOTE_BOX_X_CONSULTED                = "box_x_consulted"
NOTE_BOX_X_HIT                      = "box_x_hit"
NOTE_BOX_X_MISS                     = "box_x_miss"
NOTE_BOX_X_SKIPPED_NONTECHNICAL     = "box_x_skipped_nontechnical"
NOTE_BOX_X_SKIPPED_LOW_CONFIDENCE   = "box_x_skipped_low_confidence"
NOTE_BOX_X_REFERENCE_USED           = "box_x_reference_used"
NOTE_BOX_X_USED                     = "box_x_used"
NOTE_BOX_X_SKIPPED                  = "box_x_skipped"
NOTE_BOX_X_SUPPLEMENTAL             = "box_x_supplemental"
NOTE_INDEXING_DEFERRED              = "indexing_deferred"
NOTE_INDEXING_FALLBACK_SYNC_SMALL   = "indexing_fallback_sync_small_update"

# Phase G.5: carryover / checkpoint notes (compact, machine-readable).
NOTE_CARRYOVER_CANDIDATE_CREATED     = "carryover_candidate_created"
NOTE_CARRYOVER_CANDIDATE_LOW_CONF    = "carryover_candidate_low_confidence"
NOTE_CARRYOVER_CANDIDATE_BLOCKED_OO  = "carryover_candidate_blocked_opt_out"
NOTE_CARRYOVER_CANDIDATE_PROMOTED    = "carryover_candidate_promoted"
NOTE_CARRYOVER_OPT_OUT_ENABLED       = "carryover_opt_out_enabled"
NOTE_CARRYOVER_OPT_OUT_DISABLED      = "carryover_opt_out_disabled"
NOTE_CARRYOVER_DEFAULT_ALLOWED       = "carryover_default_allowed"
NOTE_CARRYOVER_CHECKPOINT_DETECTED   = "carryover_checkpoint_detected"
NOTE_CARRYOVER_TOO_EARLY             = "carryover_checkpoint_too_early"
NOTE_CARRYOVER_MANUAL_REQUEST        = "carryover_manual_request"

# Phase G.6: operational notes (compact, machine-readable).
NOTE_CARRYOVER_AUTO_CHECKPOINT_FIRED   = "carryover_auto_checkpoint_fired"
NOTE_CARRYOVER_AUTO_CHECKPOINT_SKIPPED = "carryover_auto_checkpoint_skipped"
NOTE_CARRYOVER_PENDING_CREATED         = "carryover_pending_created"
NOTE_CARRYOVER_PENDING_REFRESHED       = "carryover_pending_refreshed"
NOTE_CARRYOVER_PENDING_RESTORED        = "carryover_pending_restored"
NOTE_CARRYOVER_PENDING_MALFORMED       = "carryover_pending_malformed_fallback"
NOTE_CARRYOVER_PENDING_CLEARED         = "carryover_pending_cleared"
NOTE_CARRYOVER_PENDING_REMAINS         = "carryover_pending_remains"
NOTE_CARRYOVER_UI_ACTION_APPLIED       = "carryover_ui_action_applied"

# Phase G.7: auto-promotion policy notes (compact, machine-readable).
NOTE_CARRYOVER_WAITING_CONFIRMATION              = "carryover_candidate_waiting_for_confirmation"
NOTE_CARRYOVER_WAITING_STABILITY                 = "carryover_candidate_waiting_for_stability"
NOTE_CARRYOVER_AUTO_PROMOTED                     = "carryover_candidate_auto_promoted"
NOTE_CARRYOVER_AUTO_PROMOTION_REJECTED_EPHEMERAL = "carryover_candidate_auto_promotion_rejected_ephemeral"
NOTE_CARRYOVER_AUTO_PROMOTION_REJECTED_LOW_CONF  = "carryover_candidate_auto_promotion_rejected_low_confidence"
NOTE_CARRYOVER_AUTO_PROMOTION_REJECTED_OPT_OUT   = "carryover_candidate_auto_promotion_rejected_opt_out"


# Stability bands. Compact, inspectable strings.
STABILITY_VOLATILE         = "volatile"        # session-scoped (Box M ephemeral)
STABILITY_CURATED          = "curated"         # M L1 / curated layer
STABILITY_DISTILLED        = "distilled"       # Box P durable
STABILITY_WORKSPACE        = "workspace"       # Box A user-owned
STABILITY_QUARANTINE       = "quarantine"      # Box S transient
STABILITY_EXTERNAL_CURATED = "external_curated"  # Box X: durable external knowledge


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IndexedBoxEntry:
    """
    Canonical shape for an entry in an indexable box (M / P / A).

    Not every field is meaningful for every box. A box owner fills what
    applies and leaves the rest at default. Serialization is JSON-safe.

    Design rules:
      - raw_content  : original text (may be truncated by box policy)
      - metadata     : box-specific k/v bag (sources, chunk offsets, etc.)
      - summary_capsule : distilled/short form used for priority lookups
      - embedding_ref : opaque pointer into the box's vector store
                        (NOT the raw vector — we don't move embeddings
                        through the canonical shape)
      - timestamps   : created_at / updated_at (ISO8601)
      - confidence   : 0.0–1.0; how sure we are this entry is worth using
      - stability    : one of STABILITY_* above
    """
    box_label:        str                  # "M" | "P" | "A"
    entry_id:         str                  # box-assigned id
    raw_content:      str                  = ""
    metadata:         Dict[str, Any]       = field(default_factory=dict)
    summary_capsule:  str                  = ""
    embedding_ref:    Optional[str]        = None
    created_at:       str                  = field(default_factory=_now_iso)
    updated_at:       str                  = field(default_factory=_now_iso)
    confidence:       float                = 0.0
    stability:        str                  = STABILITY_VOLATILE
    notes:            List[str]            = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "box_label":       self.box_label,
            "entry_id":        self.entry_id,
            "raw_content":     self.raw_content,
            "metadata":        dict(self.metadata),
            "summary_capsule": self.summary_capsule,
            "embedding_ref":   self.embedding_ref,
            "created_at":      self.created_at,
            "updated_at":      self.updated_at,
            "confidence":      round(float(self.confidence), 4),
            "stability":       self.stability,
            "notes":           list(self.notes),
        }


# ── Deferred indexing scaffold ──────────────────────────────────────────────
#
# Spec §4: prefer write-behind or deferred indexing over synchronous full-
# cost indexing on the hot response path. This module offers the envelope
# and a bounded queue. The actual "worker" can be the existing
# ContextProcessor daemon, a future worker thread, or a test harness —
# this class is model-agnostic.


@dataclass
class DeferredIndexingTask:
    """Envelope for a pending index operation that the hot path has
    deferred. Consumers (a worker / a scheduled flush) read `payload`
    and execute the appropriate indexing action for the target box."""
    box_label:    str
    op:           str                # "add" | "update" | "delete"
    payload:      Dict[str, Any]     = field(default_factory=dict)
    enqueued_at:  str                = field(default_factory=_now_iso)
    size_hint:    int                = 0   # rough cost estimate

    def to_dict(self) -> Dict[str, Any]:
        return {
            "box_label":   self.box_label,
            "op":          self.op,
            "payload":     dict(self.payload),
            "enqueued_at": self.enqueued_at,
            "size_hint":   self.size_hint,
        }


class DeferredIndexingQueue:
    """
    Bounded in-memory FIFO of deferred indexing tasks.

    The hot response path enqueues here (O(1)); an out-of-band worker or
    explicit flush consumes. When full, the oldest entry is dropped — the
    queue is a write-behind hint, not a durable job store.

    SMALL_UPDATE_THRESHOLD (bytes) is consulted by callers that want to
    pick "tiny synchronous update" vs "defer". It is compared against the
    task's `size_hint`. A caller that does a tiny update may still choose
    sync; this is advisory.
    """
    SMALL_UPDATE_THRESHOLD: int = 512   # bytes; advisory

    def __init__(self, maxlen: int = 256) -> None:
        self._q: Deque[DeferredIndexingTask] = deque(maxlen=maxlen)

    def enqueue(self, task: DeferredIndexingTask) -> None:
        self._q.append(task)

    def dequeue(self) -> Optional[DeferredIndexingTask]:
        if not self._q:
            return None
        return self._q.popleft()

    def __len__(self) -> int:
        return len(self._q)

    def peek_all(self) -> List[DeferredIndexingTask]:
        """Inspection helper — returns a snapshot copy, does not drain."""
        return list(self._q)

    def should_defer(self, size_hint: int) -> bool:
        """Advisory: True if the caller should enqueue rather than do the
        work synchronously on the hot path. Small updates fall through
        to sync; large ones defer."""
        return size_hint > self.SMALL_UPDATE_THRESHOLD
