"""Tests for src/governance/deletion_manager.py."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.governance.deletion_manager import (
    ANONYMOUS, DeletionManager, ProposalError,
)
from src.retrieval.pattern_schema import Pattern


def _seed_pattern_dict(pid: str = "pat_self_ref_identity_001") -> dict:
    return {
        "id": pid, "version": "1.0", "lang": "en",
        "topic": "self_reference", "intent": "describe_self",
        "concepts": [], "priority": 100,
        "examples": ["a", "b", "c", "d", "e"],
        "negative_examples": [], "context_required": None,
        "context_excluded": [],
        "route": {"primary_box": "box_0", "exclude_boxes": [],
                  "synthesis_mode": "identity_response"},
        "tags": [], "cross_lingual_test_queries": [
            {"lang": "ja", "query": "x", "expected_match": True},
            {"lang": "ja", "query": "y", "expected_match": False},
            {"lang": "zh", "query": "z", "expected_match": True},
            {"lang": "zh", "query": "w", "expected_match": False},
        ],
        "lifecycle": {
            "hit_count": 0, "last_hit_date": None,
            "last_xling_pass_rate": None, "audit_status": "active",
            "deletion_proposals": [],
            "history": [{
                "timestamp": "2026-04-25T20:00:00Z", "event": "created",
                "actor": "claude_code", "detail": "seed",
            }],
        },
        "origin": {"type": "manual", "evolution_log_entry": 21,
                   "date": "2026-04-25"},
        "deprecated": False,
    }


def _setup(tmp_path: Path) -> tuple[DeletionManager, Path]:
    cfg = tmp_path / "config" / "pattern_library"
    cfg.mkdir(parents=True)
    src = cfg / "self_reference.jsonl"
    with src.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_seed_pattern_dict()) + "\n")
    audit = tmp_path / "data" / "pattern_library" / "audit_log" / "proposals.jsonl"
    mgr = DeletionManager(config_dir=cfg, audit_path=audit)
    return mgr, src


# ─── Validation ──────────────────────────────────────────────────────

def test_proposal_short_reason_rejected(tmp_path: Path) -> None:
    mgr, _ = _setup(tmp_path)
    with pytest.raises(ProposalError):
        mgr.propose("pat_self_ref_identity_001", "alice", "no")


def test_proposal_long_reason_rejected(tmp_path: Path) -> None:
    mgr, _ = _setup(tmp_path)
    with pytest.raises(ProposalError):
        mgr.propose("pat_self_ref_identity_001", "alice", "x" * 1001)


def test_proposal_unknown_pattern_rejected(tmp_path: Path) -> None:
    mgr, _ = _setup(tmp_path)
    with pytest.raises(ProposalError):
        mgr.propose("pat_does_not_exist_001", "alice", "good reason here")


def test_proposer_too_long_rejected(tmp_path: Path) -> None:
    mgr, _ = _setup(tmp_path)
    with pytest.raises(ProposalError):
        mgr.propose(
            "pat_self_ref_identity_001",
            "x" * 100, "valid reason here please.",
        )


# ─── Happy path ──────────────────────────────────────────────────────

def test_proposal_persisted_and_lifecycle_updated(tmp_path: Path) -> None:
    mgr, src = _setup(tmp_path)
    when = datetime(2026, 4, 25, 22, 0, 0, tzinfo=timezone.utc)
    res = mgr.propose(
        "pat_self_ref_identity_001",
        "alice", "duplicate of pat_self_ref_identity_002",
        when=when,
    )
    assert res.proposal_id.startswith("del_20260425_220000_")
    assert res.pattern_id == "pat_self_ref_identity_001"
    assert res.saved_to == src

    # Re-read the source file and verify the lifecycle updates
    with src.open("r", encoding="utf-8") as fh:
        line = fh.readline().strip()
        raw = json.loads(line)
    p = Pattern.model_validate(raw)
    assert p.lifecycle.audit_status == "user_deletion_proposed"
    assert len(p.lifecycle.deletion_proposals) == 1
    prop = p.lifecycle.deletion_proposals[0]
    assert prop.proposal_id == res.proposal_id
    assert prop.proposer == "alice"
    assert prop.status == "pending"
    assert "duplicate" in prop.reason
    # lifecycle.history grew by one
    assert len(p.lifecycle.history) == 2
    assert p.lifecycle.history[-1].event == "deletion_proposed"
    assert p.lifecycle.history[-1].actor == "user_alice"


def test_anonymous_proposer_default(tmp_path: Path) -> None:
    mgr, _ = _setup(tmp_path)
    res = mgr.propose(
        "pat_self_ref_identity_001", "", "valid reason here please.",
    )
    # Reload and check actor is anonymous
    src = list((tmp_path / "config" / "pattern_library").glob("*.jsonl"))[0]
    raw = json.loads(src.read_text().splitlines()[0])
    p = Pattern.model_validate(raw)
    assert p.lifecycle.deletion_proposals[0].proposer == ANONYMOUS
    assert p.lifecycle.history[-1].actor == "anonymous"


def test_audit_log_appended(tmp_path: Path) -> None:
    mgr, _ = _setup(tmp_path)
    mgr.propose(
        "pat_self_ref_identity_001", "bob",
        "ambiguous overlap with another pattern",
    )
    audit_path = (
        tmp_path / "data" / "pattern_library" / "audit_log" / "proposals.jsonl"
    )
    assert audit_path.exists()
    raw = audit_path.read_text(encoding="utf-8").strip()
    rec = json.loads(raw)
    assert rec["pattern_id"] == "pat_self_ref_identity_001"
    assert rec["proposer"] == "bob"
    assert rec["proposal_id"].startswith("del_")


def test_atomic_no_tmp_residue(tmp_path: Path) -> None:
    mgr, _ = _setup(tmp_path)
    mgr.propose(
        "pat_self_ref_identity_001", "alice", "valid reason here please.",
    )
    leftovers = list(
        (tmp_path / "config" / "pattern_library").glob("*.tmp")
    )
    assert leftovers == []


def test_two_proposals_accumulate(tmp_path: Path) -> None:
    mgr, src = _setup(tmp_path)
    mgr.propose("pat_self_ref_identity_001", "alice", "first reason here.")
    mgr.propose("pat_self_ref_identity_001", "bob", "second reason here.")
    raw = json.loads(src.read_text().splitlines()[0])
    p = Pattern.model_validate(raw)
    assert len(p.lifecycle.deletion_proposals) == 2
    proposers = {dp.proposer for dp in p.lifecycle.deletion_proposals}
    assert proposers == {"alice", "bob"}
