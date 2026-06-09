"""Phase 3 Commit 33 hit-count tracker tests."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from src.retrieval.hit_count_tracker import (
    HitCountTracker, get_tracker, reset_tracker,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_tracker()
    yield
    reset_tracker()


def test_record_increments_count() -> None:
    t = HitCountTracker()
    t.record("pat_a")
    t.record("pat_a")
    t.record("pat_b")
    assert t.snapshot() == {"pat_a": 2, "pat_b": 1}
    assert t.total() == 3


def test_record_empty_pattern_id_is_noop() -> None:
    t = HitCountTracker()
    t.record("")
    t.record(None)  # type: ignore[arg-type]
    assert t.snapshot() == {}
    assert t.total() == 0


def test_singleton_returns_same_instance() -> None:
    a = get_tracker()
    b = get_tracker()
    assert a is b


def test_concurrent_increments_are_atomic() -> None:
    """200 threads each increment the same pattern 100x. Total must be
    20,000 with no lost updates under contention."""
    t = HitCountTracker()
    barrier = threading.Barrier(200)

    def worker():
        barrier.wait()
        for _ in range(100):
            t.record("pat_x")

    threads = [threading.Thread(target=worker) for _ in range(200)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert t.snapshot()["pat_x"] == 20_000


def test_flush_persists_increments_to_jsonl(tmp_path: Path) -> None:
    """Flush rewrites pattern JSONL files with updated lifecycle.hit_count
    and lifecycle.last_hit_date. Counter is reset after a flush."""
    f = tmp_path / "topic.jsonl"
    obj = {
        "id": "pat_x_001",
        "lifecycle": {"hit_count": 5, "audit_status": "active"},
    }
    f.write_text(json.dumps(obj, ensure_ascii=False) + "\n",
                 encoding="utf-8")

    t = HitCountTracker()
    t.record("pat_x_001")
    t.record("pat_x_001")
    t.record("pat_x_001")
    summary = t.flush(tmp_path)

    assert summary["patterns_updated"] == 1
    assert summary["total_hits"] == 3
    assert summary["files_written"] == 1
    assert summary["errors"] == []

    after = json.loads(f.read_text(encoding="utf-8").strip())
    assert after["lifecycle"]["hit_count"] == 8  # 5 + 3
    assert after["lifecycle"]["last_hit_date"]  # populated
    assert t.snapshot() == {}  # reset after flush


def test_flush_empty_is_noop(tmp_path: Path) -> None:
    t = HitCountTracker()
    summary = t.flush(tmp_path)
    assert summary == {"patterns_updated": 0, "total_hits": 0,
                       "files_written": 0, "errors": []}


def test_flush_handles_missing_lifecycle(tmp_path: Path) -> None:
    f = tmp_path / "topic.jsonl"
    obj = {"id": "pat_y_001"}  # no lifecycle key
    f.write_text(json.dumps(obj) + "\n", encoding="utf-8")

    t = HitCountTracker()
    t.record("pat_y_001")
    summary = t.flush(tmp_path)
    assert summary["patterns_updated"] == 1

    after = json.loads(f.read_text(encoding="utf-8").strip())
    assert after["lifecycle"]["hit_count"] == 1


def test_flush_skips_non_recorded_patterns(tmp_path: Path) -> None:
    """Patterns in the JSONL but not in the tracker are left untouched."""
    f = tmp_path / "topic.jsonl"
    untouched = {
        "id": "pat_quiet",
        "lifecycle": {"hit_count": 99, "audit_status": "active"},
    }
    busy = {"id": "pat_busy", "lifecycle": {"hit_count": 0}}
    f.write_text(
        "\n".join(json.dumps(o) for o in (untouched, busy)) + "\n",
        encoding="utf-8",
    )

    t = HitCountTracker()
    t.record("pat_busy")
    t.flush(tmp_path)

    after = [
        json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_id = {a["id"]: a for a in after}
    assert by_id["pat_quiet"]["lifecycle"]["hit_count"] == 99
    assert by_id["pat_busy"]["lifecycle"]["hit_count"] == 1


def test_route_via_pattern_library_records_hit() -> None:
    """End-to-end: route_via_pattern_library increments tracker for the
    matched pattern."""
    from src.retrieval.pattern_lookup import (
        PatternLibrary, route_via_pattern_library, RouteDecision,
    )
    from src.retrieval.pattern_schema import (
        CrossLingualTestQuery, Origin, Pattern, RouteConfig,
    )
    from datetime import datetime, timezone

    p = Pattern(
        id="pat_self_reference_001",
        topic="self_reference", intent="describe",
        examples=["Tell me about you", "Who are you", "Describe yourself",
                  "What do you do", "What are you"],
        route=RouteConfig(primary_box="box_0",
                           exclude_boxes=["box_w"],
                           synthesis_mode="identity_response"),
        cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="x", expected_match=True),
            CrossLingualTestQuery(lang="ja", query="y", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="z", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="w", expected_match=True),
        ],
        origin=Origin(type="manual", date=datetime.now(timezone.utc)),
    )
    lib = PatternLibrary(patterns={p.id: p}, metadata=[], index=None)

    from src.retrieval import pattern_lookup as pl
    original = pl.route_via_pattern_library
    pl.route_via_pattern_library = lambda q, s, lib: RouteDecision(
        pattern=p, confidence="high", score=0.95,
    )
    try:
        # Direct call to the real function — bypass our mock by reverting
        # before invoking. The mock above is to verify isolation; we want
        # the actual instrumentation path here.
        pl.route_via_pattern_library = original
        # Force a high-confidence single match: synthetic with score 0.95
        # by using a single pattern + a single high-scoring vector
        from types import SimpleNamespace
        lib.metadata = [{"vec_id": 0, "pattern_id": p.id,
                          "example_text": "x", "topic": "self_reference"}]

        class _FakeIndex:
            def search(self, q, k):
                import numpy as np
                # Return one high-scoring hit for vec 0
                return (np.array([[0.95] + [0.0] * (k - 1)]),
                        np.array([[0] + [-1] * (k - 1)]))

        lib.index = _FakeIndex()
        # Inject fake encoder so embedding works
        class _Enc:
            def encode(self, texts, **kw):
                import numpy as np
                return np.zeros((len(texts), 1024), dtype="float32")

        lib.encoder = _Enc()
        decision = pl.route_via_pattern_library("describe yourself",
                                                  session_state=None,
                                                  library=lib)
    finally:
        pl.route_via_pattern_library = original

    assert decision is not None
    tracker = get_tracker()
    snapshot = tracker.snapshot()
    assert snapshot.get(p.id, 0) >= 1
