"""Lookup helper tests with mock library — no ME5 / FAISS required."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

import numpy as np
import pytest

from src.retrieval.pattern_lookup import (
    NEG_MARGIN, PatternLibrary, RouteDecision, route_via_pattern_library,
)
from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Origin, Pattern, RouteConfig,
)


# ─────────────────────────────────────────────────────────────────────────
# Mock FAISS index — returns pre-baked (scores, indices)
# ─────────────────────────────────────────────────────────────────────────

class MockIndex:
    def __init__(self, scores: list[float], indices: list[int]) -> None:
        self._scores = np.asarray([scores], dtype="float32")
        self._indices = np.asarray([indices], dtype="int64")

    def search(self, query, k):
        # Truncate to first k
        return self._scores[:, :k], self._indices[:, :k]


class StubEncoder:
    """Returns deterministic, predictable vectors keyed by input string.
    Lets tests configure max-cosine of negative examples."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def encode(self, texts, **kwargs):
        out = []
        for t in texts:
            if t not in self._vectors:
                # default: zero vector
                out.append([0.0] * 4)
            else:
                out.append(self._vectors[t])
        return np.asarray(out, dtype="float32")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _xling() -> list[CrossLingualTestQuery]:
    return [
        CrossLingualTestQuery(lang="ja", query="ja1", expected_match=True),
        CrossLingualTestQuery(lang="ja", query="ja2", expected_match=False),
        CrossLingualTestQuery(lang="zh", query="zh1", expected_match=True),
        CrossLingualTestQuery(lang="zh", query="zh2", expected_match=False),
    ]


def _make_pattern(
    pid: str, topic: str = "self_reference", priority: int = 100,
    examples: Optional[list[str]] = None,
    negatives: Optional[list[str]] = None,
    context_excluded: Optional[list[str]] = None,
    deprecated: bool = False,
) -> Pattern:
    return Pattern(
        id=pid,
        topic=topic,
        intent="describe_self",
        priority=priority,
        examples=examples or ["a", "b", "c", "d", "e"],
        negative_examples=negatives or [],
        context_excluded=context_excluded or [],
        route=RouteConfig(primary_box="box_0",
                           synthesis_mode="identity_response"),
        cross_lingual_test_queries=_xling(),
        origin=Origin(type="manual", date=_now()),
        deprecated=deprecated,
    )


def _build_library(
    patterns: list[Pattern], metadata: list[dict],
    scores: list[float], indices: list[int],
    encoder_vectors: Optional[dict[str, list[float]]] = None,
) -> PatternLibrary:
    """Build an in-memory mock library."""
    pat_dict = {p.id: p for p in patterns}
    lib = PatternLibrary(
        patterns=pat_dict, metadata=metadata,
        index=MockIndex(scores, indices),
    )
    if encoder_vectors is not None:
        lib.encoder = StubEncoder(encoder_vectors)
    return lib


def _meta(*pairs: tuple[int, str]) -> list[dict]:
    """Convenience to build a metadata list from (vec_id, pattern_id) pairs."""
    out = []
    for vec_id, pid in pairs:
        out.append({"vec_id": vec_id, "pattern_id": pid,
                    "example_text": "x", "topic": "self_reference"})
    return out


# ─────────────────────────────────────────────────────────────────────────
# 1. high_conf_single — exactly one pattern above HIGH threshold → "high"
# ─────────────────────────────────────────────────────────────────────────

def test_high_confidence_single_pattern() -> None:
    p = _make_pattern("pat_self_ref_identity_001")
    lib = _build_library(
        patterns=[p],
        metadata=_meta((0, p.id), (1, p.id)),
        scores=[0.85, 0.80],
        indices=[0, 1],
    )
    qemb = [1.0, 0.0, 0.0, 0.0]
    decision = route_via_pattern_library(
        "describe yourself", session_state=None,
        library=lib, query_emb=qemb,
    )
    assert decision is not None
    assert decision.confidence == "high"
    assert decision.pattern.id == p.id
    assert decision.score == pytest.approx(0.85)


# ─────────────────────────────────────────────────────────────────────────
# 2. high_conf_multi — >1 pattern above HIGH; resolve via priority
# ─────────────────────────────────────────────────────────────────────────

def test_high_confidence_multiple_resolves_by_priority() -> None:
    p_low = _make_pattern("pat_self_ref_identity_001", priority=100)
    p_high = _make_pattern("pat_self_ref_identity_002", priority=500)
    lib = _build_library(
        patterns=[p_low, p_high],
        metadata=_meta((0, p_low.id), (1, p_high.id)),
        scores=[0.88, 0.90],
        indices=[0, 1],
    )
    qemb = [1.0, 0.0, 0.0, 0.0]
    decision = route_via_pattern_library(
        "describe yourself", session_state=None,
        library=lib, query_emb=qemb,
    )
    assert decision is not None
    assert decision.confidence == "high"
    assert decision.pattern.id == p_high.id  # higher priority wins


# ─────────────────────────────────────────────────────────────────────────
# 3. medium_conf — best pattern between MED and HIGH → "medium" + warning
# ─────────────────────────────────────────────────────────────────────────

def test_medium_confidence() -> None:
    p = _make_pattern("pat_self_ref_identity_001")
    lib = _build_library(
        patterns=[p],
        metadata=_meta((0, p.id)),
        scores=[0.75],
        indices=[0],
    )
    qemb = [1.0, 0.0, 0.0, 0.0]
    decision = route_via_pattern_library(
        "describe", session_state=None,
        library=lib, query_emb=qemb,
    )
    assert decision is not None
    assert decision.confidence == "medium"
    assert decision.warning == "LOW_CONFIDENCE"
    assert decision.score == pytest.approx(0.75)


# ─────────────────────────────────────────────────────────────────────────
# 4. low_conf — best pattern below MED threshold → None
# ─────────────────────────────────────────────────────────────────────────

def test_low_confidence_returns_none() -> None:
    p = _make_pattern("pat_self_ref_identity_001")
    lib = _build_library(
        patterns=[p],
        metadata=_meta((0, p.id)),
        scores=[0.40],
        indices=[0],
    )
    qemb = [1.0, 0.0, 0.0, 0.0]
    decision = route_via_pattern_library(
        "completely unrelated query", session_state=None,
        library=lib, query_emb=qemb,
    )
    assert decision is None


# ─────────────────────────────────────────────────────────────────────────
# 5. neg_filtered — high score but very close to a negative example
# ─────────────────────────────────────────────────────────────────────────

def test_negative_example_filter_blocks_high_score() -> None:
    """Pattern hits 0.85, but the negative-example similarity is also high
    (0.84), giving margin 0.01 < NEG_MARGIN=0.05 → pattern dropped → None."""
    p = _make_pattern(
        "pat_self_ref_identity_001",
        negatives=["What is a Möbius strip"],
    )
    qemb = [1.0, 0.0, 0.0, 0.0]
    encoder_vectors = {
        "passage: What is a Möbius strip": [0.84, 0.0, 0.0, 0.54],
    }
    lib = _build_library(
        patterns=[p],
        metadata=_meta((0, p.id)),
        scores=[0.85],
        indices=[0],
        encoder_vectors=encoder_vectors,
    )

    decision = route_via_pattern_library(
        "tell me about Möbius", session_state=None,
        library=lib, query_emb=qemb,
    )
    assert decision is None  # filtered out by negative-example margin


def test_negative_example_filter_keeps_high_score_with_margin() -> None:
    """Pattern hits 0.85, negative similarity 0.50 → margin 0.35 ≥ 0.05 →
    pattern survives, returns high-confidence decision."""
    p = _make_pattern(
        "pat_self_ref_identity_001",
        negatives=["What is a Möbius strip"],
    )
    qemb = [1.0, 0.0, 0.0, 0.0]
    encoder_vectors = {
        "passage: What is a Möbius strip": [0.50, 0.5, 0.0, 0.5],
    }
    lib = _build_library(
        patterns=[p],
        metadata=_meta((0, p.id)),
        scores=[0.85],
        indices=[0],
        encoder_vectors=encoder_vectors,
    )
    decision = route_via_pattern_library(
        "describe yourself", session_state=None,
        library=lib, query_emb=qemb,
    )
    assert decision is not None
    assert decision.confidence == "high"


# ─────────────────────────────────────────────────────────────────────────
# Additional sanity checks
# ─────────────────────────────────────────────────────────────────────────

def test_empty_library_returns_none() -> None:
    lib = PatternLibrary(patterns={}, metadata=[], index=MockIndex([], []))
    decision = route_via_pattern_library(
        "anything", session_state=None, library=lib, query_emb=[1, 0, 0, 0]
    )
    assert decision is None


def test_deprecated_pattern_excluded() -> None:
    p = _make_pattern("pat_self_ref_identity_001", deprecated=True)
    lib = _build_library(
        patterns=[p],
        metadata=_meta((0, p.id)),
        scores=[0.95],
        indices=[0],
    )
    qemb = [1.0, 0.0, 0.0, 0.0]
    decision = route_via_pattern_library(
        "describe yourself", session_state=None,
        library=lib, query_emb=qemb,
    )
    assert decision is None  # deprecated dropped


def test_context_excluded_filters_pattern() -> None:
    p = _make_pattern(
        "pat_self_ref_identity_001",
        context_excluded=["correction_context"],
    )
    lib = _build_library(
        patterns=[p],
        metadata=_meta((0, p.id)),
        scores=[0.85],
        indices=[0],
    )
    qemb = [1.0, 0.0, 0.0, 0.0]
    state = SimpleNamespace(recent_context=["correction_context"])
    decision = route_via_pattern_library(
        "describe yourself", session_state=state,
        library=lib, query_emb=qemb,
    )
    assert decision is None  # context-excluded


def test_neg_margin_constant_is_0_05() -> None:
    assert NEG_MARGIN == 0.05
