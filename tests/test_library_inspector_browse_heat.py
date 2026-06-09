"""Phase 3 Commit 34 — Library Inspector browse hot/cold heat filter
+ live tracker snapshot tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    cfg = tmp_path / "config" / "pattern_library"
    cfg.mkdir(parents=True)
    monkeypatch.setattr(
        "src.ui.library_inspector.routes.author.CONFIG_DIR", cfg,
    )
    monkeypatch.setattr(
        "src.ui.library_inspector.lib.library_reader.DEFAULT_CONFIG_DIR",
        cfg,
    )

    # Seed a small library with varying hit_counts for the heat filter
    def make(pid, topic, intent, hit_count):
        return {
            "id": pid, "version": "1.0", "lang": "en", "topic": topic,
            "intent": intent, "concepts": [], "priority": 100,
            "examples": ["a", "b", "c", "d", "e"],
            "negative_examples": [],
            "context_required": None, "context_excluded": [],
            "route": {"primary_box": "box_0", "exclude_boxes": [],
                       "synthesis_mode": "default"},
            "tags": [],
            "cross_lingual_test_queries": [
                {"lang": "ja", "query": "a", "expected_match": True,
                 "min_cosine": 0.62},
                {"lang": "ja", "query": "b", "expected_match": True,
                 "min_cosine": 0.62},
                {"lang": "zh", "query": "c", "expected_match": True,
                 "min_cosine": 0.62},
                {"lang": "zh", "query": "d", "expected_match": True,
                 "min_cosine": 0.62},
            ],
            "lifecycle": {"hit_count": hit_count, "audit_status": "active"},
            "origin": {"type": "manual",
                       "date": "2026-04-27T00:00:00Z"},
        }

    seed = [
        make("pat_self_reference_001", "self_reference", "describe", 10),
        make("pat_self_reference_002", "self_reference", "describe2", 5),
        make("pat_self_reference_003", "self_reference", "describe3", 0),
        make("pat_self_reference_004", "self_reference", "describe4", 0),
    ]
    by_topic: dict[str, list] = {}
    for s in seed:
        by_topic.setdefault(s["topic"], []).append(s)
    for topic, pats in by_topic.items():
        with (cfg / f"{topic}.jsonl").open("w", encoding="utf-8") as fh:
            for p in pats:
                fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    from src.ui.library_inspector.app import create_app
    a = create_app(config_dir=cfg)
    a.config.update(TESTING=True)
    return a


@pytest.fixture
def client(app):
    return app.test_client()


def test_default_browse_returns_all_patterns(client) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for pid in ("pat_self_reference_001", "pat_self_reference_002",
                "pat_self_reference_003", "pat_self_reference_004"):
        assert pid in body


def test_heat_hot_filters_to_above_median(client) -> None:
    """Hot = hit_count >= median (which is 2.5 → 5 here, since
    sorted counts are [0, 0, 5, 10] → median index 2 = 5).
    Hot threshold = max(median, 1) = 5. So only 001 (10) and 002 (5)
    qualify."""
    resp = client.get("/?heat=hot")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "pat_self_reference_001" in body
    assert "pat_self_reference_002" in body
    # Cold ones should NOT appear
    assert "pat_self_reference_003" not in body or "><code>pat_self_reference_003</code>" not in body


def test_heat_cold_filters_to_zero_hits(client) -> None:
    resp = client.get("/?heat=cold")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Cold (0 hits)
    assert "pat_self_reference_003" in body
    assert "pat_self_reference_004" in body
    # Hot patterns should NOT appear in main rows
    # (use a stricter check — they may appear in form options)
    assert "><code>pat_self_reference_001</code>" not in body
    assert "><code>pat_self_reference_002</code>" not in body


def test_heat_filter_combined_with_audit_status(client) -> None:
    resp = client.get("/?heat=cold&audit_status=active")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "pat_self_reference_003" in body


def test_tracker_snapshot_panel_appears_when_nonzero(client) -> None:
    """If the in-memory tracker has any hits, the snapshot panel renders."""
    from src.retrieval.hit_count_tracker import get_tracker, reset_tracker
    reset_tracker()
    tracker = get_tracker()
    tracker.record("pat_self_reference_001")
    tracker.record("pat_self_reference_001")
    tracker.record("pat_self_reference_002")

    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Live in-memory tracker" in body
    assert ">3<" in body  # tracker_total is 3
    reset_tracker()


def test_tracker_snapshot_panel_hidden_when_empty(client) -> None:
    from src.retrieval.hit_count_tracker import reset_tracker
    reset_tracker()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Live in-memory tracker" not in body
