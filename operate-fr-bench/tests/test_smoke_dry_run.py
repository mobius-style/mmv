"""End-to-end dry-run of the OPERATE-FR v0.1 harness with the dummy adapter.

Verifies:
    - run_eval produces a JSONL file with 100 rows (one per task).
    - score reads it and emits a component-vector summary.
    - report renders Markdown without composite score.
    - the resulting markdown report contains the required sections.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import run_eval, score, report  # noqa: E402


def _read_jsonl(p: Path) -> list[dict]:
    rows = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@pytest.fixture
def tmp_reports(tmp_path: Path) -> Path:
    d = tmp_path / "reports"
    d.mkdir()
    return d


def test_end_to_end_dummy(tmp_reports: Path) -> None:
    suite_path = ROOT / "configs" / "suite_smoke.yaml"
    out_jsonl = tmp_reports / "dummy_smoke.jsonl"
    summary_json = tmp_reports / "dummy_smoke_summary.json"
    report_md = tmp_reports / "smoke_dry_run_report.md"

    # ── 1. run ─────────────────────────────────────────────────────
    summary = run_eval.run(
        suite_path=suite_path,
        profile_name="dummy",
        out_path=out_jsonl,
    )
    assert out_jsonl.exists()
    rows = _read_jsonl(out_jsonl)
    assert len(rows) == 100
    assert summary["ran"] == 100
    # dummy never errors
    assert summary["errored"] == 0
    # every row should carry a classified_route in the taxonomy
    for r in rows:
        assert r["classified_route"] in (
            "answer", "ask", "verify", "date_bound_answer",
            "abstain", "re_anchor", "execute", "refuse",
        )

    # ── 2. score ───────────────────────────────────────────────────
    labels_path = ROOT / "data" / "labels" / "smoke100_route_labels.jsonl"
    tasks_path = ROOT / "data" / "smoke100.jsonl"
    score.main([
        "--results", str(out_jsonl),
        "--labels", str(labels_path),
        "--suite-data", str(tasks_path),
        "--out", str(summary_json),
    ])
    assert summary_json.exists()
    summary_data = json.loads(summary_json.read_text(encoding="utf-8"))
    assert "component_vector" in summary_data
    cv = summary_data["component_vector"]
    assert cv["totals"]["total_tasks"] == 100
    # no composite anywhere
    assert "composite" not in cv
    assert "composite_score" not in cv
    # by-family results must cover every family that has tasks
    by_fam = cv["route_correctness_by_family"]
    for fam in ("volatile_current", "stale_premise_trap", "stable_control",
                "date_boundary", "query_neutrality", "ambiguous_time_frame"):
        assert fam in by_fam, f"family {fam!r} missing from per-family vector"

    # ── 3. report ──────────────────────────────────────────────────
    report.main([
        "--summary", str(summary_json),
        "--out", str(report_md),
    ])
    assert report_md.exists()
    md = report_md.read_text(encoding="utf-8")
    assert "OPERATE-FR" in md
    assert "candidate operational benchmark" in md.lower()
    # composite-score language should be explicitly absent
    assert "no official composite" in md.lower() \
        or "no composite" in md.lower()
