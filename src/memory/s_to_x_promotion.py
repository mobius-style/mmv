#!/usr/bin/env python3
"""
s_to_x_promotion.py — Curation-gated pipeline from Box S → Box X.

Box S is the transient quarantine workspace for external-search
results. Box X is the durable curated external-knowledge layer.
This module is the **only sanctioned path** between them.

Non-negotiable rules:
  - Nothing goes directly from S to X without curation logic.
  - Raw weak snippets are never persisted into X.
  - Every S → X attempt produces an inspectable record
    (``BoxXPromotionRecord``) regardless of outcome.
  - Missing provenance blocks promotion.
  - Duplicates (by fingerprint) are rejected, not overwritten.

Promotion outcomes:
  - promoted:       entry accepted into Box X
  - rejected:       explicit failure (low quality, bad source, …)
  - deferred:       candidate looks reasonable but needs more signal
                    (e.g. not yet repeatedly rescued)
  - duplicate:      already present in Box X

The canonical entry point is ``evaluate_x_promotion_candidate`` for
inspection-only classification and
``promote_search_result_to_box_x`` for the full write path.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .box_x import (
    BOX_X_LABEL,
    BOX_X_MIN_QUALITY_SCORE,
    BoxXEntry,
    BoxXPromotionRecord,
    BoxXStore,
    FRESHNESS_SLOW_CHANGING,
    FRESHNESS_STATIC_REFERENCE,
    FRESHNESS_VOLATILE,
    new_entry_id,
    _now_iso,
)
from .indexed_box_entry import (
    NOTE_BOX_X_DUPLICATE_EXISTING,
    NOTE_BOX_X_LOW_QUALITY,
    NOTE_BOX_X_MISSING_PROVENANCE,
    NOTE_BOX_X_PROMOTED_FROM_S,
    NOTE_BOX_X_PROMOTION_DEFERRED,
    NOTE_BOX_X_PROMOTION_REJECTED,
)

logger = logging.getLogger(__name__)


# ── Outcomes ───────────────────────────────────────────────────────────────

OUTCOME_PROMOTED   = "promoted"
OUTCOME_REJECTED   = "rejected"
OUTCOME_DEFERRED   = "deferred"
OUTCOME_DUPLICATE  = "duplicate"

# ── Rejection reason tags ──────────────────────────────────────────────────

REASON_MISSING_PROVENANCE       = "missing_provenance"
REASON_MISSING_CONTENT          = "missing_content"
REASON_LOW_QUALITY              = "low_quality_score"
REASON_CONTENT_TOO_SHORT        = "content_too_short"
REASON_CONTENT_TOO_LONG         = "content_too_long_raw_snippet"
REASON_SOURCE_FAMILY_REJECTED   = "source_family_rejected"
REASON_NO_CANONICAL_TERM        = "no_canonical_term"
REASON_DUPLICATE                = "duplicate_existing_x"
REASON_INSUFFICIENT_RESCUE      = "insufficient_repeat_rescue"
REASON_REJECTED_BY_S_QUARANTINE = "rejected_by_s_quarantine"

# ── Policy knobs (conservative defaults) ───────────────────────────────────

# Minimum content length in characters. Raw snippets from web search
# are usually below this; promotable content is a real curated
# paragraph, not a 40-char blurb.
_MIN_CONTENT_CHARS = 120

# Upper bound. A 20KB chunk is almost certainly raw noisy scrape; we
# refuse to persist it as "curated" knowledge.
_MAX_CONTENT_CHARS = 8_000

# Minimum repeat rescue count before auto-promotion from S. Candidates
# below this are deferred (they look reasonable but need more
# evidence of repeated relevance).
_MIN_RESCUE_COUNT_AUTO = 2

# Source families that Box X never accepts (noisy, unreliable, or
# dynamic content farms).
_SOURCE_FAMILY_DENYLIST: set[str] = {
    "unknown",
    "ephemeral_search",
    "raw_web_snippet",
}

# Source families that are auto-acceptable (reputable reference-style
# sources). Candidates from these families get a quality bonus.
_SOURCE_FAMILY_REPUTABLE: set[str] = {
    "nlab",
    "stanford_encyclopedia",
    "wolfram_mathworld",
    "arxiv_survey",
    "curated_domain_pack",
    "official_documentation",
    "kiwix",
    "wikipedia_high_confidence",
}


# ── Candidate shape ────────────────────────────────────────────────────────


@dataclass
class PromotionCandidate:
    """What an S → X promotion caller supplies.

    ``source_family``, ``source_uri`` and ``canonical_term`` are the
    three provenance keys that must all be present for the candidate
    to have any chance of being promoted.
    """
    canonical_term:   str
    domain:           str
    title:            str
    content:          str
    source_family:    str
    source_uri:       str
    retrieved_at:     str                  = ""
    freshness_policy: str                  = FRESHNESS_STATIC_REFERENCE
    quality_score:    float                = 0.0
    rescue_count:     int                  = 0   # times this was found useful
    explicit_approval: bool                = False
    metadata:         Dict[str, Any]       = field(default_factory=dict)
    extra_canonical_terms: List[str]       = field(default_factory=list)

    def canonical_terms(self) -> List[str]:
        out: List[str] = []
        if self.canonical_term:
            out.append(self.canonical_term)
        for t in self.extra_canonical_terms:
            if t and t not in out:
                out.append(t)
        return out

    def fingerprint(self) -> str:
        h = hashlib.sha256()
        h.update((self.canonical_term or "").strip().lower().encode("utf-8"))
        h.update(b"|")
        h.update((self.domain or "").strip().lower().encode("utf-8"))
        h.update(b"|")
        h.update((self.source_uri or "").strip().lower().encode("utf-8"))
        return h.hexdigest()[:16]


@dataclass
class PromotionEvaluation:
    """Inspection-only result of a promotion evaluation."""
    outcome:        str              # promoted | rejected | deferred | duplicate
    reason:         str
    candidate_hash: str
    notes:          List[str]        = field(default_factory=list)
    final_quality:  float            = 0.0

    def is_accept(self) -> bool:
        return self.outcome == OUTCOME_PROMOTED


# ── Core evaluation ────────────────────────────────────────────────────────


def _score_quality_adjustment(
    candidate: PromotionCandidate,
) -> Tuple[float, List[str]]:
    """Apply source-family and explicit-approval adjustments.

    Returns ``(adjusted_score, notes)``. The raw quality_score from the
    caller is the baseline; adjustments are small and bounded.
    """
    notes: List[str] = []
    adjusted = float(candidate.quality_score)
    if candidate.source_family in _SOURCE_FAMILY_REPUTABLE:
        adjusted = min(1.0, adjusted + 0.10)
        notes.append("source_family_reputable_bonus")
    if candidate.explicit_approval:
        adjusted = min(1.0, adjusted + 0.10)
        notes.append("explicit_approval_bonus")
    return adjusted, notes


def evaluate_x_promotion_candidate(
    candidate: PromotionCandidate,
    *,
    store: Optional[BoxXStore] = None,
    s_rejected: bool = False,
) -> PromotionEvaluation:
    """Evaluate (without writing) whether a candidate should be
    promoted to Box X.

    Args:
      candidate   : the promotion candidate
      store       : optional Box X store (used for dedup). When None,
                    duplicates cannot be detected and are handled on
                    the write path instead.
      s_rejected  : True if Box S already rejected this query as
                    useless. Forces an immediate rejection.

    Returns:
      a PromotionEvaluation with outcome and a compact reason tag.
    """
    notes: List[str] = []
    fp = candidate.fingerprint()

    # Fast-fail gates. Each gate produces a rejection with the right
    # inspectable reason tag; no silent promotions.
    if s_rejected:
        return PromotionEvaluation(
            outcome=OUTCOME_REJECTED, reason=REASON_REJECTED_BY_S_QUARANTINE,
            candidate_hash=fp, notes=[NOTE_BOX_X_PROMOTION_REJECTED],
        )
    if not (candidate.source_family and candidate.source_uri):
        return PromotionEvaluation(
            outcome=OUTCOME_REJECTED, reason=REASON_MISSING_PROVENANCE,
            candidate_hash=fp, notes=[NOTE_BOX_X_MISSING_PROVENANCE],
        )
    if candidate.source_family in _SOURCE_FAMILY_DENYLIST:
        return PromotionEvaluation(
            outcome=OUTCOME_REJECTED, reason=REASON_SOURCE_FAMILY_REJECTED,
            candidate_hash=fp, notes=[NOTE_BOX_X_PROMOTION_REJECTED],
        )
    if not candidate.canonical_term:
        return PromotionEvaluation(
            outcome=OUTCOME_REJECTED, reason=REASON_NO_CANONICAL_TERM,
            candidate_hash=fp, notes=[NOTE_BOX_X_PROMOTION_REJECTED],
        )
    if not candidate.content or not candidate.content.strip():
        return PromotionEvaluation(
            outcome=OUTCOME_REJECTED, reason=REASON_MISSING_CONTENT,
            candidate_hash=fp, notes=[NOTE_BOX_X_PROMOTION_REJECTED],
        )
    clen = len(candidate.content)
    if clen < _MIN_CONTENT_CHARS:
        return PromotionEvaluation(
            outcome=OUTCOME_REJECTED, reason=REASON_CONTENT_TOO_SHORT,
            candidate_hash=fp, notes=[NOTE_BOX_X_PROMOTION_REJECTED],
        )
    if clen > _MAX_CONTENT_CHARS:
        return PromotionEvaluation(
            outcome=OUTCOME_REJECTED, reason=REASON_CONTENT_TOO_LONG,
            candidate_hash=fp, notes=[NOTE_BOX_X_PROMOTION_REJECTED],
        )

    if store is not None and store.exists(
        canonical_term=candidate.canonical_term,
        domain=candidate.domain,
        source_uri=candidate.source_uri,
    ):
        return PromotionEvaluation(
            outcome=OUTCOME_DUPLICATE, reason=REASON_DUPLICATE,
            candidate_hash=fp, notes=[NOTE_BOX_X_DUPLICATE_EXISTING],
        )

    adjusted, adj_notes = _score_quality_adjustment(candidate)
    notes.extend(adj_notes)

    if adjusted < BOX_X_MIN_QUALITY_SCORE:
        return PromotionEvaluation(
            outcome=OUTCOME_REJECTED, reason=REASON_LOW_QUALITY,
            candidate_hash=fp, notes=notes + [NOTE_BOX_X_LOW_QUALITY],
            final_quality=adjusted,
        )

    # Defer when quality is acceptable but repeated rescue evidence is
    # thin and the candidate was not explicitly approved. This keeps
    # noise from sneaking in on a single search hit.
    if (
        not candidate.explicit_approval
        and candidate.rescue_count < _MIN_RESCUE_COUNT_AUTO
    ):
        return PromotionEvaluation(
            outcome=OUTCOME_DEFERRED, reason=REASON_INSUFFICIENT_RESCUE,
            candidate_hash=fp, notes=notes + [NOTE_BOX_X_PROMOTION_DEFERRED],
            final_quality=adjusted,
        )

    return PromotionEvaluation(
        outcome=OUTCOME_PROMOTED, reason="accepted",
        candidate_hash=fp, notes=notes + [NOTE_BOX_X_PROMOTED_FROM_S],
        final_quality=adjusted,
    )


def promote_search_result_to_box_x(
    candidate: PromotionCandidate,
    *,
    store: BoxXStore,
    s_rejected: bool = False,
    record_log: bool = True,
) -> Tuple[PromotionEvaluation, Optional[BoxXEntry]]:
    """Full write path. Evaluates the candidate and, on success,
    writes it to the Box X store.

    Always logs an inspectable ``BoxXPromotionRecord`` to the store's
    JSONL promotion log (unless ``record_log=False``).

    Returns ``(evaluation, entry_or_none)``. When the outcome is not
    ``promoted``, ``entry_or_none`` is None.
    """
    ev = evaluate_x_promotion_candidate(
        candidate, store=store, s_rejected=s_rejected,
    )
    entry: Optional[BoxXEntry] = None

    if ev.outcome == OUTCOME_PROMOTED:
        entry_id = new_entry_id(
            canonical_term=candidate.canonical_term,
            domain=candidate.domain,
            source_uri=candidate.source_uri,
        )
        retrieved_at = candidate.retrieved_at or _now_iso()
        entry = BoxXEntry(
            entry_id         = entry_id,
            title            = candidate.title or candidate.canonical_term,
            canonical_terms  = candidate.canonical_terms(),
            domain           = candidate.domain or "uncategorized",
            source_family    = candidate.source_family,
            source_uri       = candidate.source_uri,
            source_path      = candidate.metadata.get("source_path", "") if isinstance(candidate.metadata, dict) else "",
            content          = candidate.content.strip(),
            metadata         = dict(candidate.metadata or {}),
            retrieved_at     = retrieved_at,
            last_verified_at = retrieved_at,
            freshness_policy = (
                candidate.freshness_policy
                if candidate.freshness_policy in (
                    FRESHNESS_STATIC_REFERENCE,
                    FRESHNESS_SLOW_CHANGING,
                    FRESHNESS_VOLATILE,
                )
                else FRESHNESS_STATIC_REFERENCE
            ),
            quality_score    = ev.final_quality or candidate.quality_score,
            provenance       = {
                "source_family":  candidate.source_family,
                "source_uri":     candidate.source_uri,
                "rescue_count":   candidate.rescue_count,
                "approved":       candidate.explicit_approval,
                "candidate_hash": ev.candidate_hash,
            },
            notes            = list(ev.notes),
        )
        store.add(entry, persist=True)

    if record_log:
        rec = BoxXPromotionRecord(
            timestamp=_now_iso(),
            outcome=ev.outcome,
            reason=ev.reason,
            candidate_hash=ev.candidate_hash,
            canonical_term=candidate.canonical_term,
            domain=candidate.domain,
            source_family=candidate.source_family,
            source_uri=candidate.source_uri,
            quality_score=ev.final_quality or candidate.quality_score,
            notes=list(ev.notes),
        )
        try:
            store.append_promotion_record(rec)
        except Exception as exc:
            logger.debug("[S→X] promotion log write failed: %s", exc)

    return ev, entry


def box_s_to_x_candidate(
    *,
    canonical_term: str,
    domain: str,
    title: str,
    content: str,
    source_family: str,
    source_uri: str,
    quality_score: float = 0.0,
    rescue_count: int = 0,
    explicit_approval: bool = False,
    freshness_policy: str = FRESHNESS_STATIC_REFERENCE,
    metadata: Optional[Dict[str, Any]] = None,
    extra_canonical_terms: Optional[List[str]] = None,
) -> PromotionCandidate:
    """Convenience constructor for callers bridging Box S observations
    into the S → X promotion path.
    """
    return PromotionCandidate(
        canonical_term=canonical_term,
        domain=domain,
        title=title,
        content=content,
        source_family=source_family,
        source_uri=source_uri,
        quality_score=quality_score,
        rescue_count=rescue_count,
        explicit_approval=explicit_approval,
        freshness_policy=freshness_policy,
        metadata=dict(metadata or {}),
        extra_canonical_terms=list(extra_canonical_terms or []),
    )
