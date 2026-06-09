"""Phase 3 Commit 30 full primary mode tests.

Asserts:
1. Default (no env): no _pattern_library_primary stamping
2. FULL_PRIMARY=1 + high-conf any of 6 topics → state stamped (mode=full)
3. FULL_PRIMARY=1 + low-conf any topic → not stamped
4. FULL_PRIMARY=1 + None decision → no-op
5. FULL_PRIMARY takes precedence over PRIMARY_SELF_REF (both set → mode=full)
6. Trace reasoning reflects full_primary_<topic> when full mode fires
7. Backward compat: PRIMARY_SELF_REF still works for self_reference only
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.kernel.routing_engine import RoutingEngine
from src.kernel.trace_recorder import TraceRecorder
from src.retrieval.pattern_lookup import PatternLibrary, RouteDecision
from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Origin, Pattern, RouteConfig,
)


SUPPORTED_TOPICS = [
    "self_reference",
    "conceptual_explain",
    "factual_inquiry",
    "correction",
    "casual_engagement",
    "casual_greeting",
]


def _now():
    return datetime.now(timezone.utc)


def _pattern(topic: str, pid: str | None = None) -> Pattern:
    return Pattern(
        id=pid or f"pat_{topic}_001",
        topic=topic,
        intent="describe_topic",
        examples=["a", "b", "c", "d", "e"],
        route=RouteConfig(primary_box="box_0",
                           exclude_boxes=["box_w"],
                           synthesis_mode="identity_response"),
        cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="x", expected_match=True),
            CrossLingualTestQuery(lang="ja", query="y", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="z", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="w", expected_match=True),
        ],
        origin=Origin(type="manual", date=_now()),
    )


def _bare_lib(p: Pattern) -> PatternLibrary:
    return PatternLibrary(patterns={p.id: p}, metadata=[], index=None)


def _run_lookup(eng: RoutingEngine, decision, query="q", state=None):
    state = state or SimpleNamespace(active_language="en", conversation_turns=[])
    from src.retrieval import pattern_lookup as pl
    original = pl.route_via_pattern_library
    pl.route_via_pattern_library = lambda q, s, lib: decision
    try:
        eng._advisory_pattern_library_lookup(query, state)
    finally:
        pl.route_via_pattern_library = original
    return state


@pytest.fixture(autouse=True)
def _clean_env():
    # Phase 3 + Phase 2 vars cleared before/after each test
    for var in (
        "MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF",
        "MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY",
    ):
        os.environ.pop(var, None)
    yield
    for var in (
        "MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF",
        "MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY",
    ):
        os.environ.pop(var, None)


# ─────────────────────────────────────────────────────────────────────


def test_default_no_stamping_for_full_primary() -> None:
    """Without FULL_PRIMARY env, even high-conf decision must not stamp."""
    eng = RoutingEngine()
    p = _pattern("factual_inquiry")
    eng.pattern_library = _bare_lib(p)
    eng.trace_recorder = None

    decision = RouteDecision(pattern=p, confidence="high", score=0.9)
    state = _run_lookup(eng, decision)
    assert not hasattr(state, "_pattern_library_primary")


@pytest.mark.parametrize("topic", SUPPORTED_TOPICS)
def test_full_primary_stamps_all_six_topics(topic: str) -> None:
    """FULL_PRIMARY=1 + high-conf for any of 6 topics → state stamped."""
    eng = RoutingEngine()
    p = _pattern(topic)
    eng.pattern_library = _bare_lib(p)
    eng.trace_recorder = None

    decision = RouteDecision(pattern=p, confidence="high", score=0.92)
    os.environ["MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY"] = "1"
    state = _run_lookup(eng, decision)

    assert hasattr(state, "_pattern_library_primary")
    primary = state._pattern_library_primary
    assert primary["pattern_id"] == p.id
    assert primary["topic"] == topic
    assert primary["mode"] == "full"


def test_full_primary_low_conf_does_not_stamp() -> None:
    eng = RoutingEngine()
    p = _pattern("factual_inquiry")
    eng.pattern_library = _bare_lib(p)
    eng.trace_recorder = None

    decision = RouteDecision(
        pattern=p, confidence="medium", score=0.6, warning="LOW_CONFIDENCE",
    )
    os.environ["MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY"] = "1"
    state = _run_lookup(eng, decision)
    assert not hasattr(state, "_pattern_library_primary")


def test_full_primary_no_decision_is_noop() -> None:
    eng = RoutingEngine()
    p = _pattern("conceptual_explain")
    eng.pattern_library = _bare_lib(p)
    eng.trace_recorder = None

    os.environ["MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY"] = "1"
    state = _run_lookup(eng, None)
    assert not hasattr(state, "_pattern_library_primary")


def test_full_primary_takes_precedence_over_selective() -> None:
    """When both env vars are set, FULL_PRIMARY wins (mode=full)."""
    eng = RoutingEngine()
    p = _pattern("self_reference")
    eng.pattern_library = _bare_lib(p)
    eng.trace_recorder = None

    decision = RouteDecision(pattern=p, confidence="high", score=0.95)
    os.environ["MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF"] = "1"
    os.environ["MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY"] = "1"
    state = _run_lookup(eng, decision)

    assert hasattr(state, "_pattern_library_primary")
    assert state._pattern_library_primary["mode"] == "full"


def test_trace_reasoning_full_primary(tmp_path: Path) -> None:
    eng = RoutingEngine()
    p = _pattern("correction")
    eng.pattern_library = _bare_lib(p)
    eng.trace_recorder = TraceRecorder(traces_dir=tmp_path)

    decision = RouteDecision(pattern=p, confidence="high", score=0.9)
    os.environ["MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY"] = "1"
    _run_lookup(eng, decision, query="actually it should be X")

    files = list(tmp_path.rglob("*.jsonl"))
    assert len(files) == 1
    obj = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert obj["hybrid_decision"]["selected"] == "library"
    assert obj["hybrid_decision"]["reasoning"] == "full_primary_correction"


def test_selective_only_still_self_ref_only() -> None:
    """Backward compat: PRIMARY_SELF_REF without FULL_PRIMARY only stamps
    self_reference. A high-conf factual_inquiry decision must NOT stamp."""
    eng = RoutingEngine()
    p = _pattern("factual_inquiry")
    eng.pattern_library = _bare_lib(p)
    eng.trace_recorder = None

    decision = RouteDecision(pattern=p, confidence="high", score=0.9)
    os.environ["MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF"] = "1"
    state = _run_lookup(eng, decision)
    assert not hasattr(state, "_pattern_library_primary")


def test_selective_only_self_ref_still_stamps_with_mode_selective() -> None:
    eng = RoutingEngine()
    p = _pattern("self_reference")
    eng.pattern_library = _bare_lib(p)
    eng.trace_recorder = None

    decision = RouteDecision(pattern=p, confidence="high", score=0.9)
    os.environ["MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF"] = "1"
    state = _run_lookup(eng, decision)

    assert hasattr(state, "_pattern_library_primary")
    assert state._pattern_library_primary["mode"] == "selective"
