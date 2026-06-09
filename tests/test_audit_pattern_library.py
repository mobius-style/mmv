"""Phase 3 Commit 35 audit_pattern_library tests."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.audit_pattern_library import (
    compute_audit, render_markdown, _percentile,
)


def _now():
    return datetime.now(timezone.utc)


def make(pid, topic, intent, hit_count=0, created_days_ago=0,
         status="active", origin_type="manual", xling_rate=None):
    created = (_now() - timedelta(days=created_days_ago)).isoformat().replace("+00:00", "Z")
    lifecycle = {"hit_count": hit_count, "audit_status": status}
    if xling_rate is not None:
        lifecycle["last_xling_pass_rate"] = xling_rate
    return {
        "id": pid, "topic": topic, "intent": intent,
        "lifecycle": lifecycle,
        "origin": {"type": origin_type, "date": created},
    }


def test_compute_audit_empty_library() -> None:
    audit = compute_audit([])
    assert audit["total_patterns"] == 0
    assert audit["deprecation_candidates"] == []
    assert audit["hit_count_summary"]["total_hits"] == 0


def test_deprecation_candidate_flagged_when_old_no_hits() -> None:
    patterns = [
        make("pat_a", "self_reference", "describe",
             hit_count=0, created_days_ago=90),
        make("pat_b", "self_reference", "describe2",
             hit_count=10, created_days_ago=90),
        make("pat_c", "self_reference", "describe3",
             hit_count=0, created_days_ago=10),
    ]
    audit = compute_audit(patterns, deprecation_age_days=60)
    cand_ids = {c["id"] for c in audit["deprecation_candidates"]}
    assert cand_ids == {"pat_a"}  # only pat_a satisfies all three conditions


def test_deprecation_candidate_skipped_when_already_deprecated() -> None:
    patterns = [
        make("pat_a", "self_reference", "describe",
             hit_count=0, created_days_ago=90, status="deprecated"),
    ]
    audit = compute_audit(patterns)
    assert audit["deprecation_candidates"] == []


def test_xling_floor_violations_flagged() -> None:
    patterns = [
        make("pat_low", "self_reference", "describe",
             xling_rate=0.3),
        make("pat_high", "self_reference", "describe2",
             xling_rate=0.9),
        make("pat_unmeasured", "self_reference", "describe3"),
    ]
    audit = compute_audit(patterns, xling_floor=0.5)
    violations = {v["id"] for v in audit["xling_floor_violations"]}
    assert violations == {"pat_low"}


def test_compute_audit_aggregates_by_topic_status_origin() -> None:
    patterns = [
        make("pat_a", "self_reference", "describe", hit_count=5,
             status="active", origin_type="manual"),
        make("pat_b", "self_reference", "describe2", hit_count=10,
             status="active", origin_type="autogen"),
        make("pat_c", "factual_inquiry", "ask", hit_count=2,
             status="deprecation_candidate", origin_type="manual"),
    ]
    audit = compute_audit(patterns)
    assert audit["by_topic"] == {"self_reference": 2, "factual_inquiry": 1}
    assert audit["by_audit_status"] == {
        "active": 2, "deprecation_candidate": 1,
    }
    assert audit["by_origin"] == {"manual": 2, "autogen": 1}


def test_hit_count_percentiles() -> None:
    patterns = [
        make(f"pat_{i:03d}", "t", "i", hit_count=v)
        for i, v in enumerate([0, 0, 0, 1, 5, 10, 20, 50, 100, 1000])
    ]
    audit = compute_audit(patterns)
    h = audit["hit_count_summary"]
    assert h["total_hits"] == 1186
    assert h["patterns_with_hits"] == 7
    assert h["max"] == 1000


def test_percentile_helper_handles_edges() -> None:
    assert _percentile([], 0.5) == 0.0
    assert _percentile([42.0], 0.5) == 42.0
    assert _percentile([1.0, 2.0, 3.0, 4.0], 0.5) == pytest.approx(2.5)


def test_render_markdown_includes_key_sections() -> None:
    patterns = [
        make("pat_old", "self_reference", "describe",
             hit_count=0, created_days_ago=90),
    ]
    audit = compute_audit(patterns, deprecation_age_days=60)
    md = render_markdown(audit)
    assert "# Pattern Library Audit Report" in md
    assert "## Composition" in md
    assert "## Hit-count summary" in md
    assert "## Deprecation candidates" in md
    assert "pat_old" in md  # candidate listed


def test_render_markdown_no_candidates_shows_none() -> None:
    audit = compute_audit([
        make("pat_busy", "t", "i", hit_count=10, created_days_ago=10),
    ])
    md = render_markdown(audit)
    assert "## Deprecation candidates (0)" in md
    assert "_None._" in md


def test_audit_writes_json_and_md_files(tmp_path: Path) -> None:
    """End-to-end: invoke the CLI as a subprocess (or via main()
    with mocked argv) and confirm both files are created."""
    cfg = tmp_path / "cfg"
    out = tmp_path / "out"
    cfg.mkdir()
    (cfg / "self_reference.jsonl").write_text(
        json.dumps(make("pat_a", "self_reference", "describe",
                         hit_count=5)) + "\n",
        encoding="utf-8",
    )

    import scripts.audit_pattern_library as mod
    sys_argv_backup = sys.argv
    try:
        sys.argv = [
            "audit_pattern_library.py",
            "--config-dir", str(cfg),
            "--output-dir", str(out),
        ]
        rc = mod.main()
        assert rc == 0
    finally:
        sys.argv = sys_argv_backup
    json_files = list(out.glob("audit_*.json"))
    md_files = list(out.glob("audit_*.md"))
    assert len(json_files) == 1
    assert len(md_files) == 1
    audit = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert audit["total_patterns"] == 1
