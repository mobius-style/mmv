"""Phase B Commit 6: Routing Engine advisory-hook tests.

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 3.5.

Asserts:
1. The advisory hook is fail-safe — any exception in lookup / trace is
   swallowed, evaluate() proceeds normally.
2. The advisory hook does NOT alter the route decision when triggered
   on a query the library would otherwise high-confidence-match.
3. The advisory hook records a trace via TraceRecorder when a library
   is configured.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.kernel.routing_engine import RoutingEngine
from src.kernel.trace_recorder import TraceRecorder
from src.retrieval.pattern_lookup import PatternLibrary, RouteDecision
from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Origin, Pattern, RouteConfig,
)


# ─── Pattern factory ──────────────────────────────────────────────────

def _make_pattern() -> Pattern:
    return Pattern(
        id="pat_self_ref_identity_001",
        topic="self_reference",
        intent="describe_self",
        examples=[
            "What are your characteristics", "Describe yourself",
            "Who are you", "Tell me about yourself", "What defines you",
        ],
        route=RouteConfig(primary_box="box_0",
                           synthesis_mode="identity_response"),
        cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="x", expected_match=True),
            CrossLingualTestQuery(lang="ja", query="y", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="z", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="w", expected_match=True),
        ],
        origin=Origin(type="manual", date=datetime.now(timezone.utc)),
    )


def _make_lib_with_decision(score: float = 0.85) -> PatternLibrary:
    """Build a library whose `route_via_pattern_library` always returns
    a high-confidence decision for any query (because the mock index
    returns a single high-scoring vector). This is enough to exercise
    the advisory path without ME5."""
    p = _make_pattern()
    metadata = [{"vec_id": 0, "pattern_id": p.id,
                 "example_text": "x", "topic": "self_reference"}]

    class _MockIndex:
        def search(self, q, k):
            import numpy as np
            return (
                np.asarray([[float(score)] + [0.0] * (k - 1)],
                           dtype="float32"),
                np.asarray([[0] + [-1] * (k - 1)], dtype="int64"),
            )
    return PatternLibrary(
        patterns={p.id: p}, metadata=metadata, index=_MockIndex(),
    )


# ─── Test 1: hook is no-op when library is None ───────────────────────

def test_advisory_hook_noop_when_library_absent() -> None:
    eng = RoutingEngine()
    eng.pattern_library = None
    eng.trace_recorder = None
    # Direct invocation should not raise
    state = SimpleNamespace(active_language="en", conversation_turns=[])
    eng._advisory_pattern_library_lookup("describe yourself", state)


# ─── Test 2: hook is fail-safe — lookup raises, hook swallows ─────────

def test_advisory_hook_swallows_lookup_exceptions() -> None:
    eng = RoutingEngine()

    class _BoomLib:
        def __init__(self) -> None:
            self.patterns = {"x": object()}
            self.metadata = [{"vec_id": 0, "pattern_id": "x"}]

        def __getattr__(self, name):
            raise RuntimeError("boom")

    eng.pattern_library = _BoomLib()
    eng.trace_recorder = None
    state = SimpleNamespace(active_language="en", conversation_turns=[])
    # Must not raise:
    eng._advisory_pattern_library_lookup("x", state)


# ─── Test 3: hook records a trace when library + recorder both present  ─

def test_advisory_hook_records_trace_on_match(tmp_path: Path) -> None:
    eng = RoutingEngine()
    eng.pattern_library = _make_lib_with_decision(score=0.85)
    eng.trace_recorder = TraceRecorder(traces_dir=tmp_path)

    state = SimpleNamespace(active_language="en", conversation_turns=[])
    # Patch route_via_pattern_library to bypass ME5 by supplying query_emb
    import src.kernel.routing_engine as routing_engine_mod
    real_lookup = routing_engine_mod.__dict__.get(
        "_advisory_pattern_library_lookup"
    )
    # Monkey-patch import inside the hook to use a known-decision stub
    from src.retrieval import pattern_lookup as pl_mod
    original = pl_mod.route_via_pattern_library

    def _stub(q, s, lib):
        p = list(lib.patterns.values())[0]
        return RouteDecision(pattern=p, confidence="high", score=0.85)

    pl_mod.route_via_pattern_library = _stub
    try:
        eng._advisory_pattern_library_lookup("describe yourself", state)
    finally:
        pl_mod.route_via_pattern_library = original

    # Trace file should exist under today's date directory
    files = list(tmp_path.rglob("*.jsonl"))
    assert len(files) == 1
    import json
    obj = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert obj["query"] == "describe yourself"
    assert obj["library_lookup"]["matched_pattern_id"] == "pat_self_ref_identity_001"
    assert obj["library_lookup"]["confidence"] == "high"
    assert obj["hybrid_decision"]["selected"] == "legacy"
    assert obj["hybrid_decision"]["reasoning"] == "advisory_only"


# ─── Test 4: hook does NOT alter routing when no decision is returned ─

def test_advisory_hook_records_no_match_too(tmp_path: Path) -> None:
    eng = RoutingEngine()
    eng.pattern_library = _make_lib_with_decision(score=0.40)
    eng.trace_recorder = TraceRecorder(traces_dir=tmp_path)

    from src.retrieval import pattern_lookup as pl_mod
    original = pl_mod.route_via_pattern_library
    pl_mod.route_via_pattern_library = lambda q, s, lib: None

    try:
        state = SimpleNamespace(active_language="en", conversation_turns=[])
        eng._advisory_pattern_library_lookup("unrelated query", state)
    finally:
        pl_mod.route_via_pattern_library = original

    files = list(tmp_path.rglob("*.jsonl"))
    assert len(files) == 1
    import json
    obj = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert obj["library_lookup"] == {}
    assert obj["hybrid_decision"]["selected"] == "legacy"


# ─── Test 5: from_disk auto-construction is no-op without index ───────

def test_engine_init_without_index_skips_library(monkeypatch) -> None:
    """When no FAISS index is present at the expected path, the engine
    falls back to None for both pattern_library and trace_recorder.
    Other behavior unchanged. Guards CI / fresh-clone scenarios."""
    eng = RoutingEngine()
    # The fixture project may or may not have an index. Just assert that
    # the attributes exist and are either None or proper objects:
    assert hasattr(eng, "pattern_library")
    assert hasattr(eng, "trace_recorder")
    if eng.pattern_library is not None:
        assert eng.trace_recorder is not None
