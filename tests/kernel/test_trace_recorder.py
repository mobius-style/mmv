"""Tests for src/kernel/trace_recorder.py."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.kernel.trace_recorder import TraceRecorder


def _ts(year: int = 2026, month: int = 4, day: int = 25) -> datetime:
    return datetime(year, month, day, 10, 30, 0, tzinfo=timezone.utc)


def test_record_writes_jsonl_in_date_dir(tmp_path: Path) -> None:
    rec = TraceRecorder(traces_dir=tmp_path)
    when = _ts()
    path = rec.record(
        query="describe yourself",
        timestamp=when,
        library_lookup={"matched_pattern_id": "pat_self_ref_identity_001",
                        "match_score": 0.73, "confidence": "high"},
        legacy_routing={"matched_rule": None, "confidence": 0.4},
        hybrid_decision={"selected": "library", "reasoning": "high"},
        consulted_boxes=["box_0"],
        excluded_boxes=["box_w"],
        final_route="identity_response",
        query_lang_detected="en",
    )
    assert path.exists()
    assert path.parent.name == "2026-04-25"
    assert path.suffix == ".jsonl"
    obj = json.loads(path.read_text(encoding="utf-8").strip())
    for key in ("trace_id", "timestamp", "query", "library_lookup",
                "legacy_routing", "hybrid_decision", "consulted_boxes",
                "excluded_boxes", "final_route"):
        assert key in obj
    assert obj["trace_id"].startswith("trc_20260425_")
    assert obj["timestamp"] == "2026-04-25T10:30:00Z"
    assert obj["query"] == "describe yourself"
    assert obj["consulted_boxes"] == ["box_0"]
    assert obj["excluded_boxes"] == ["box_w"]
    assert obj["final_route"] == "identity_response"


def test_trace_id_format(tmp_path: Path) -> None:
    rec = TraceRecorder(traces_dir=tmp_path)
    p1 = rec.record(query="a", timestamp=_ts())
    p2 = rec.record(query="b", timestamp=_ts())
    obj1 = json.loads(p1.read_text())
    obj2 = json.loads(p2.read_text())
    assert obj1["trace_id"] != obj2["trace_id"]
    assert obj1["trace_id"].startswith("trc_20260425_103000_")
    assert obj2["trace_id"].startswith("trc_20260425_103000_")


def test_atomic_write_no_tmp_residue(tmp_path: Path) -> None:
    rec = TraceRecorder(traces_dir=tmp_path)
    rec.record(query="x", timestamp=_ts())
    leftover = list(tmp_path.rglob("*.tmp"))
    assert leftover == []


def test_sweep_keeps_recent_removes_old(tmp_path: Path) -> None:
    rec = TraceRecorder(traces_dir=tmp_path, retention_days=30)
    today = _ts(2026, 4, 25)
    fresh_dir = tmp_path / today.strftime("%Y-%m-%d")
    fresh_dir.mkdir()
    (fresh_dir / "trc_x.jsonl").write_text("{}")
    boundary_dir = tmp_path / (today - timedelta(days=29)).strftime("%Y-%m-%d")
    boundary_dir.mkdir()
    (boundary_dir / "trc_y.jsonl").write_text("{}")
    old_dir = tmp_path / (today - timedelta(days=31)).strftime("%Y-%m-%d")
    old_dir.mkdir()
    (old_dir / "trc_z.jsonl").write_text("{}")
    very_old_dir = tmp_path / (today - timedelta(days=120)).strftime("%Y-%m-%d")
    very_old_dir.mkdir()
    (very_old_dir / "trc_w.jsonl").write_text("{}")

    removed = rec.sweep_old_dirs(reference=today)
    assert fresh_dir.exists()
    assert boundary_dir.exists()
    assert not old_dir.exists()
    assert not very_old_dir.exists()
    assert set(removed) == {old_dir.name, very_old_dir.name}


def test_sweep_ignores_non_date_dirs(tmp_path: Path) -> None:
    rec = TraceRecorder(traces_dir=tmp_path)
    odd = tmp_path / "not_a_date"
    odd.mkdir()
    (odd / "garbage.txt").write_text("x")
    removed = rec.sweep_old_dirs(reference=_ts())
    assert odd.exists()
    assert "not_a_date" not in removed


def test_record_triggers_sweep(tmp_path: Path) -> None:
    rec = TraceRecorder(traces_dir=tmp_path, retention_days=30)
    old_dir = tmp_path / "2026-01-01"
    old_dir.mkdir()
    (old_dir / "trc_x.jsonl").write_text("{}")
    rec.record(query="q", timestamp=_ts(2026, 4, 25))
    assert not old_dir.exists()


def test_concurrent_writes_no_race(tmp_path: Path) -> None:
    rec = TraceRecorder(traces_dir=tmp_path)
    when = _ts()
    errors: list[Exception] = []

    def writer(i: int) -> None:
        try:
            rec.record(query=f"q{i}", timestamp=when)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    files = list((tmp_path / when.strftime("%Y-%m-%d")).glob("*.jsonl"))
    assert len(files) == 20
    queries = []
    for f in files:
        queries.append(json.loads(f.read_text())["query"])
    assert set(queries) == {f"q{i}" for i in range(20)}


def test_minimal_record_omitted_fields_default_empty(tmp_path: Path) -> None:
    rec = TraceRecorder(traces_dir=tmp_path)
    p = rec.record(query="hi", timestamp=_ts())
    obj = json.loads(p.read_text())
    assert obj["library_lookup"] == {}
    assert obj["legacy_routing"] == {}
    assert obj["hybrid_decision"] == {}
    assert obj["consulted_boxes"] == []
    assert obj["excluded_boxes"] == []
    assert obj["final_route"] is None
    assert obj["query_lang_detected"] is None
