"""Embedding Rule — constitutional-level contract tests.

Per docs/EMBEDDING_RULE.md (promulgated 2026-04-23, Evolution Log
cyc_20260423_production_quality_deep_fix): every Box index generated or
consumed by MOBIUS MMV MUST use `intfloat/multilingual-e5-large` (ME5) as
the sentence encoder. Box A's former MiniLM transitional exception was
retired on 2026-05-21.

These tests are structural:
  - CustomRagAdapter must expose the model_name / query_prefix /
    passage_prefix kwargs so a Box can opt into ME5 without duplicating
    the adapter class.
  - CustomRagAdapter's default (no kwargs) must be ME5 so Box A and Box 0
    share the same vector space.
  - The rule document and Box 0 migration test file must both exist.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from src.adapters.custom_rag_adapter import CustomRagAdapter, MODEL_NAME

ROOT = Path(__file__).resolve().parents[1]
RULE = ROOT / "docs" / "EMBEDDING_RULE.md"
RL_STATUS = ROOT / "docs" / "RL_MODULE_STATUS.md"


def test_custom_rag_adapter_exposes_embedding_rule_kwargs():
    sig = inspect.signature(CustomRagAdapter.__init__)
    params = sig.parameters
    for kw in ("model_name", "query_prefix", "passage_prefix"):
        assert kw in params, (
            f"CustomRagAdapter.__init__ must expose {kw!r} to let a Box "
            f"opt into ME5 (docs/EMBEDDING_RULE.md)"
        )


def test_custom_rag_adapter_default_is_me5_large():
    assert MODEL_NAME == "intfloat/multilingual-e5-large"


def test_custom_rag_adapter_defaults_apply_me5_prefixes():
    adapter = CustomRagAdapter(watch=False)
    assert adapter._model_name == "intfloat/multilingual-e5-large"
    assert adapter._query_prefix == "query: "
    assert adapter._passage_prefix == "passage: "


def test_embedding_rule_document_exists():
    assert RULE.exists(), (
        "docs/EMBEDDING_RULE.md must exist as the authoritative statement "
        "of the ME5-large standardization rule."
    )
    txt = RULE.read_text(encoding="utf-8")
    assert "intfloat/multilingual-e5-large" in txt
    assert "Box 0" in txt
    assert "Box A" in txt


def test_mmv_owned_vector_indexes_are_me5_dimensional():
    faiss = pytest.importorskip("faiss")
    for rel_path in [
        "data/box_0/custom_index.faiss",
        "data/box_a/custom_index.faiss",
        "data/memory/capsule_index.faiss",
    ]:
        idx = faiss.read_index(str(ROOT / rel_path))
        assert idx.d == 1024, f"{rel_path} is d={idx.d}, expected ME5 d=1024"


def test_rl_module_status_document_exists():
    # Adjacent doc from the same cycle — Phase 0 investigation output.
    # Keeping it under test ensures the RL-module clarification is not
    # silently removed by a future docs cleanup.
    assert RL_STATUS.exists(), (
        "docs/RL_MODULE_STATUS.md must exist — it records the Phase 0 "
        "finding that no runtime RL module is present in MOBIUS MMV, "
        "only an RL-style benchmark harness."
    )
    txt = RL_STATUS.read_text(encoding="utf-8")
    assert "eval/rl_bench" in txt
    assert "No runtime reinforcement-learning module" in txt
