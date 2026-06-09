"""Phase 3 Commit 37 Secretary trigger condition tests.

5 triggers verified:
1. observe_audit  → deprecation_candidate → deprecate_pattern proposal
2. observe_audit  → xling_floor_violation → expand_examples proposal
3. observe_hit_counts → hot saturation → lower_priority proposal
4. observe_hit_counts → cold accumulation → deprecate_pattern (review)
5. observe_threshold_drift → topic below gate → rebalance_threshold

Plus HARD CONSTRAINT 7 reverification: triggers do not mutate the
library directory.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.secretary.secretary_core import (
    ProposalStore, Secretary, secretary_will_not_mutate_library,
)


@pytest.fixture
def lib_dir(tmp_path: Path) -> Path:
    cfg = tmp_path / "library"
    cfg.mkdir()
    (cfg / "self_reference.jsonl").write_text(
        json.dumps({"id": "pat_self_reference_001"}) + "\n",
        encoding="utf-8",
    )
    return cfg


@pytest.fixture
def secretary(tmp_path: Path, lib_dir: Path) -> Secretary:
    store = ProposalStore(
        proposals_path=tmp_path / "proposals" / "store.jsonl",
    )
    return Secretary(proposal_store=store, library_path=lib_dir)


# ─── Trigger 1: deprecation candidate ──────────────────────────────


def test_audit_deprecation_candidate_emits_deprecate_pattern(
    secretary: Secretary,
) -> None:
    audit = {
        "deprecation_candidates": [
            {"id": "pat_x_001", "topic": "self_reference",
             "intent": "describe", "age_days": 90,
             "reason": "no_hits_after_60_days"},
        ],
        "xling_floor_violations": [],
    }
    out = secretary.observe_audit(audit)
    assert len(out) == 1
    assert out[0].kind == "deprecate_pattern"
    assert out[0].target_pattern_id == "pat_x_001"
    assert "no_hits" in out[0].rationale
    assert out[0].evidence["trigger"] == "audit.deprecation_candidate"
    # Persisted
    assert len(secretary.proposal_store.list_all()) == 1


# ─── Trigger 2: xling floor violation ──────────────────────────────


def test_audit_xling_violation_emits_expand_examples(
    secretary: Secretary,
) -> None:
    audit = {
        "deprecation_candidates": [],
        "xling_floor_violations": [
            {"id": "pat_x_002", "topic": "factual_inquiry",
             "xling_pass_rate": 0.30},
        ],
    }
    out = secretary.observe_audit(audit)
    assert len(out) == 1
    assert out[0].kind == "expand_examples"
    assert out[0].target_pattern_id == "pat_x_002"
    assert out[0].suggested_change.get("add_examples_lang") == ["ja", "zh"]


# ─── Trigger 3: hit-count saturation ───────────────────────────────


def test_hit_counts_hot_saturation_emits_lower_priority(
    secretary: Secretary,
) -> None:
    snapshot = {
        "pat_quiet": 5,
        "pat_warm": 50,
        "pat_hot": 250,
    }
    out = secretary.observe_hit_counts(snapshot, anomaly_floor=100)
    kinds = [p.kind for p in out]
    targets = [p.target_pattern_id for p in out]
    assert "lower_priority" in kinds
    assert "pat_hot" in targets
    # pat_warm (50) below threshold, should NOT trigger
    assert "pat_warm" not in [t for t, k in zip(targets, kinds)
                               if k == "lower_priority"]


# ─── Trigger 4: cold accumulation ──────────────────────────────────


def test_hit_counts_cold_accumulation_emits_deprecate_proposal(
    secretary: Secretary,
) -> None:
    """5+ patterns at hit_count==0 surfaces a review proposal."""
    snapshot = {f"pat_cold_{i:03d}": 0 for i in range(5)}
    out = secretary.observe_hit_counts(snapshot)
    cold_props = [p for p in out
                   if p.evidence.get("trigger") == "hit_count.cold_accumulation"]
    assert len(cold_props) == 1
    assert cold_props[0].kind == "deprecate_pattern"
    assert cold_props[0].evidence["cold_pattern_count"] == 5


def test_hit_counts_below_cold_threshold_no_proposal(
    secretary: Secretary,
) -> None:
    """Less than 5 cold patterns → no cold-accumulation proposal."""
    snapshot = {"pat_cold_a": 0, "pat_cold_b": 0}
    out = secretary.observe_hit_counts(snapshot)
    cold_props = [p for p in out
                   if p.evidence.get("trigger") == "hit_count.cold_accumulation"]
    assert cold_props == []


# ─── Trigger 5: threshold drift ────────────────────────────────────


def test_threshold_drift_below_gate_emits_rebalance(
    secretary: Secretary,
) -> None:
    accuracy = {
        "self_reference": 0.94,
        "factual_inquiry": 0.82,  # below 0.85 gate
        "conceptual_explain": 0.81,  # below
        "correction": 0.93,
    }
    out = secretary.observe_threshold_drift(accuracy, target_min=0.85)
    topics = sorted(p.target_topic for p in out)
    assert topics == ["conceptual_explain", "factual_inquiry"]
    for p in out:
        assert p.kind == "rebalance_threshold"
        assert p.suggested_change.get("rerun_sweep") is True


def test_threshold_drift_all_above_gate_no_proposal(
    secretary: Secretary,
) -> None:
    accuracy = {"self_reference": 0.94, "correction": 0.93}
    out = secretary.observe_threshold_drift(accuracy, target_min=0.85)
    assert out == []


# ─── Cap on proposals ──────────────────────────────────────────────


def test_observe_audit_caps_proposal_count(
    secretary: Secretary,
) -> None:
    """max_proposals limit prevents flood from large audits."""
    audit = {
        "deprecation_candidates": [
            {"id": f"pat_{i:03d}"} for i in range(50)
        ],
        "xling_floor_violations": [],
    }
    out = secretary.observe_audit(audit, max_proposals=5)
    assert len(out) == 5


# ─── HARD CONSTRAINT 7 reverification ─────────────────────────────


def test_triggers_do_not_mutate_library_dir(
    secretary: Secretary, lib_dir: Path,
) -> None:
    before = secretary_will_not_mutate_library(lib_dir)
    secretary.observe_audit({
        "deprecation_candidates": [{"id": "pat_x"}],
        "xling_floor_violations": [
            {"id": "pat_y", "xling_pass_rate": 0.3},
        ],
    })
    secretary.observe_hit_counts({
        f"pat_{i:03d}": (200 if i == 0 else 0) for i in range(10)
    })
    secretary.observe_threshold_drift({"self_reference": 0.5})
    after = secretary_will_not_mutate_library(lib_dir)
    assert before == after
