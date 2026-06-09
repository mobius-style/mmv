"""Phase 4 v2 Commit 3-4 — sub_topic schema + index metadata + threshold tests."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from src.retrieval.pattern_lookup import PatternLibrary, route_via_pattern_library, RouteDecision
from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Origin, Pattern, RouteConfig,
)


def _now():
    return datetime.now(timezone.utc)


def _pattern(pid: str, topic: str, sub_topic: str = "",
             primary_box: str = "box_0") -> Pattern:
    return Pattern(
        id=pid, topic=topic, sub_topic=sub_topic, intent="describe",
        examples=["a", "b", "c", "d", "e"],
        route=RouteConfig(primary_box=primary_box,
                           exclude_boxes=[],
                           synthesis_mode="identity_response"),
        cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="x", expected_match=True),
            CrossLingualTestQuery(lang="ja", query="y", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="z", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="w", expected_match=True),
        ],
        origin=Origin(type="manual", date=_now()),
    )


# ─── Pattern schema sub_topic field ─────────────────────────────────


def test_pattern_default_sub_topic_is_empty_string() -> None:
    p = _pattern("pat_self_reference_001", "self_reference")
    assert p.sub_topic == ""


def test_pattern_sub_topic_round_trips_via_jsonl() -> None:
    p = _pattern("pat_self_reference_001", "self_reference",
                 sub_topic="sr_identity")
    raw = p.model_dump(exclude_none=False)
    p2 = Pattern.model_validate(raw)
    assert p2.sub_topic == "sr_identity"


def test_pattern_legacy_jsonl_without_sub_topic_validates() -> None:
    """Phase 1-3 patterns serialized without sub_topic must still
    validate (backward compat for any pre-migration JSONL)."""
    raw = _pattern("pat_self_reference_001", "self_reference").model_dump(
        exclude_none=False,
    )
    raw.pop("sub_topic", None)
    p = Pattern.model_validate(raw)
    assert p.sub_topic == ""


# ─── PatternLibrary.coverage_by_sub_topic ─────────────────────────


def test_coverage_by_sub_topic_empty_library() -> None:
    lib = PatternLibrary(patterns={}, metadata=[], index=None)
    assert lib.coverage_by_sub_topic() == {}


def test_coverage_by_sub_topic_groups_correctly() -> None:
    a = _pattern("pat_self_reference_001", "self_reference",
                 sub_topic="sr_identity")
    b = _pattern("pat_self_reference_002", "self_reference",
                 sub_topic="sr_identity")
    c = _pattern("pat_self_reference_003", "self_reference",
                 sub_topic="sr_capabilities")
    d = _pattern("pat_self_reference_004", "self_reference")  # legacy, no sub_topic
    lib = PatternLibrary(
        patterns={p.id: p for p in (a, b, c, d)},
        metadata=[], index=None,
    )
    assert lib.coverage_by_sub_topic() == {
        "sr_identity": 2,
        "sr_capabilities": 1,
        "": 1,
    }


# ─── PatternLibrary.from_disk loads sub_topic thresholds ──────────


def test_from_disk_loads_sub_topic_thresholds(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    p = _pattern("pat_self_reference_001", "self_reference",
                 sub_topic="sr_identity")
    (cfg / "self_reference.jsonl").write_text(
        p.model_dump_json(exclude_none=False) + "\n",
        encoding="utf-8",
    )
    thresholds_path = tmp_path / "thresholds.yaml"
    thresholds_path.write_text(yaml.safe_dump({
        "self_reference": {"high": 0.85, "med": 0.65},
        "sub_topics": {
            "sr_identity": {"high": 0.92, "med": 0.70},
            "sr_capabilities": {"high": 0.88, "med": 0.68},
        },
    }), encoding="utf-8")

    # Build a tiny FAISS index
    import faiss
    import numpy as np
    index = faiss.IndexFlatIP(1024)
    index.add(np.zeros((1, 1024), dtype="float32"))
    index_path = tmp_path / "idx.faiss"
    faiss.write_index(index, str(index_path))
    metadata_path = tmp_path / "meta.jsonl"
    metadata_path.write_text(json.dumps({
        "vec_id": 0, "pattern_id": p.id,
        "example_text": "a", "topic": "self_reference",
        "sub_topic": "sr_identity",
    }) + "\n", encoding="utf-8")

    lib = PatternLibrary.from_disk(cfg, index_path, metadata_path,
                                    thresholds_path=thresholds_path)
    assert lib.high_thresholds["self_reference"] == 0.85
    assert lib.med_thresholds["self_reference"] == 0.65
    assert lib.sub_topic_high_thresholds["sr_identity"] == 0.92
    assert lib.sub_topic_med_thresholds["sr_identity"] == 0.70
    assert lib.sub_topic_high_thresholds["sr_capabilities"] == 0.88


def test_from_disk_no_sub_topic_yaml_section_works(tmp_path: Path) -> None:
    """Pre-Phase-4 thresholds.yaml without sub_topics section continues
    to work; sub_topic_high/med dicts are empty."""
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    p = _pattern("pat_self_reference_001", "self_reference")
    (cfg / "self_reference.jsonl").write_text(
        p.model_dump_json(exclude_none=False) + "\n",
        encoding="utf-8",
    )
    thresholds_path = tmp_path / "thresholds.yaml"
    thresholds_path.write_text(yaml.safe_dump({
        "self_reference": {"high": 0.85, "med": 0.65},
    }), encoding="utf-8")

    import faiss
    import numpy as np
    index = faiss.IndexFlatIP(1024)
    index.add(np.zeros((1, 1024), dtype="float32"))
    index_path = tmp_path / "idx.faiss"
    faiss.write_index(index, str(index_path))
    metadata_path = tmp_path / "meta.jsonl"
    metadata_path.write_text(json.dumps({
        "vec_id": 0, "pattern_id": p.id,
        "example_text": "a", "topic": "self_reference",
    }) + "\n", encoding="utf-8")

    lib = PatternLibrary.from_disk(cfg, index_path, metadata_path,
                                    thresholds_path=thresholds_path)
    assert lib.sub_topic_high_thresholds == {}
    assert lib.sub_topic_med_thresholds == {}


# ─── route_via_pattern_library prefers sub_topic threshold when set ─


def _build_library(p: Pattern, score: float, sub_high: dict | None = None):
    """Helper: stub library with a single pattern + a synthetic FAISS
    index that returns `score` for the first vector."""
    import numpy as np
    lib = PatternLibrary(
        patterns={p.id: p},
        metadata=[{
            "vec_id": 0, "pattern_id": p.id, "example_text": "x",
            "topic": p.topic, "sub_topic": p.sub_topic,
        }],
        index=None,
        sub_topic_high_thresholds=sub_high or {},
    )

    class _Idx:
        def search(self, q, k):
            return (np.array([[score] + [0.0] * (k - 1)]),
                    np.array([[0] + [-1] * (k - 1)]))
    lib.index = _Idx()

    class _Enc:
        def encode(self, texts, **kw):
            return np.zeros((len(texts), 1024), dtype="float32")
    lib.encoder = _Enc()
    return lib


def test_sub_topic_threshold_overrides_topic_threshold() -> None:
    """When pattern has sub_topic AND sub_topic threshold defined,
    sub-topic value is used. Score 0.86 with topic_high=0.84 (would
    pass) but sub_topic_high=0.92 (does not pass) → must NOT match."""
    p = _pattern("pat_self_reference_001", "self_reference",
                 sub_topic="sr_identity")
    lib = _build_library(p, score=0.86, sub_high={"sr_identity": 0.92})
    lib.high_thresholds = {"self_reference": 0.84}
    lib.med_thresholds = {"self_reference": 0.65}

    decision = route_via_pattern_library(
        "test query", session_state=None, library=lib,
    )
    # Score 0.86 falls below sub_topic high (0.92) but above topic high
    # (0.84). With sub-topic preference, should land in medium band
    # (between 0.65 and 0.92) — but our sub_topic_med_thresholds is
    # empty, so falls back to topic-level med 0.65 → medium.
    assert decision is not None
    assert decision.confidence == "medium"


def test_sub_topic_threshold_fallback_to_topic_when_undefined() -> None:
    """Pattern sub_topic="sr_identity" but no sub_topic threshold
    defined → fall back to topic-level threshold."""
    p = _pattern("pat_self_reference_001", "self_reference",
                 sub_topic="sr_identity")
    lib = _build_library(p, score=0.86, sub_high={})  # no sub-topic override
    lib.high_thresholds = {"self_reference": 0.84}
    lib.med_thresholds = {"self_reference": 0.65}

    decision = route_via_pattern_library(
        "test query", session_state=None, library=lib,
    )
    assert decision is not None
    assert decision.confidence == "high"  # 0.86 > topic_high 0.84


def test_legacy_pattern_no_sub_topic_uses_topic_threshold() -> None:
    """Pattern with sub_topic="" must fall back to topic threshold
    even if sub_topic_high_thresholds dict has unrelated entries."""
    p = _pattern("pat_self_reference_001", "self_reference",
                 sub_topic="")
    lib = _build_library(p, score=0.90,
                          sub_high={"sr_identity": 0.95})
    lib.high_thresholds = {"self_reference": 0.84}
    lib.med_thresholds = {"self_reference": 0.65}

    decision = route_via_pattern_library(
        "test query", session_state=None, library=lib,
    )
    assert decision is not None
    assert decision.confidence == "high"  # 0.90 > topic 0.84
