"""
pattern_lookup.py — route_via_pattern_library() implementation.

Authoritative reference: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 3.

Flow:
    1. Embed query (ME5 + "query: " prefix)
    2. FAISS top-K=20 over example index
    3. Max-pool scores by pattern_id
    4. Negative-example filter (NEG_MARGIN=0.05)
    5. Context filter (context_required / context_excluded)
    6. Threshold filter (per-topic HIGH/MED)
    7. Conflict resolution (priority → score → context → id)
    8. Return RouteDecision or None

`route_via_pattern_library` returns None when the library cannot
confidently route — caller falls back to legacy regex routing.

Library construction is decoupled from inference for testability:
    - PatternLibrary.from_disk(...)  loads from config/data dirs
    - PatternLibrary(patterns=..., metadata=..., index=..., thresholds=...)
      can be built in-memory by tests with a mock index.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .pattern_schema import Pattern

NEG_MARGIN = 0.05
TOP_K = 20

DEFAULT_HIGH_THRESHOLDS: dict[str, float] = {
    "self_reference":     0.85,
    "factual_inquiry":    0.85,
    "correction":         0.82,
    "conceptual_explain": 0.86,
    "casual_engagement":  0.85,
    "casual_greeting":    0.85,
}
DEFAULT_MED_THRESHOLDS: dict[str, float] = {
    "self_reference":     0.65,
    "factual_inquiry":    0.70,
    "correction":         0.65,
    "conceptual_explain": 0.65,
    "casual_engagement":  0.70,
    "casual_greeting":    0.70,
}


@dataclass
class RouteDecision:
    pattern: Pattern
    confidence: str  # "high" or "medium"
    score: float
    warning: Optional[str] = None


@dataclass
class PatternLibrary:
    patterns: dict[str, Pattern]              # pattern_id → Pattern
    metadata: list[dict]                       # vec_id → {pattern_id, ...}
    index: Any                                  # faiss.Index
    high_thresholds: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_HIGH_THRESHOLDS)
    )
    med_thresholds: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_MED_THRESHOLDS)
    )
    # Phase 4 v2 Commit 4: per-sub-topic threshold overrides (topic-level
    # values still apply when sub_topic is empty or missing from this dict).
    sub_topic_high_thresholds: dict[str, float] = field(default_factory=dict)
    sub_topic_med_thresholds: dict[str, float] = field(default_factory=dict)
    encoder: Any = None                         # SentenceTransformer
    _neg_emb_cache: dict[str, list] = field(default_factory=dict)

    def coverage_by_sub_topic(self) -> dict[str, int]:
        """Phase 4 v2 Commit 3 helper: counts patterns per sub_topic.

        Returns ``{sub_topic: count}``; the empty-string key collects
        legacy patterns that have no sub_topic assigned (Phase 1-3
        residue). Useful for milestone gap analysis."""
        counts: dict[str, int] = {}
        for p in self.patterns.values():
            sub = getattr(p, "sub_topic", "") or ""
            counts[sub] = counts.get(sub, 0) + 1
        return counts

    # Phase 4 audit Commit 16: align with build_pattern_index +
    # conflict_checker. By default, exclude patterns whose
    # lifecycle.audit_status flags them as deprecation_candidate /
    # deprecated / under_review. They remain in JSONL (audit trail)
    # but are not loaded into the active library used for routing.
    INACTIVE_STATUSES = {"deprecation_candidate", "deprecated", "under_review"}

    @classmethod
    def from_disk(
        cls, config_dir: Path, index_path: Path, metadata_path: Path,
        thresholds_path: Optional[Path] = None,
        include_inactive: bool = False,
    ) -> "PatternLibrary":
        import faiss
        import json
        patterns: dict[str, Pattern] = {}
        for jsonl in sorted(Path(config_dir).glob("*.jsonl")):
            if jsonl.name.startswith("_"):
                continue
            with jsonl.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    raw = json.loads(line)
                    p = Pattern.model_validate(raw)
                    if not include_inactive:
                        status = getattr(p.lifecycle, "audit_status",
                                         "active")
                        if status in cls.INACTIVE_STATUSES:
                            continue
                    patterns[p.id] = p
        metadata: list[dict] = []
        with Path(metadata_path).open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    metadata.append(json.loads(line))
        index = faiss.read_index(str(index_path))
        high_t = dict(DEFAULT_HIGH_THRESHOLDS)
        med_t = dict(DEFAULT_MED_THRESHOLDS)
        # Phase 4 v2 Commit 4: per-sub-topic threshold overrides.
        # YAML may carry a top-level `sub_topics:` mapping in addition
        # to the existing per-topic root keys. Both shapes are supported.
        sub_high_t: dict[str, float] = {}
        sub_med_t: dict[str, float] = {}
        if thresholds_path and Path(thresholds_path).exists():
            try:
                import yaml
                t = yaml.safe_load(Path(thresholds_path).read_text())
                for key, vals in (t or {}).items():
                    if key == "sub_topics" and isinstance(vals, dict):
                        for sid, svals in vals.items():
                            if not isinstance(svals, dict):
                                continue
                            if "high" in svals:
                                sub_high_t[sid] = float(svals["high"])
                            if "med" in svals:
                                sub_med_t[sid] = float(svals["med"])
                    elif isinstance(vals, dict):
                        if "high" in vals:
                            high_t[key] = float(vals["high"])
                        if "med" in vals:
                            med_t[key] = float(vals["med"])
            except Exception:
                pass
        return cls(
            patterns=patterns, metadata=metadata, index=index,
            high_thresholds=high_t, med_thresholds=med_t,
            sub_topic_high_thresholds=sub_high_t,
            sub_topic_med_thresholds=sub_med_t,
        )


def _embed_query(library: PatternLibrary, query: str):
    """ME5 query encoding. Phase 3 Commit 28: prefer the process-shared
    ME5 singleton; fall back to per-library encoder for tests that
    inject one directly."""
    import numpy as np
    if library.encoder is not None:
        # Test path: caller injected an encoder. Honor it.
        vec = library.encoder.encode(
            ["query: " + query],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vec, dtype="float32")
    # Production path: use process-shared singleton (one ME5 load per
    # process, regardless of how many PatternLibrary instances exist).
    from src.services.me5_singleton import get_me5_singleton
    singleton = get_me5_singleton()
    return singleton.encode_query(query).reshape(1, -1)


def _embed_negatives(library: PatternLibrary, pattern: Pattern):
    """Cache negative-example embeddings on first use. Phase 3 Commit 28:
    prefer the process-shared singleton."""
    import numpy as np
    if pattern.id in library._neg_emb_cache:
        return library._neg_emb_cache[pattern.id]
    if not pattern.negative_examples:
        library._neg_emb_cache[pattern.id] = None
        return None
    if library.encoder is not None:
        vecs = library.encoder.encode(
            ["passage: " + n for n in pattern.negative_examples],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    else:
        from src.services.me5_singleton import get_me5_singleton
        singleton = get_me5_singleton()
        vecs = singleton.encode_batch(
            pattern.negative_examples, prefix="passage: ",
        )
    arr = np.asarray(vecs, dtype="float32")
    library._neg_emb_cache[pattern.id] = arr
    return arr


def _aggregate_by_pattern(
    scores: list[float], indices: list[int], metadata: list[dict],
) -> dict[str, float]:
    by_pat: dict[str, float] = {}
    for s, vec_id in zip(scores, indices):
        if vec_id < 0 or vec_id >= len(metadata):
            continue
        pid = metadata[vec_id]["pattern_id"]
        if pid not in by_pat or s > by_pat[pid]:
            by_pat[pid] = float(s)
    return by_pat


def _matches_context(pattern: Pattern, session_state: Any) -> bool:
    """Return True if the session state is compatible with the pattern's
    context_required/context_excluded constraints. Conservative default:
    if session_state is None or has no context attr, only accept patterns
    that are not context-restrictive."""
    if pattern.context_required and not session_state:
        return False
    excluded = set(pattern.context_excluded or [])
    if not excluded:
        return True
    state_ctx = set()
    for attr in ("recent_context", "context_tags", "context"):
        v = getattr(session_state, attr, None)
        if isinstance(v, (list, set, tuple)):
            state_ctx |= set(v)
        elif isinstance(v, str):
            state_ctx.add(v)
    return state_ctx.isdisjoint(excluded)


def _resolve_conflict(
    pattern_ids: list[str], pattern_scores: dict[str, float],
    library: PatternLibrary, session_state: Any,
) -> str:
    """Spec Section 3.4 priority → score → context fit → id."""
    def context_fit_score(pid: str) -> int:
        return 1 if _matches_context(library.patterns[pid], session_state) else 0
    return max(
        pattern_ids,
        key=lambda pid: (
            library.patterns[pid].priority,
            pattern_scores[pid],
            context_fit_score(pid),
            -ord(pid[0]) if pid else 0,
            pid,
        ),
    )


def route_via_pattern_library(
    query: str, session_state: Any, library: PatternLibrary,
    *, query_emb=None,
) -> Optional[RouteDecision]:
    """Spec Section 3.1 main entry.

    `query_emb` may be supplied by tests that want to bypass ME5 — when set,
    embedding is reused; negative-example embeddings still go through the
    encoder unless individual patterns have them pre-cached on the library.
    """
    import numpy as np
    if not library.patterns or not library.metadata:
        return None

    qvec = _embed_query(library, query) if query_emb is None else np.asarray(
        query_emb, dtype="float32"
    ).reshape(1, -1)

    D, I = library.index.search(qvec, TOP_K)
    pat_scores = _aggregate_by_pattern(
        D[0].tolist(), I[0].tolist(), library.metadata
    )

    # Step 4: deprecated + negative filter
    for pid in list(pat_scores.keys()):
        p = library.patterns.get(pid)
        if p is None or p.deprecated:
            pat_scores.pop(pid, None)
            continue
        neg_arr = _embed_negatives(library, p)
        if neg_arr is None:
            continue
        # Cosine via inner product on normalized vectors
        max_neg = float(neg_arr.dot(qvec[0]).max())
        if pat_scores[pid] - max_neg < NEG_MARGIN:
            pat_scores.pop(pid, None)

    # Step 5: context filter
    candidates = [
        pid for pid in pat_scores
        if _matches_context(library.patterns[pid], session_state)
    ]

    # Step 6: threshold filter
    high_conf: list[str] = []
    med_conf: list[str] = []
    for pid in candidates:
        p = library.patterns[pid]
        score = pat_scores[pid]
        # Phase 4 v2 Commit 4: prefer per-sub-topic threshold when the
        # pattern has a non-empty sub_topic AND that sub_topic has a
        # threshold defined. Otherwise fall back to topic-level value
        # (Phase 1-3 behavior preserved).
        sub = getattr(p, "sub_topic", "") or ""
        if sub and sub in library.sub_topic_high_thresholds:
            high_t = library.sub_topic_high_thresholds[sub]
        else:
            high_t = library.high_thresholds.get(p.topic, 0.999)
        if sub and sub in library.sub_topic_med_thresholds:
            med_t = library.sub_topic_med_thresholds[sub]
        else:
            med_t = library.med_thresholds.get(p.topic, 0.999)
        if score > high_t:
            high_conf.append(pid)
        elif med_t < score <= high_t:
            med_conf.append(pid)

    # Step 7: conflict resolution + hit-count instrumentation (Phase 3
    # Commit 33). The tracker is process-shared; record() is O(1) and
    # never raises. flush() persists deltas back to JSONL on demand.
    chosen_pid: Optional[str] = None
    if len(high_conf) == 1:
        chosen_pid = high_conf[0]
        decision = RouteDecision(
            pattern=library.patterns[chosen_pid], confidence="high",
            score=pat_scores[chosen_pid],
        )
    elif len(high_conf) > 1:
        chosen_pid = _resolve_conflict(
            high_conf, pat_scores, library, session_state,
        )
        decision = RouteDecision(
            pattern=library.patterns[chosen_pid], confidence="high",
            score=pat_scores[chosen_pid],
        )
    elif med_conf:
        chosen_pid = max(med_conf, key=lambda p: pat_scores[p])
        decision = RouteDecision(
            pattern=library.patterns[chosen_pid], confidence="medium",
            score=pat_scores[chosen_pid], warning="LOW_CONFIDENCE",
        )
    else:
        return None

    if chosen_pid is not None:
        try:
            from src.retrieval.hit_count_tracker import get_tracker
            get_tracker().record(chosen_pid)
        except Exception:
            pass  # instrumentation must never break routing
    return decision
