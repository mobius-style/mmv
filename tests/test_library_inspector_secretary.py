"""Phase 3 Commit 38 Library Inspector Secretary route tests."""
from __future__ import annotations

import hashlib
import json
import os
from base64 import b64encode
from pathlib import Path

import pytest


SECRET_PASSWORD = "phase3-test-secret"
SECRET_HASH = hashlib.sha256(SECRET_PASSWORD.encode("utf-8")).hexdigest()


@pytest.fixture
def app(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config" / "pattern_library"
    cfg.mkdir(parents=True)
    proposals = tmp_path / "secretary" / "proposals.jsonl"
    proposals.parent.mkdir(parents=True)
    monkeypatch.setattr(
        "src.ui.library_inspector.routes.author.CONFIG_DIR", cfg,
    )
    monkeypatch.setattr(
        "src.ui.library_inspector.lib.library_reader.DEFAULT_CONFIG_DIR",
        cfg,
    )
    monkeypatch.setenv("MOBIUS_LIB_AUTHOR_PASSWORD_HASH", SECRET_HASH)
    from src.ui.library_inspector.app import create_app
    a = create_app(config_dir=cfg)
    a.config["TESTING"] = True
    a.config["SECRETARY_PROPOSALS_PATH"] = str(proposals)
    a.config["_proposals_path"] = proposals
    return a


@pytest.fixture
def client(app):
    return app.test_client()


def _auth_headers(user="taiko", pwd=SECRET_PASSWORD):
    creds = b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


def _seed_proposal(path: Path, **kwargs):
    from src.secretary.secretary_core import Proposal, ProposalStore
    p = Proposal.make(
        kind=kwargs.get("kind", "deprecate_pattern"),
        rationale=kwargs.get("rationale", "test rationale"),
        target_pattern_id=kwargs.get("target_pattern_id"),
        target_topic=kwargs.get("target_topic"),
        evidence=kwargs.get("evidence", {"trigger": "test"}),
        suggested_change=kwargs.get("suggested_change", {}),
    )
    ProposalStore(proposals_path=path).append(p)
    return p


# ─── Auth gating ───────────────────────────────────────────────────


def test_secretary_disabled_without_env_var(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr(
        "src.ui.library_inspector.routes.author.CONFIG_DIR", cfg,
    )
    monkeypatch.setattr(
        "src.ui.library_inspector.lib.library_reader.DEFAULT_CONFIG_DIR",
        cfg,
    )
    monkeypatch.delenv("MOBIUS_LIB_AUTHOR_PASSWORD_HASH", raising=False)
    from src.ui.library_inspector.app import create_app
    a = create_app(config_dir=cfg)
    a.config["TESTING"] = True
    resp = a.test_client().get("/secretary")
    assert resp.status_code == 403


def test_secretary_requires_basic_auth(client) -> None:
    resp = client.get("/secretary")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers


def test_secretary_wrong_password_rejected(client) -> None:
    resp = client.get("/secretary", headers=_auth_headers(pwd="wrong"))
    assert resp.status_code == 401


def test_secretary_correct_password_accepted(client, app) -> None:
    resp = client.get("/secretary", headers=_auth_headers())
    assert resp.status_code == 200


# ─── List rendering ────────────────────────────────────────────────


def test_secretary_lists_pending_proposals(client, app) -> None:
    p = _seed_proposal(app.config["_proposals_path"],
                        target_pattern_id="pat_x_001",
                        rationale="test rationale unique-marker-91")
    resp = client.get("/secretary", headers=_auth_headers())
    body = resp.get_data(as_text=True)
    assert p.proposal_id in body
    assert "pat_x_001" in body
    assert "unique-marker-91" in body


def test_secretary_shows_zero_pending_when_empty(client) -> None:
    resp = client.get("/secretary", headers=_auth_headers())
    body = resp.get_data(as_text=True)
    assert "No pending proposals." in body


# ─── Decide endpoint ───────────────────────────────────────────────


def test_decide_approve_updates_status(client, app) -> None:
    proposals_path = app.config["_proposals_path"]
    p = _seed_proposal(proposals_path)
    resp = client.post(
        f"/secretary/{p.proposal_id}/decide",
        data={"decision": "approved", "note": "looks good"},
        headers=_auth_headers(),
    )
    assert resp.status_code in (302, 303)  # redirect after action
    # Verify status changed
    from src.secretary.secretary_core import ProposalStore
    store = ProposalStore(proposals_path=proposals_path)
    listed = store.list_all()
    assert listed[0].status == "approved"
    assert listed[0].decision_note == "looks good"


def test_decide_reject_updates_status(client, app) -> None:
    proposals_path = app.config["_proposals_path"]
    p = _seed_proposal(proposals_path)
    resp = client.post(
        f"/secretary/{p.proposal_id}/decide",
        data={"decision": "rejected"},
        headers=_auth_headers(),
    )
    assert resp.status_code in (302, 303)
    from src.secretary.secretary_core import ProposalStore
    listed = ProposalStore(proposals_path=proposals_path).list_all()
    assert listed[0].status == "rejected"


def test_decide_invalid_decision_returns_400(client, app) -> None:
    proposals_path = app.config["_proposals_path"]
    p = _seed_proposal(proposals_path)
    resp = client.post(
        f"/secretary/{p.proposal_id}/decide",
        data={"decision": "foo"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


def test_decide_unknown_proposal_returns_404(client, app) -> None:
    resp = client.post(
        "/secretary/prop_does_not_exist/decide",
        data={"decision": "approved"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


# ─── HARD CONSTRAINT 7: decision does not mutate library ──────────


def test_approve_does_not_modify_library_dir(client, app, tmp_path: Path) -> None:
    """Even on 'approved' decision, config/pattern_library/* unchanged."""
    proposals_path = app.config["_proposals_path"]
    cfg = tmp_path / "config" / "pattern_library"
    # Seed a library file with a known fingerprint
    seed = {"id": "pat_self_reference_001"}
    seed_path = cfg / "self_reference.jsonl"
    seed_path.write_text(json.dumps(seed) + "\n", encoding="utf-8")
    before = seed_path.read_bytes()
    p = _seed_proposal(proposals_path, target_pattern_id="pat_self_reference_001")
    client.post(
        f"/secretary/{p.proposal_id}/decide",
        data={"decision": "approved"},
        headers=_auth_headers(),
    )
    after = seed_path.read_bytes()
    assert before == after
