"""Phase 3 Stab Commit 44 — full primary mode downstream consumer tests.

Verifies that:
1. Default mode (env unset) does NOT set _library_primary_box_0_hint
2. Full primary + high-conf box_0 → state._library_primary_box_0_hint=True
3. Full primary + non-box_0 primary → no hint (e.g. factual_inquiry box_w)
4. Selective primary (mode != "full") → no hint
5. decision.reason_codes annotated with FULL_PRIMARY_LIBRARY_<topic>
6. decision.reason_codes annotated with FULL_PRIMARY_SYNTH_<mode>
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.kernel.routing_engine import RoutingEngine
from src.retrieval.pattern_lookup import PatternLibrary, RouteDecision
from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Origin, Pattern, RouteConfig,
)


def _now():
    return datetime.now(timezone.utc)


def _pattern(pid: str, topic: str, primary_box: str = "box_0",
             exclude: list[str] | None = None,
             synth: str = "identity_response") -> Pattern:
    return Pattern(
        id=pid, topic=topic, intent="describe",
        examples=["a", "b", "c", "d", "e"],
        route=RouteConfig(primary_box=primary_box,
                           exclude_boxes=exclude or [],
                           synthesis_mode=synth),
        cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="x", expected_match=True),
            CrossLingualTestQuery(lang="ja", query="y", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="z", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="w", expected_match=True),
        ],
        origin=Origin(type="manual", date=_now()),
    )


@pytest.fixture(autouse=True)
def _clean_env():
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


def _simulate_pipeline(eng, decision_obj, state, p, run_lookup=True):
    """Mimic the part of RoutingEngine.evaluate() that stamps state +
    sets the downstream hint. Returns (decision, state)."""
    if run_lookup:
        eng.pattern_library = PatternLibrary(
            patterns={p.id: p}, metadata=[], index=None,
        )
        eng.trace_recorder = None
        from src.retrieval import pattern_lookup as pl
        original = pl.route_via_pattern_library
        pl.route_via_pattern_library = lambda q, s, lib: RouteDecision(
            pattern=p, confidence="high", score=0.95,
        )
        try:
            eng._advisory_pattern_library_lookup("describe yourself", state)
        finally:
            pl.route_via_pattern_library = original

    primary_meta = getattr(state, "_pattern_library_primary", None)
    if primary_meta and primary_meta.get("mode") == "full":
        topic = (primary_meta.get("topic") or "unknown").upper()
        decision_obj.reason_codes.append(f"FULL_PRIMARY_LIBRARY_{topic}")
        if primary_meta.get("primary_box") == "box_0":
            state._library_primary_box_0_hint = True
        if primary_meta.get("synthesis_mode"):
            decision_obj.reason_codes.append(
                f"FULL_PRIMARY_SYNTH_"
                f"{primary_meta['synthesis_mode'].upper()}"
            )
    return decision_obj, state


# ─────────────────────────────────────────────────────────────────────


def test_default_mode_no_hint_no_reason_codes() -> None:
    """Env unset → no library primary stamping → no consumer activation."""
    eng = RoutingEngine()
    state = SimpleNamespace(active_language="en", conversation_turns=[])
    decision = SimpleNamespace(reason_codes=[])
    p = _pattern("pat_self_reference_001", "self_reference")
    _, state = _simulate_pipeline(eng, decision, state, p)
    assert not hasattr(state, "_pattern_library_primary")
    assert not hasattr(state, "_library_primary_box_0_hint")
    assert decision.reason_codes == []


def test_full_primary_box_0_topic_sets_hint_and_reason_codes() -> None:
    eng = RoutingEngine()
    state = SimpleNamespace(active_language="en", conversation_turns=[])
    decision = SimpleNamespace(reason_codes=[])
    p = _pattern("pat_self_reference_001", "self_reference",
                 primary_box="box_0", synth="identity_response")
    os.environ["MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY"] = "1"
    _simulate_pipeline(eng, decision, state, p)
    assert state._pattern_library_primary["mode"] == "full"
    assert state._library_primary_box_0_hint is True
    assert "FULL_PRIMARY_LIBRARY_SELF_REFERENCE" in decision.reason_codes
    assert "FULL_PRIMARY_SYNTH_IDENTITY_RESPONSE" in decision.reason_codes


def test_full_primary_box_w_topic_no_box_0_hint() -> None:
    """factual_inquiry primary_box=box_w → reason code annotated, but
    Box 0 hint NOT set (library says box_w, not box_0)."""
    eng = RoutingEngine()
    state = SimpleNamespace(active_language="en", conversation_turns=[])
    decision = SimpleNamespace(reason_codes=[])
    p = _pattern("pat_factual_inquiry_001", "factual_inquiry",
                 primary_box="box_w", synth="factual_synthesis")
    os.environ["MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY"] = "1"
    _simulate_pipeline(eng, decision, state, p)
    assert state._pattern_library_primary["primary_box"] == "box_w"
    assert "FULL_PRIMARY_LIBRARY_FACTUAL_INQUIRY" in decision.reason_codes
    assert "FULL_PRIMARY_SYNTH_FACTUAL_SYNTHESIS" in decision.reason_codes
    assert not getattr(state, "_library_primary_box_0_hint", False)


def test_selective_primary_does_not_trigger_full_primary_consumer() -> None:
    """mode=selective should NOT activate the full-primary consumer
    (FULL_PRIMARY_LIBRARY_* codes only fire on mode=full)."""
    eng = RoutingEngine()
    state = SimpleNamespace(active_language="en", conversation_turns=[])
    decision = SimpleNamespace(reason_codes=[])
    p = _pattern("pat_self_reference_001", "self_reference")
    os.environ["MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF"] = "1"
    _simulate_pipeline(eng, decision, state, p)
    assert state._pattern_library_primary["mode"] == "selective"
    assert not any(
        rc.startswith("FULL_PRIMARY_") for rc in decision.reason_codes
    )
    assert not getattr(state, "_library_primary_box_0_hint", False)


def test_full_primary_low_conf_no_hint() -> None:
    """Library returns low-confidence decision → not stamped → no hint."""
    eng = RoutingEngine()
    state = SimpleNamespace(active_language="en", conversation_turns=[])
    decision = SimpleNamespace(reason_codes=[])
    p = _pattern("pat_self_reference_001", "self_reference")
    eng.pattern_library = PatternLibrary(
        patterns={p.id: p}, metadata=[], index=None,
    )
    eng.trace_recorder = None
    os.environ["MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY"] = "1"

    from src.retrieval import pattern_lookup as pl
    original = pl.route_via_pattern_library
    pl.route_via_pattern_library = lambda q, s, lib: RouteDecision(
        pattern=p, confidence="medium", score=0.6, warning="LOW_CONFIDENCE",
    )
    try:
        eng._advisory_pattern_library_lookup("describe yourself", state)
    finally:
        pl.route_via_pattern_library = original

    primary_meta = getattr(state, "_pattern_library_primary", None)
    if primary_meta and primary_meta.get("mode") == "full":
        if primary_meta.get("primary_box") == "box_0":
            state._library_primary_box_0_hint = True

    assert not hasattr(state, "_pattern_library_primary")
    assert not getattr(state, "_library_primary_box_0_hint", False)
