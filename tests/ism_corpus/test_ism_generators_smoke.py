"""Phase 4 v2.1 Commit 7 — ISM corpus generator smoke tests.

These tests verify the generator scripts' assembly logic without
making Groq API calls. The actual generation runs happen during
ISM milestones (I-1 through I-3).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import scripts.ism_corpus.intent_variants_generator as ivg
import scripts.ism_corpus.abstain_gap_filler as agf


# ─── intent_variants_generator ────────────────────────────────────


def test_supported_target_intents_match_phase4_plan() -> None:
    """The 6 under-represented intents from Phase 4 v2.1 Commit 5
    investigation must be the supported targets."""
    expected = {
        "correction", "meta_question", "game_move",
        "clarification", "creative_request", "translation_request",
    }
    assert set(ivg.SUPPORTED_TARGETS) == expected


def test_assemble_chunk_preserves_seed_metadata() -> None:
    seed = {
        "id": "seed-001",
        "intent_type": "meta_question",
        "formal_type": "what",
        "response_type": "direct_answer",
        "wiki_lookup": False,
        "qk_entitlement": "answerable",
        "qk_tvs_estimate": "low",
        "qk_halfstep_type": "none",
        "language": "ja",
        "query": "あなたは何ができますか",
    }
    chunk = ivg.assemble_chunk(
        seed, variant_text="あなたの機能を教えてください",
        batch_id="bat_test", groq_run_id="run_test",
    )
    assert chunk["intent_type"] == "meta_question"
    assert chunk["language"] == "ja"
    assert chunk["query"] == "あなたの機能を教えてください"
    assert chunk["_origin"]["seed_chunk_id"] == "seed-001"
    assert chunk["_origin"]["prompt_version"] == "intent_variants_v1"
    assert chunk["id"] != "seed-001"  # new uuid


def test_assemble_chunk_inherits_qk_metadata() -> None:
    seed = {
        "id": "seed-002",
        "intent_type": "correction",
        "formal_type": "yesno",
        "qk_entitlement": "abstain",
        "qk_tvs_estimate": "high",
        "language": "zh",
        "query": "this is wrong",
    }
    chunk = ivg.assemble_chunk(
        seed, variant_text="this is incorrect",
        batch_id="bat", groq_run_id="run",
    )
    assert chunk["qk_entitlement"] == "abstain"
    assert chunk["qk_tvs_estimate"] == "high"
    assert chunk["formal_type"] == "yesno"


# ─── abstain_gap_filler ───────────────────────────────────────────


def test_detect_language_japanese() -> None:
    assert agf.detect_language("こんにちは、元気ですか") == "ja"
    assert agf.detect_language("カタカナのテスト") == "ja"


def test_detect_language_chinese() -> None:
    assert agf.detect_language("你好,最近怎么样") == "zh"
    assert agf.detect_language("人工智能的发展") == "zh"


def test_detect_language_english_default() -> None:
    assert agf.detect_language("Hello, how are you") == "en"
    assert agf.detect_language("This is a question") == "en"


def test_assemble_abstain_chunk_has_abstain_entitlement() -> None:
    chunk = agf.assemble_chunk(
        query="Will I marry my high school crush?",
        language="en",
        batch_id="bat_test",
        groq_run_id="run_test",
        source_label="synthetic",
    )
    assert chunk["qk_entitlement"] == "abstain"
    assert chunk["language"] == "en"
    assert chunk["wiki_lookup"] is False  # abstain → no wiki
    assert chunk["_origin"]["type"] == "ism_autogen"
    assert chunk["_origin"]["prompt_version"].startswith("abstain_gap_v1_")


def test_pattern_library_negatives_extraction(tmp_path, monkeypatch) -> None:
    """Smoke: extracting negative_examples from a pattern JSONL
    yields chunks with abstain entitlement."""
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    fake_pattern = {
        "id": "pat_self_reference_001", "version": "1.0",
        "lang": "en", "topic": "self_reference",
        "intent": "describe", "concepts": [], "priority": 100,
        "examples": ["a", "b", "c", "d", "e"],
        "negative_examples": [
            "Will the user be happy with this answer?",
            "未来予測してください",
            "你能预测股价吗",
        ],
        "context_required": None, "context_excluded": [],
        "route": {"primary_box": "box_0", "exclude_boxes": [],
                   "synthesis_mode": "default"},
        "tags": [],
        "cross_lingual_test_queries": [
            {"lang": "ja", "query": "x", "expected_match": True,
             "min_cosine": 0.62},
            {"lang": "ja", "query": "y", "expected_match": True,
             "min_cosine": 0.62},
            {"lang": "zh", "query": "z", "expected_match": True,
             "min_cosine": 0.62},
            {"lang": "zh", "query": "w", "expected_match": True,
             "min_cosine": 0.62},
        ],
        "lifecycle": {"hit_count": 0, "audit_status": "active"},
        "origin": {"type": "manual", "date": "2026-04-27T00:00:00Z"},
    }
    (cfg / "self_reference.jsonl").write_text(
        json.dumps(fake_pattern, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(agf, "PL_CONFIG", cfg)
    chunks = agf.source_pattern_library_negatives(
        max_chunks=100, batch_id="bat_test",
    )
    assert len(chunks) == 3
    langs = {c["language"] for c in chunks}
    assert "en" in langs
    assert "ja" in langs
    assert "zh" in langs
    for c in chunks:
        assert c["qk_entitlement"] == "abstain"


def test_pattern_library_negatives_respects_max_chunks(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    fake_pattern = {
        "id": "pat_self_reference_001", "version": "1.0",
        "lang": "en", "topic": "self_reference",
        "intent": "describe", "concepts": [], "priority": 100,
        "examples": ["a", "b", "c", "d", "e"],
        "negative_examples": [f"neg query {i}" for i in range(50)],
        "context_required": None, "context_excluded": [],
        "route": {"primary_box": "box_0", "exclude_boxes": [],
                   "synthesis_mode": "default"},
        "tags": [],
        "cross_lingual_test_queries": [
            {"lang": "ja", "query": "x", "expected_match": True,
             "min_cosine": 0.62},
            {"lang": "ja", "query": "y", "expected_match": True,
             "min_cosine": 0.62},
            {"lang": "zh", "query": "z", "expected_match": True,
             "min_cosine": 0.62},
            {"lang": "zh", "query": "w", "expected_match": True,
             "min_cosine": 0.62},
        ],
        "lifecycle": {"hit_count": 0, "audit_status": "active"},
        "origin": {"type": "manual", "date": "2026-04-27T00:00:00Z"},
    }
    (cfg / "self_reference.jsonl").write_text(
        json.dumps(fake_pattern, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(agf, "PL_CONFIG", cfg)
    chunks = agf.source_pattern_library_negatives(
        max_chunks=10, batch_id="bat_test",
    )
    assert len(chunks) == 10  # respects max
