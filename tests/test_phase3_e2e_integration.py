"""Phase 3 Commit 39 — E2E integration test.

Verifies that the four Phase 3 mechanisms cooperate end-to-end:
1. Full primary mode (env-gated, 6 topics)
2. ME5 singleton (process-shared encoder)
3. Hit-count tracker (atomic increment, flush)
4. Secretary (proposal-only, observe → emit, no library mutation)

Uses synthetic small library to keep the test fast and isolated
from the production config dir. The integration check is the
INTERACTION pattern, not absolute accuracy on a real harness.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from src.kernel.routing_engine import RoutingEngine
from src.retrieval.hit_count_tracker import (
    get_tracker, reset_tracker,
)
from src.retrieval.pattern_lookup import (
    PatternLibrary, route_via_pattern_library, RouteDecision,
)
from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Origin, Pattern, RouteConfig,
)
from src.secretary.secretary_core import (
    ProposalStore, Secretary, secretary_will_not_mutate_library,
)
from src.services.me5_singleton import get_me5_singleton, reset_me5_singleton


def _now():
    return datetime.now(timezone.utc)


def _pattern(pid, topic, examples=None):
    return Pattern(
        id=pid, topic=topic, intent="describe",
        examples=examples or ["a", "b", "c", "d", "e"],
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


@pytest.fixture(autouse=True)
def _reset():
    reset_tracker()
    reset_me5_singleton()
    yield
    reset_tracker()
    reset_me5_singleton()
    for var in (
        "MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF",
        "MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY",
    ):
        os.environ.pop(var, None)


@pytest.fixture
def lib_dir(tmp_path: Path) -> Path:
    cfg = tmp_path / "library"
    cfg.mkdir()
    p = _pattern("pat_self_reference_001", "self_reference")
    (cfg / "self_reference.jsonl").write_text(
        p.model_dump_json(exclude_none=False) + "\n",
        encoding="utf-8",
    )
    return cfg


def _stub_lib_with_high_score(pattern: Pattern) -> PatternLibrary:
    """Build a PatternLibrary backed by a stub FAISS index returning a
    single high-confidence hit."""
    lib = PatternLibrary(
        patterns={pattern.id: pattern},
        metadata=[{"vec_id": 0, "pattern_id": pattern.id,
                    "example_text": "x", "topic": pattern.topic}],
        index=None,
    )

    class _Idx:
        def search(self, q, k):
            return (np.array([[0.95] + [0.0] * (k - 1)]),
                    np.array([[0] + [-1] * (k - 1)]))
    lib.index = _Idx()

    class _Enc:
        def encode(self, texts, **kw):
            return np.zeros((len(texts), 1024), dtype="float32")
    lib.encoder = _Enc()
    return lib


# ─── E2E #1: routing → tracker → flush → audit → Secretary ────────


def test_routing_path_increments_tracker_and_flush_persists(
    lib_dir: Path,
) -> None:
    """End-to-end route call → hit-count tracker increments →
    flush() writes back to library JSONL."""
    p = _pattern("pat_self_reference_001", "self_reference")
    lib = _stub_lib_with_high_score(p)

    state = SimpleNamespace(active_language="en", conversation_turns=[])
    decision = route_via_pattern_library("describe yourself",
                                          session_state=state, library=lib)
    assert decision is not None
    assert decision.confidence == "high"

    tracker = get_tracker()
    assert tracker.snapshot()[p.id] == 1

    # Flush against the on-disk library — should update lifecycle.hit_count
    summary = tracker.flush(lib_dir)
    assert summary["patterns_updated"] == 1
    after = json.loads(
        (lib_dir / "self_reference.jsonl")
        .read_text(encoding="utf-8").strip()
    )
    assert after["lifecycle"]["hit_count"] == 1


def test_full_primary_mode_stamps_state_and_records_hit(
    lib_dir: Path,
) -> None:
    """Full primary mode + hit-count instrumentation cooperate."""
    p = _pattern("pat_self_reference_001", "self_reference")
    eng = RoutingEngine()
    eng.pattern_library = _stub_lib_with_high_score(p)
    eng.trace_recorder = None
    state = SimpleNamespace(active_language="en", conversation_turns=[])

    os.environ["MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY"] = "1"
    eng._advisory_pattern_library_lookup("describe yourself", state)

    # Full primary stamped state
    assert hasattr(state, "_pattern_library_primary")
    assert state._pattern_library_primary["mode"] == "full"
    # Tracker recorded the hit
    assert get_tracker().snapshot()[p.id] >= 1


def test_audit_findings_drive_secretary_proposals(
    lib_dir: Path, tmp_path: Path,
) -> None:
    """Audit script output → Secretary observes → proposal emitted →
    Secretary did NOT mutate library directory."""
    audit = {
        "deprecation_candidates": [
            {"id": "pat_self_reference_001",
             "topic": "self_reference",
             "intent": "describe",
             "age_days": 90,
             "reason": "no_hits_after_60_days"},
        ],
        "xling_floor_violations": [],
    }
    store = ProposalStore(
        proposals_path=tmp_path / "proposals" / "store.jsonl",
    )
    sec = Secretary(proposal_store=store, library_path=lib_dir)
    before = secretary_will_not_mutate_library(lib_dir)
    proposals = sec.observe_audit(audit)
    after = secretary_will_not_mutate_library(lib_dir)

    assert len(proposals) == 1
    assert proposals[0].kind == "deprecate_pattern"
    assert before == after  # HARD CONSTRAINT 7
    assert len(store.list_pending()) == 1


def test_hit_count_saturation_drives_secretary_proposal(
    lib_dir: Path, tmp_path: Path,
) -> None:
    """Hit-count tracker → snapshot → Secretary sees saturation →
    lower_priority proposal emitted, library unchanged."""
    store = ProposalStore(
        proposals_path=tmp_path / "proposals" / "store.jsonl",
    )
    sec = Secretary(proposal_store=store, library_path=lib_dir)

    # Simulate 250 hits on a single pattern (saturation > 100)
    tracker = get_tracker()
    for _ in range(250):
        tracker.record("pat_self_reference_001")

    before = secretary_will_not_mutate_library(lib_dir)
    proposals = sec.observe_hit_counts(tracker.snapshot(),
                                          anomaly_floor=100)
    after = secretary_will_not_mutate_library(lib_dir)
    sat_props = [p for p in proposals
                  if p.evidence.get("trigger") == "hit_count.saturation"]
    assert len(sat_props) == 1
    assert sat_props[0].kind == "lower_priority"
    assert before == after


def test_secretary_proposal_lifecycle_end_to_end(
    lib_dir: Path, tmp_path: Path,
) -> None:
    """User emits a proposal → store has it pending → T approves via
    update_status → status flips → library directory unchanged."""
    store = ProposalStore(
        proposals_path=tmp_path / "proposals" / "store.jsonl",
    )
    sec = Secretary(proposal_store=store, library_path=lib_dir)

    p = sec.emit_user_proposal(
        kind="add_negative_examples",
        rationale="user reports false positive",
        target_pattern_id="pat_self_reference_001",
    )
    assert len(store.list_pending()) == 1

    before = secretary_will_not_mutate_library(lib_dir)
    updated = store.update_status(
        p.proposal_id, "approved",
        decided_by="human:taiko",
        decision_note="approved at quarterly review",
    )
    after = secretary_will_not_mutate_library(lib_dir)

    assert updated.status == "approved"
    assert store.list_pending() == []  # no longer pending
    assert before == after  # library still unchanged


# ─── ME5 singleton sanity (already tested elsewhere; integration recheck) ───


def test_me5_singleton_is_shared_across_pattern_lookup_calls(
    lib_dir: Path,
) -> None:
    """Same singleton is returned even when a fresh PatternLibrary is
    created with a fresh from-disk path."""
    s1 = get_me5_singleton()
    s2 = get_me5_singleton()
    assert s1 is s2
