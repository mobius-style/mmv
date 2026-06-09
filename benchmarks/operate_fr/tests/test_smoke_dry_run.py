"""End-to-end dummy dry-run test.

Uses the dummy profile to run a few tasks through the full pipeline:
run_eval → score → report. Verifies that:
  - JSONL results are produced and pass schema validation
  - score summary is generated
  - markdown report is rendered

No network is performed by the dummy adapter.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.operate_fr.harness import report as rpt_mod
from benchmarks.operate_fr.harness import run_eval, score as score_mod
from benchmarks.operate_fr.harness.schemas import validate_result


def test_dummy_dry_run_end_to_end(tmp_path: Path) -> None:
    suite_path = REPO_ROOT / "benchmarks/operate_fr/configs/suite_smoke.yaml"
    out_jsonl = tmp_path / "dummy.jsonl"
    info = run_eval.run_suite(suite_path, "dummy", out_jsonl, max_tasks=5)
    assert info["n_tasks"] == 5
    rows = [json.loads(l) for l in out_jsonl.read_text().splitlines() if l.strip()]
    assert len(rows) == 5
    for r in rows:
        validate_result(r)
        assert r["predicted_route"] is not None

    # score
    labels_path = REPO_ROOT / "benchmarks/operate_fr/data/labels/smoke100_route_labels.jsonl"
    data_path = REPO_ROOT / "benchmarks/operate_fr/data/smoke100.jsonl"
    labels = [json.loads(l) for l in labels_path.read_text().splitlines() if l.strip()]
    tasks = [json.loads(l) for l in data_path.read_text().splitlines() if l.strip()]
    summary = score_mod.score_results(
        rows,
        labels_by_task={r["task_id"]: r for r in labels},
        tasks_by_id={r["id"]: r for r in tasks},
    )
    assert summary["n_scored"] == 5
    assert "overall_route_correctness" in summary
    assert "composite_score" not in summary

    # report
    out_md = tmp_path / "report.md"
    text = rpt_mod.render_report(summary, profile_name="dummy",
                                 section_label="neutral_baseline")
    rpt_mod.write_report_to(out_md, text)
    assert out_md.exists()
    body = out_md.read_text()
    assert "OPERATE-FR v0.1" in body
    assert "component-vector" in body
    assert "neutral_baseline" in body
