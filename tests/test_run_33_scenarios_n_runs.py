"""Phase 3 Stabilization Commit 41 — N-runs aggregation tests for
scripts/run_33_scenarios.py.

The harness aggregator is exercised via _aggregate_runs() unit tests.
Full subprocess integration is exercised in the Phase 3 stab Commit
42 N=5 measurement run; here we only pin the aggregation contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_33_scenarios as harness


def test_aggregate_single_run_produces_zero_stdev() -> None:
    runs = [{"total_passed": 31, "identity_leakage": 0}]
    summary = harness._aggregate_runs(runs)
    assert summary["n_runs"] == 1
    assert summary["mean"] == 31
    assert summary["stdev"] == 0.0
    assert summary["min"] == summary["max"] == 31
    assert summary["max_leakage"] == 0


def test_aggregate_three_runs_computes_mean_and_stdev() -> None:
    runs = [
        {"total_passed": 30, "identity_leakage": 0},
        {"total_passed": 31, "identity_leakage": 0},
        {"total_passed": 30, "identity_leakage": 0},
    ]
    summary = harness._aggregate_runs(runs)
    assert summary["n_runs"] == 3
    assert summary["n_parsed"] == 3
    assert summary["mean"] == pytest.approx(30 + 1/3, abs=0.01)
    assert summary["min"] == 30
    assert summary["max"] == 31
    assert summary["stdev"] > 0


def test_aggregate_handles_missing_total_passed() -> None:
    """A run that failed to parse total_passed should not break aggregation;
    only successfully-parsed values feed mean/stdev."""
    runs = [
        {"total_passed": 31, "identity_leakage": 0},
        {"total_passed": None, "identity_leakage": 0, "error": "timeout"},
        {"total_passed": 30, "identity_leakage": 0},
    ]
    summary = harness._aggregate_runs(runs)
    assert summary["n_runs"] == 3
    assert summary["n_parsed"] == 2
    assert summary["mean"] == 30.5


def test_aggregate_picks_max_leakage() -> None:
    runs = [
        {"total_passed": 31, "identity_leakage": 0},
        {"total_passed": 30, "identity_leakage": 2},
        {"total_passed": 31, "identity_leakage": 1},
    ]
    summary = harness._aggregate_runs(runs)
    assert summary["max_leakage"] == 2
    assert summary["leakage_per_run"] == [0, 2, 1]


def test_aggregate_empty_runs() -> None:
    summary = harness._aggregate_runs([])
    assert summary["n_runs"] == 0
    assert summary["n_parsed"] == 0
    assert "mean" not in summary
    assert summary["max_leakage"] == 0
