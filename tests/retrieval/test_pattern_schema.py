"""Schema validation tests for src/retrieval/pattern_schema.py."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.retrieval.pattern_schema import (
    CrossLingualTestQuery,
    DeletionProposal,
    Lifecycle,
    LifecycleEvent,
    Origin,
    Pattern,
    RouteConfig,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _minimal_xling() -> list[CrossLingualTestQuery]:
    return [
        CrossLingualTestQuery(lang="ja", query="あなたの特徴は？",
                              expected_match=True, min_cosine=0.6),
        CrossLingualTestQuery(lang="ja", query="ウルトラマンメビウスの特徴",
                              expected_match=False),
        CrossLingualTestQuery(lang="zh", query="你的特征是什么",
                              expected_match=True, min_cosine=0.6),
        CrossLingualTestQuery(lang="zh", query="莫比乌斯环的特征",
                              expected_match=False),
    ]


def _minimal_origin() -> Origin:
    return Origin(type="forensic", date=_now(), evolution_log_entry=21)


def _minimal_route() -> RouteConfig:
    return RouteConfig(primary_box="box_0", synthesis_mode="identity_response")


def _make_pattern(**overrides) -> Pattern:
    base = dict(
        id="pat_self_ref_identity_001",
        topic="self_reference",
        intent="describe_self",
        examples=[
            "What are your characteristics",
            "What are your features",
            "Who are you",
            "Describe yourself",
            "Tell me about yourself",
        ],
        route=_minimal_route(),
        cross_lingual_test_queries=_minimal_xling(),
        origin=_minimal_origin(),
    )
    base.update(overrides)
    return Pattern(**base)


# ── ID format ──────────────────────────────────────────────────────────────

def test_id_valid_format() -> None:
    p = _make_pattern()
    assert p.id == "pat_self_ref_identity_001"


@pytest.mark.parametrize("bad_id", [
    "pat-self-ref-001",
    "pat_self_ref_1",
    "pat_self_ref_0001",
    "self_ref_001",
    "PAT_self_ref_001",
])
def test_id_invalid_format_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        _make_pattern(id=bad_id)


# ── Examples bounds ────────────────────────────────────────────────────────

def test_examples_minimum_5() -> None:
    with pytest.raises(ValidationError):
        _make_pattern(examples=["a", "b", "c", "d"])


def test_examples_maximum_15() -> None:
    with pytest.raises(ValidationError):
        _make_pattern(examples=[f"q{i}" for i in range(16)])


def test_examples_exact_5_ok() -> None:
    p = _make_pattern(examples=["q1", "q2", "q3", "q4", "q5"])
    assert len(p.examples) == 5


def test_examples_exact_15_ok() -> None:
    p = _make_pattern(examples=[f"q{i}" for i in range(15)])
    assert len(p.examples) == 15


# ── Cross-lingual coverage validator ───────────────────────────────────────

def test_cross_lingual_requires_2_ja_and_2_zh() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _make_pattern(cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="x", expected_match=True),
            CrossLingualTestQuery(lang="ja", query="y", expected_match=False),
            CrossLingualTestQuery(lang="zh", query="z", expected_match=True),
            CrossLingualTestQuery(lang="en", query="w", expected_match=False),
        ])
    assert "at least 2 ja and 2 zh" in str(exc_info.value)


def test_cross_lingual_min_length_4() -> None:
    with pytest.raises(ValidationError):
        _make_pattern(cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="x", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="y", expected_match=True),
        ])


# ── Priority bounds ────────────────────────────────────────────────────────

@pytest.mark.parametrize("p_val", [0, 100, 500, 1000])
def test_priority_in_bounds(p_val: int) -> None:
    p = _make_pattern(priority=p_val)
    assert p.priority == p_val


@pytest.mark.parametrize("bad", [-1, 1001, 5000])
def test_priority_out_of_bounds(bad: int) -> None:
    with pytest.raises(ValidationError):
        _make_pattern(priority=bad)


# ── min_cosine bounds ──────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0])
def test_min_cosine_out_of_bounds(bad: float) -> None:
    with pytest.raises(ValidationError):
        CrossLingualTestQuery(
            lang="ja", query="x", expected_match=True, min_cosine=bad
        )


# ── Lifecycle defaults + xling_pass_rate bounds ────────────────────────────

def test_lifecycle_defaults() -> None:
    p = _make_pattern()
    assert p.lifecycle.hit_count == 0
    assert p.lifecycle.last_hit_date is None
    assert p.lifecycle.last_xling_pass_rate is None
    assert p.lifecycle.audit_status == "active"
    assert p.lifecycle.deletion_proposals == []
    assert p.lifecycle.history == []


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_lifecycle_xling_pass_rate_bounds(bad: float) -> None:
    with pytest.raises(ValidationError):
        Lifecycle(last_xling_pass_rate=bad)


# ── Box namespace ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("box", [
    "box_0", "box_1", "box_2", "box_3", "box_4",
    "box_5", "box_6", "box_7", "box_w",
])
def test_route_primary_box_valid(box: str) -> None:
    rc = RouteConfig(primary_box=box, synthesis_mode="x")
    assert rc.primary_box == box


@pytest.mark.parametrize("bad", ["box_8", "box_9", "boxw", "box_W", "1"])
def test_route_primary_box_invalid(bad: str) -> None:
    with pytest.raises(ValidationError):
        RouteConfig(primary_box=bad, synthesis_mode="x")


# ── Lang locked to en ──────────────────────────────────────────────────────

def test_lang_must_be_en() -> None:
    with pytest.raises(ValidationError):
        _make_pattern(lang="ja")


# ── Origin types ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("t", ["forensic", "manual", "autogen", "secretary"])
def test_origin_types_valid(t: str) -> None:
    o = Origin(type=t, date=_now())
    assert o.type == t


def test_origin_type_invalid() -> None:
    with pytest.raises(ValidationError):
        Origin(type="bogus", date=_now())


# ── LifecycleEvent + DeletionProposal smoke ────────────────────────────────

def test_lifecycle_event_basic() -> None:
    ev = LifecycleEvent(
        timestamp=_now(), event="created", actor="taiko", detail="seed"
    )
    assert ev.event == "created"


def test_deletion_proposal_basic() -> None:
    dp = DeletionProposal(
        proposal_id="del_001", proposer="user_x", date=_now(),
        reason="duplicate", status="pending",
    )
    assert dp.status == "pending"


# ── Round-trip via JSON ────────────────────────────────────────────────────

def test_pattern_json_roundtrip() -> None:
    p = _make_pattern()
    serialized = p.model_dump_json()
    p2 = Pattern.model_validate_json(serialized)
    assert p2.id == p.id
    assert p2.examples == p.examples
    assert len(p2.cross_lingual_test_queries) == 4
