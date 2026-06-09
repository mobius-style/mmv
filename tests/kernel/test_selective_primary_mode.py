"""Phase 2 Commit 20 selective primary mode tests.

Asserts:
1. Default OFF: state has no _pattern_library_primary attribute set
2. Env on + library high-conf + topic=self_reference: state stamped
3. Env on + library low-conf: state NOT stamped
4. Env on + library high-conf + non-self_ref topic: state NOT stamped
5. Env on + library returns None: hook is no-op
6. Hybrid trace records reflect selective-primary firing
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.kernel.routing_engine import RoutingEngine
from src.kernel.trace_recorder import TraceRecorder
from src.retrieval.pattern_lookup import PatternLibrary, RouteDecision
from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Origin, Pattern, RouteConfig,
)


def _now():
    return datetime.now(timezone.utc)


def _self_ref_pattern():
    return Pattern(
        id="pat_self_ref_identity_001",
        topic="self_reference",
        intent="describe_self",
        examples=["Tell me about you", "Describe yourself", "Who are you",
                  "What are your features", "What defines you"],
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


def _factual_pattern():
    p = _self_ref_pattern()
    p2 = p.model_copy(update={
        "id": "pat_factual_inquiry_001",
        "topic": "factual_inquiry",
        "intent": "ask_definition",
    })
    return p2


def _bare_lib_with_decision(p, score=0.9):
    lib = PatternLibrary(
        patterns={p.id: p}, metadata=[], index=None,
    )
    return lib


# ─────────────────────────────────────────────────────────────────────

def test_default_no_primary_stamping() -> None:
    """Without env, even if library returns high-conf self_reference
    decision, state must NOT be stamped with _pattern_library_primary."""
    eng = RoutingEngine()
    eng.pattern_library = _bare_lib_with_decision(_self_ref_pattern())
    eng.trace_recorder = None
    state = SimpleNamespace(active_language="en", conversation_turns=[])

    p = _self_ref_pattern()
    decision = RouteDecision(pattern=p, confidence="high", score=0.9)
    from src.retrieval import pattern_lookup as pl
    original = pl.route_via_pattern_library
    pl.route_via_pattern_library = lambda q, s, lib: decision
    os.environ.pop("MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF", None)
    try:
        eng._advisory_pattern_library_lookup("describe yourself", state)
    finally:
        pl.route_via_pattern_library = original
    assert not hasattr(state, "_pattern_library_primary")


def test_env_on_high_conf_self_ref_stamps_state() -> None:
    eng = RoutingEngine()
    eng.pattern_library = _bare_lib_with_decision(_self_ref_pattern())
    eng.trace_recorder = None
    state = SimpleNamespace(active_language="en", conversation_turns=[])

    p = _self_ref_pattern()
    decision = RouteDecision(pattern=p, confidence="high", score=0.9)
    from src.retrieval import pattern_lookup as pl
    original = pl.route_via_pattern_library
    pl.route_via_pattern_library = lambda q, s, lib: decision
    os.environ["MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF"] = "1"
    try:
        eng._advisory_pattern_library_lookup("describe yourself", state)
    finally:
        pl.route_via_pattern_library = original
        os.environ.pop("MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF", None)

    assert hasattr(state, "_pattern_library_primary")
    primary = state._pattern_library_primary
    assert primary["pattern_id"] == p.id
    assert primary["topic"] == "self_reference"
    assert primary["primary_box"] == "box_0"
    assert primary["exclude_boxes"] == ["box_w"]
    assert primary["synthesis_mode"] == "identity_response"


def test_env_on_low_conf_does_not_stamp() -> None:
    eng = RoutingEngine()
    eng.pattern_library = _bare_lib_with_decision(_self_ref_pattern())
    eng.trace_recorder = None
    state = SimpleNamespace(active_language="en", conversation_turns=[])

    p = _self_ref_pattern()
    decision = RouteDecision(
        pattern=p, confidence="medium", score=0.6,
        warning="LOW_CONFIDENCE",
    )
    from src.retrieval import pattern_lookup as pl
    original = pl.route_via_pattern_library
    pl.route_via_pattern_library = lambda q, s, lib: decision
    os.environ["MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF"] = "1"
    try:
        eng._advisory_pattern_library_lookup("describe yourself", state)
    finally:
        pl.route_via_pattern_library = original
        os.environ.pop("MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF", None)

    assert not hasattr(state, "_pattern_library_primary")


def test_env_on_high_conf_non_self_ref_does_not_stamp() -> None:
    """Selective primary applies ONLY to self_reference topic."""
    eng = RoutingEngine()
    eng.pattern_library = _bare_lib_with_decision(_factual_pattern())
    eng.trace_recorder = None
    state = SimpleNamespace(active_language="en", conversation_turns=[])

    p = _factual_pattern()
    decision = RouteDecision(pattern=p, confidence="high", score=0.95)
    from src.retrieval import pattern_lookup as pl
    original = pl.route_via_pattern_library
    pl.route_via_pattern_library = lambda q, s, lib: decision
    os.environ["MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF"] = "1"
    try:
        eng._advisory_pattern_library_lookup("what is X", state)
    finally:
        pl.route_via_pattern_library = original
        os.environ.pop("MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF", None)

    assert not hasattr(state, "_pattern_library_primary")


def test_env_on_no_decision_is_noop() -> None:
    eng = RoutingEngine()
    eng.pattern_library = _bare_lib_with_decision(_self_ref_pattern())
    eng.trace_recorder = None
    state = SimpleNamespace(active_language="en", conversation_turns=[])

    from src.retrieval import pattern_lookup as pl
    original = pl.route_via_pattern_library
    pl.route_via_pattern_library = lambda q, s, lib: None
    os.environ["MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF"] = "1"
    try:
        eng._advisory_pattern_library_lookup("describe yourself", state)
    finally:
        pl.route_via_pattern_library = original
        os.environ.pop("MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF", None)

    assert not hasattr(state, "_pattern_library_primary")


def test_trace_records_hybrid_decision_field(tmp_path: Path) -> None:
    """When primary fires, trace's hybrid_decision.selected = 'library'.
    When advisory mode (env unset), it's 'legacy'."""
    eng = RoutingEngine()
    eng.pattern_library = _bare_lib_with_decision(_self_ref_pattern())
    eng.trace_recorder = TraceRecorder(traces_dir=tmp_path)

    p = _self_ref_pattern()
    decision = RouteDecision(pattern=p, confidence="high", score=0.9)
    from src.retrieval import pattern_lookup as pl
    original = pl.route_via_pattern_library
    pl.route_via_pattern_library = lambda q, s, lib: decision

    state = SimpleNamespace(active_language="en", conversation_turns=[])
    os.environ["MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF"] = "1"
    try:
        eng._advisory_pattern_library_lookup("describe yourself", state)
    finally:
        pl.route_via_pattern_library = original
        os.environ.pop("MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF", None)

    files = list(tmp_path.rglob("*.jsonl"))
    assert len(files) == 1
    obj = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert obj["hybrid_decision"]["selected"] == "library"
    assert obj["hybrid_decision"]["reasoning"] == "selective_primary_self_ref"
    assert obj["library_lookup"]["topic"] == "self_reference"
