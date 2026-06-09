"""Tests for scripts/classify_metric5_failures.py — Phase 3 Stab Commit 42."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import classify_metric5_failures as classify_mod


def test_parse_failures_extracts_block() -> None:
    raw = """
===== Scenario results: 30/33 passed =====
By category:
  factual_general               : 3/3
  identity_stability            : 3/3

--- FAIL: self_reference_integrity_ja (ja/self_reference) ---
  turn 0: response_must_not_semantically_contain
    expected: <= 2
    actual:   5

--- FAIL: factual_krillin_ja (ja/factual_krillin) ---
  turn -1: stochastic_gate
    expected: 3/5 runs PASS
    actual:   0/5
"""
    fails = classify_mod.parse_failures(raw)
    assert len(fails) == 2
    assert fails[0]["scenario_id"] == "self_reference_integrity_ja"
    assert fails[0]["category"] == "self_reference"
    assert fails[1]["scenario_id"] == "factual_krillin_ja"


def test_classify_response_length_max_is_category_b() -> None:
    detail = "turn 0: response_length_max\n  expected: 1500\n  actual: 1540"
    assert classify_mod.classify(detail) == "B"


def test_classify_response_must_not_semantically_contain_is_category_b() -> None:
    detail = "turn 0: response_must_not_semantically_contain\n  expected: <= 2\n  actual: 5"
    assert classify_mod.classify(detail) == "B"


def test_classify_stochastic_gate_is_category_b() -> None:
    detail = "turn -1: stochastic_gate\n  expected: 3/5 runs PASS\n  actual: 0/5"
    assert classify_mod.classify(detail) == "B"


def test_classify_unknown_returns_unknown() -> None:
    detail = "some weird unrelated message"
    assert classify_mod.classify(detail) == "Unknown"


def test_classify_pattern_library_signature_is_category_a() -> None:
    detail = "turn 0: wrong_box_selected — library_route_mismatch"
    assert classify_mod.classify(detail) == "A"


def test_classify_oom_is_category_c() -> None:
    detail = "RuntimeError: CUDA out of memory"
    assert classify_mod.classify(detail) == "C"


def test_main_writes_json_and_markdown(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: synthesize a fake aggregate JSON and run main()."""
    raw_run_output = (
        "===== Scenario results: 30/33 passed =====\n"
        "By category:\n  factual_general : 3/3\n"
        "\n--- FAIL: self_reference_integrity_ja (ja/self_reference) ---\n"
        "  turn 0: response_must_not_semantically_contain\n"
        "    expected: <= 2\n  actual:   5\n"
    )
    payload = {
        "n_runs": 1, "baseline": 31,
        "runs": [{
            "total_passed": 30,
            "identity_leakage": 0,
            "raw_output": raw_run_output,
        }],
    }
    in_path = tmp_path / "agg.json"
    in_path.write_text(json.dumps(payload), encoding="utf-8")
    out_md = tmp_path / "report.md"

    monkeypatch.setattr(sys, "argv", [
        "classify_metric5_failures.py",
        "--input", str(in_path),
        "--report", str(out_md),
    ])
    rc = classify_mod.main()
    assert rc == 0
    assert out_md.exists()
    body = out_md.read_text(encoding="utf-8")
    assert "Metric 5 Failure Root Cause Analysis" in body
    assert "self_reference_integrity_ja" in body
    assert "Category" in body
