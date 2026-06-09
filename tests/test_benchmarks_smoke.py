"""Smoke tests for the benchmark harness.

These verify that:
  - every runner module imports
  - configs (matrix, profiles, suites) parse
  - the dummy profile can be invoked end-to-end and produces valid JSONL
  - placeholder runners emit a single well-formed row
  - the orchestrator can walk the smoke suite using the dummy profile
  - the summarizer produces a Markdown report from result files

They do NOT make network calls. The real-API smoke runs against 9B/120B are
exercised by `scripts/run_bench_smoke.sh`, not by pytest.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def tmp_results_dir(tmp_path: Path) -> Path:
    d = tmp_path / "results"
    d.mkdir()
    return d


@pytest.fixture
def tmp_reports_dir(tmp_path: Path) -> Path:
    d = tmp_path / "reports"
    d.mkdir()
    return d


def test_runners_import() -> None:
    """All runner modules should import cleanly."""
    from benchmarks.runners import (  # noqa: F401
        run_agent_benchmarks,
        run_humaneval,
        run_inhouse_mc,
        run_lm_eval,
        run_mobius_governance,
        run_swebench,
    )


def test_configs_parse() -> None:
    from benchmarks.lib.config_loader import (
        load_benchmark_matrix,
        load_model_profiles,
        load_suite,
    )

    profiles = load_model_profiles()
    assert "local-ollama-9b" in profiles
    assert "groq-gpt-oss-120b" in profiles
    assert "dummy" in profiles

    matrix = load_benchmark_matrix()
    names = {b["name"] for b in matrix}
    for required in ("mobius_governance", "inhouse_mc_smoke", "mmlu", "humaneval"):
        assert required in names

    for suite in ("smoke", "standard", "full", "governance"):
        load_suite(suite)


def test_dummy_governance_runner(tmp_results_dir: Path) -> None:
    """End-to-end with dummy profile produces a valid JSONL file."""
    from benchmarks.runners import run_mobius_governance

    out_path = run_mobius_governance.run(
        "dummy", sample_size=3, output_dir=tmp_results_dir
    )
    assert out_path.exists()
    rows = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 3
    for r in rows:
        # required schema fields
        for k in (
            "run_id", "timestamp", "model_profile", "benchmark", "task",
            "sample_id", "prompt_hash", "output_hash", "score", "metric_name",
            "latency_ms", "tokens_in", "tokens_out", "error", "metadata",
        ):
            assert k in r
        assert r["model_profile"] == "dummy"
        assert r["benchmark"] == "mobius_governance"
        assert r["metric_name"] == "governance_score"
        # dummy backend should not error
        assert r["error"] is None


def test_dummy_inhouse_mc_runner(tmp_results_dir: Path) -> None:
    from benchmarks.runners import run_inhouse_mc

    out_path = run_inhouse_mc.run(
        "dummy", sample_size=4, output_dir=tmp_results_dir
    )
    rows = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 4
    for r in rows:
        assert r["metric_name"] == "accuracy"
        # dummy never knows the right letter — score will be 0.0
        assert r["score"] in (0.0, 1.0)
        assert r["error"] is None


def test_placeholder_runner_writes_one_row(tmp_results_dir: Path) -> None:
    from benchmarks.runners import run_humaneval

    out_path = run_humaneval.run(
        "dummy", benchmark_name="humaneval",
        sample_size=2, output_dir=tmp_results_dir,
    )
    rows = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    r = rows[0]
    assert r["score"] is None
    assert r["error"] and r["error"].startswith("PLACEHOLDER")
    assert "install_hint" in r["metadata"]


def test_orchestrator_smoke_with_dummy(
    tmp_results_dir: Path, tmp_reports_dir: Path
) -> None:
    """Run the smoke suite end-to-end with the dummy profile.

    All real model backends are skipped — the smoke suite is filtered down
    to the dummy profile via the --profiles override emulation.
    """
    from benchmarks import run_suite

    records, report_path = run_suite.run_suite(
        "smoke", profiles=["dummy"],
        output_dir=tmp_results_dir, reports_dir=tmp_reports_dir,
    )
    assert report_path.exists()
    # smoke.yaml lists 10 benchmark entries; 1 profile => 10 records
    assert len(records) >= 5
    statuses = {r["status"] for r in records}
    assert statuses & {"enabled", "placeholder"}


def test_summarizer_writes_report(
    tmp_results_dir: Path, tmp_reports_dir: Path
) -> None:
    from benchmarks.runners import run_mobius_governance
    from scripts import summarize_benchmarks

    run_mobius_governance.run("dummy", sample_size=2, output_dir=tmp_results_dir)

    md, csv_p = summarize_benchmarks.write_summary(
        results_dir=tmp_results_dir, reports_dir=tmp_reports_dir
    )
    assert md.exists() and md.stat().st_size > 0
    assert csv_p.exists()
    text = md.read_text(encoding="utf-8")
    assert "Benchmark summary" in text
    assert "Möbius governance summary" in text


def test_purity_guard_rejects_wrong_backend() -> None:
    from benchmarks.lib.purity_guard import (
        CallEvidence,
        PurityViolation,
        enforce_purity,
    )

    profile = {
        "purity_guard": {
            "require_backend": "groq",
            "require_model_substring": "gpt-oss-120b",
            "forbid_endpoint_substring": ["localhost"],
        }
    }
    # backend mismatch
    with pytest.raises(PurityViolation):
        enforce_purity(profile, CallEvidence(
            backend="ollama", endpoint="https://api.groq.com",
            reported_model="openai/gpt-oss-120b",
        ))
    # endpoint contains forbidden substring
    with pytest.raises(PurityViolation):
        enforce_purity(profile, CallEvidence(
            backend="groq", endpoint="http://localhost:11434",
            reported_model="openai/gpt-oss-120b",
        ))
    # model echo mismatch
    with pytest.raises(PurityViolation):
        enforce_purity(profile, CallEvidence(
            backend="groq", endpoint="https://api.groq.com",
            reported_model="qwen3.5:9b",
        ))
    # happy path — no exception
    enforce_purity(profile, CallEvidence(
        backend="groq", endpoint="https://api.groq.com",
        reported_model="openai/gpt-oss-120b",
    ))
