"""Phase 3 Commit 36 Secretary skeleton tests.

HARD CONSTRAINT 7 verification: Secretary must NOT mutate the
library directory under any of its operations.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.secretary.secretary_core import (
    Proposal, ProposalStore, Secretary,
    secretary_will_not_mutate_library,
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
def store(tmp_path: Path) -> ProposalStore:
    return ProposalStore(proposals_path=tmp_path / "proposals" / "store.jsonl")


# ─── Proposal dataclass ─────────────────────────────────────────────


def test_proposal_make_assigns_id_and_timestamp() -> None:
    p = Proposal.make(
        kind="deprecate_pattern",
        rationale="zero hits over 60 days",
    )
    assert p.proposal_id.startswith("prop_")
    assert p.status == "pending"
    assert p.created_at  # populated
    assert p.kind == "deprecate_pattern"


def test_proposal_to_jsonl_round_trip() -> None:
    p = Proposal.make(
        kind="add_negative_examples",
        rationale="false positive on disambiguator queries",
        evidence={"trigger": "audit_finding"},
        target_pattern_id="pat_self_reference_001",
    )
    line = p.to_jsonl()
    obj = json.loads(line)
    assert obj["proposal_id"] == p.proposal_id
    assert obj["kind"] == "add_negative_examples"


# ─── ProposalStore ─────────────────────────────────────────────────


def test_store_append_and_list(store: ProposalStore) -> None:
    a = Proposal.make("deprecate_pattern", "r1")
    b = Proposal.make("expand_examples", "r2")
    store.append(a)
    store.append(b)
    listed = store.list_all()
    assert {p.proposal_id for p in listed} == {a.proposal_id, b.proposal_id}


def test_store_list_pending_filters(store: ProposalStore) -> None:
    a = Proposal.make("deprecate_pattern", "r1")
    b = Proposal.make("expand_examples", "r2")
    store.append(a)
    store.append(b)
    store.update_status(a.proposal_id, "approved")
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].proposal_id == b.proposal_id


def test_store_update_status_records_decision(store: ProposalStore) -> None:
    p = Proposal.make("rebalance_threshold", "low confidence drift")
    store.append(p)
    updated = store.update_status(
        p.proposal_id, "rejected",
        decided_by="human:taiko",
        decision_note="threshold tuning planned at next quarterly review",
    )
    assert updated is not None
    assert updated.status == "rejected"
    assert updated.decided_at  # populated
    assert updated.decision_note == ("threshold tuning planned at next "
                                       "quarterly review")
    # And the in-store version reflects the update
    assert store.list_all()[0].status == "rejected"


# ─── Secretary skeleton ────────────────────────────────────────────


def test_secretary_observe_audit_returns_empty_list_in_skeleton(
    lib_dir: Path, store: ProposalStore,
) -> None:
    """Skeleton stub returns [] until Commit 37 wires triggers."""
    sec = Secretary(proposal_store=store, library_path=lib_dir)
    result = sec.observe_audit({"deprecation_candidates": []})
    assert result == []


def test_secretary_observe_hit_counts_returns_empty_list_in_skeleton(
    lib_dir: Path, store: ProposalStore,
) -> None:
    sec = Secretary(proposal_store=store, library_path=lib_dir)
    result = sec.observe_hit_counts({"pat_a": 5})
    assert result == []


def test_secretary_emit_user_proposal_persists_to_store(
    lib_dir: Path, store: ProposalStore,
) -> None:
    sec = Secretary(proposal_store=store, library_path=lib_dir)
    p = sec.emit_user_proposal(
        kind="add_negative_examples",
        rationale="user reported wrong route on q='X'",
        target_pattern_id="pat_self_reference_001",
    )
    listed = store.list_all()
    assert len(listed) == 1
    assert listed[0].proposal_id == p.proposal_id
    assert listed[0].evidence["source"] == "user"


# ─── HARD CONSTRAINT 7: Secretary MUST NOT mutate library ──────────


def test_secretary_observe_audit_does_not_mutate_library(
    lib_dir: Path, store: ProposalStore,
) -> None:
    sec = Secretary(proposal_store=store, library_path=lib_dir)
    before = secretary_will_not_mutate_library(lib_dir)
    sec.observe_audit({"deprecation_candidates": [{"id": "pat_x"}]})
    after = secretary_will_not_mutate_library(lib_dir)
    assert before == after


def test_secretary_emit_user_proposal_does_not_mutate_library(
    lib_dir: Path, store: ProposalStore,
) -> None:
    sec = Secretary(proposal_store=store, library_path=lib_dir)
    before = secretary_will_not_mutate_library(lib_dir)
    sec.emit_user_proposal(
        kind="add_negative_examples",
        rationale="...",
        target_pattern_id="pat_self_reference_001",
    )
    after = secretary_will_not_mutate_library(lib_dir)
    assert before == after


def test_proposal_store_writes_outside_library_dir(
    lib_dir: Path, tmp_path: Path,
) -> None:
    """The proposals JSONL lives outside config/pattern_library/.
    This is a structural invariant: never co-locate proposals with
    library config."""
    store = ProposalStore(
        proposals_path=tmp_path / "proposals" / "store.jsonl",
    )
    p = Proposal.make("deprecate_pattern", "r")
    store.append(p)
    # Ensure no file under lib_dir was created
    lib_files_after = sorted(lib_dir.glob("**/*"))
    # Only the originally-seeded JSONL should be present
    assert all(f.name == "self_reference.jsonl"
               for f in lib_files_after if f.is_file())
    # And the proposals path is in a separate dir
    assert tmp_path / "proposals" in store.proposals_path.parents
