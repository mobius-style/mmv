"""Phase 2 Commit 21 — Library Inspector authoring form tests."""
from __future__ import annotations

import hashlib
import json
import os
from base64 import b64encode
from pathlib import Path

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Sandbox config dir + LibraryReader
    cfg = tmp_path / "config" / "pattern_library"
    cfg.mkdir(parents=True)
    monkeypatch.setattr(
        "src.ui.library_inspector.routes.author.CONFIG_DIR", cfg,
    )
    monkeypatch.setattr(
        "src.ui.library_inspector.lib.library_reader.DEFAULT_CONFIG_DIR",
        cfg,
    )
    from src.ui.library_inspector.app import create_app
    app = create_app(config_dir=cfg)
    app.config.update(TESTING=True)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _basic_auth(user="t", password="secret"):
    creds = b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


# ─── Auth gating ──────────────────────────────────────────────────────

def test_get_form_returns_403_when_env_unset(client, monkeypatch):
    monkeypatch.delenv("MOBIUS_LIB_AUTHOR_PASSWORD_HASH", raising=False)
    r = client.get("/pattern/new")
    assert r.status_code == 403


def test_get_form_returns_401_without_auth(client, monkeypatch):
    h = hashlib.sha256(b"secret").hexdigest()
    monkeypatch.setenv("MOBIUS_LIB_AUTHOR_PASSWORD_HASH", h)
    r = client.get("/pattern/new")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_get_form_succeeds_with_auth(client, monkeypatch):
    h = hashlib.sha256(b"secret").hexdigest()
    monkeypatch.setenv("MOBIUS_LIB_AUTHOR_PASSWORD_HASH", h)
    r = client.get("/pattern/new", headers=_basic_auth(password="secret"))
    assert r.status_code == 200
    txt = r.get_data(as_text=True)
    assert "Author New Pattern" in txt
    assert "Examples" in txt


def test_get_form_401_with_wrong_password(client, monkeypatch):
    h = hashlib.sha256(b"correct").hexdigest()
    monkeypatch.setenv("MOBIUS_LIB_AUTHOR_PASSWORD_HASH", h)
    r = client.get("/pattern/new", headers=_basic_auth(password="wrong"))
    assert r.status_code == 401


# ─── POST validation ─────────────────────────────────────────────────

def _valid_form_data() -> dict:
    return {
        "id": "pat_factual_inquiry_999",
        "topic": "factual_inquiry",
        "intent": "ask_test_thing",
        "examples": "What is foo\nDefine bar\nExplain baz\n"
                     "Tell me about quux\nWhat does X mean",
        "negative_examples": "What is the wife of Krillin",
        "primary_box": "box_w",
        "synthesis_mode": "factual_synthesis",
    }


def test_post_invalid_id_returns_422(client, monkeypatch):
    h = hashlib.sha256(b"s").hexdigest()
    monkeypatch.setenv("MOBIUS_LIB_AUTHOR_PASSWORD_HASH", h)
    data = _valid_form_data()
    data["id"] = "bad_id"
    r = client.post("/pattern/new", data=data, headers=_basic_auth(password="s"))
    assert r.status_code == 422
    assert b"id must match" in r.data


def test_post_too_few_examples_returns_422(client, monkeypatch):
    h = hashlib.sha256(b"s").hexdigest()
    monkeypatch.setenv("MOBIUS_LIB_AUTHOR_PASSWORD_HASH", h)
    data = _valid_form_data()
    data["examples"] = "only one\nand two\nand three"  # only 3 lines
    r = client.post("/pattern/new", data=data, headers=_basic_auth(password="s"))
    assert r.status_code == 422
    assert b"at least 5 examples" in r.data


def test_post_xling_too_few_returns_422(client, monkeypatch):
    """Less than 4 cross-lingual queries → Pydantic min_length fail."""
    h = hashlib.sha256(b"s").hexdigest()
    monkeypatch.setenv("MOBIUS_LIB_AUTHOR_PASSWORD_HASH", h)
    data = _valid_form_data()
    from werkzeug.datastructures import MultiDict
    md = MultiDict(data)
    md.add("xl_lang", "ja"); md.add("xl_query", "ja query")
    md.add("xl_match", "true"); md.add("xl_min_cos", "0.65")
    r = client.post("/pattern/new", data=md, headers=_basic_auth(password="s"))
    assert r.status_code == 422


def test_post_happy_path_appends_to_jsonl(client, monkeypatch, tmp_path):
    h = hashlib.sha256(b"s").hexdigest()
    monkeypatch.setenv("MOBIUS_LIB_AUTHOR_PASSWORD_HASH", h)
    from werkzeug.datastructures import MultiDict
    md = MultiDict(_valid_form_data())
    pairs = [
        ("ja", "fooの定義", "true", "0.65"),
        ("ja", "barの定義", "true", "0.65"),
        ("zh", "foo是什么", "true", "0.65"),
        ("zh", "bar是什么", "false", ""),
    ]
    for lang, q, m, mc in pairs:
        md.add("xl_lang", lang); md.add("xl_query", q)
        md.add("xl_match", m); md.add("xl_min_cos", mc)
    from src.ui.library_inspector.routes.author import CONFIG_DIR
    target = CONFIG_DIR / "factual_inquiry.jsonl"
    assert not target.exists() or target.stat().st_size == 0
    r = client.post("/pattern/new", data=md,
                    headers=_basic_auth(password="s"))
    assert r.status_code == 302  # redirect to detail page
    assert "/pattern/pat_factual_inquiry_999" in r.headers.get(
        "Location", ""
    )
    assert target.exists()
    raw = target.read_text(encoding="utf-8").strip()
    obj = json.loads(raw.splitlines()[-1])
    assert obj["id"] == "pat_factual_inquiry_999"
    assert obj["topic"] == "factual_inquiry"
    assert len(obj["examples"]) >= 5
    assert obj["origin"]["type"] == "manual"
    assert any(q["lang"] == "ja" for q in obj["cross_lingual_test_queries"])
    assert any(q["lang"] == "zh" for q in obj["cross_lingual_test_queries"])


def test_post_duplicate_id_rejected(client, monkeypatch, tmp_path):
    h = hashlib.sha256(b"s").hexdigest()
    monkeypatch.setenv("MOBIUS_LIB_AUTHOR_PASSWORD_HASH", h)
    # Pre-seed the target file with the same id
    from src.ui.library_inspector.routes.author import CONFIG_DIR
    seed_target = CONFIG_DIR / "factual_inquiry.jsonl"
    seed_target.write_text(json.dumps({
        "id": "pat_factual_inquiry_999", "topic": "factual_inquiry",
        "intent": "x", "examples": ["a", "b", "c", "d", "e"],
        "negative_examples": [], "version": "1.0", "lang": "en",
        "concepts": [], "priority": 100,
        "context_required": None, "context_excluded": [],
        "route": {"primary_box": "box_0", "exclude_boxes": [],
                  "synthesis_mode": "x"},
        "tags": [],
        "cross_lingual_test_queries": [
            {"lang": "ja", "query": "x", "expected_match": True},
            {"lang": "ja", "query": "y", "expected_match": False},
            {"lang": "zh", "query": "z", "expected_match": True},
            {"lang": "zh", "query": "w", "expected_match": False},
        ],
        "lifecycle": {"hit_count": 0, "last_hit_date": None,
                       "last_xling_pass_rate": None,
                       "audit_status": "active",
                       "deletion_proposals": [], "history": []},
        "origin": {"type": "manual", "date": "2026-04-26T00:00:00",
                    "evolution_log_entry": None,
                    "scenario_id": None, "batch_id": None,
                    "groq_run_id": None, "prompt_version": None},
        "deprecated": False,
    }) + "\n")

    from werkzeug.datastructures import MultiDict
    md = MultiDict(_valid_form_data())
    for lang, q, m, mc in [("ja", "1", "true", "0.65"),
                            ("ja", "2", "true", "0.65"),
                            ("zh", "3", "true", "0.65"),
                            ("zh", "4", "false", "")]:
        md.add("xl_lang", lang); md.add("xl_query", q)
        md.add("xl_match", m); md.add("xl_min_cos", mc)
    r = client.post("/pattern/new", data=md,
                    headers=_basic_auth(password="s"))
    assert r.status_code == 422
    assert b"already exists" in r.data
