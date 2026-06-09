"""Box 0 ME5-large migration — contract-level assertions.

Per Evolution Log cyc_20260423_production_quality_deep_fix (Phase 2, Fix L1-A):
Box 0's embedding encoder was MiniLM-L6-v2 (English-only, 384-dim), which
produced semantic drift on Japanese self-reference queries — the canonical
production symptom was `"貴方の特徴を教えてください"` retrieving a persona-
safety chunk instead of MOBIUS identity chunks. Box 0 has been migrated to
`intfloat/multilingual-e5-large` (ME5, 1024-dim, cross-lingual).

These tests are index-only — they do NOT load the SentenceTransformer. They
lock in:
  1. The on-disk manifest records ME5 as Box 0's encoder.
  2. The FAISS index dimensionality matches ME5 (1024), not MiniLM (384).
  3. Chunks are present at roughly the expected count (regression canary).

These assertions must remain true for any future rebuild of Box 0. If a
future change lands that rebuilds Box 0 with a different encoder, that
change must also update this file and docs/EMBEDDING_RULE.md explicitly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import faiss

ROOT = Path(__file__).resolve().parents[1]
BOX_0 = ROOT / "data" / "box_0"
MANIFEST = BOX_0 / "index_manifest.json"
INDEX    = BOX_0 / "custom_index.faiss"
CHUNKS   = BOX_0 / "custom_chunks.jsonl"

ME5_NAME = "intfloat/multilingual-e5-large"
ME5_DIM  = 1024


@pytest.mark.skipif(not MANIFEST.exists(), reason="Box 0 manifest not present")
def test_box_0_manifest_records_me5_encoder():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data.get("model") == ME5_NAME, (
        f"Box 0 manifest must record ME5 as encoder "
        f"(EMBEDDING_RULE.md); got {data.get('model')!r}"
    )


@pytest.mark.skipif(not INDEX.exists(), reason="Box 0 index not present")
def test_box_0_index_is_1024_dim():
    idx = faiss.read_index(str(INDEX))
    assert idx.d == ME5_DIM, (
        f"Box 0 FAISS index must be {ME5_DIM}-dim (ME5-large); "
        f"got d={idx.d}. If this fails, the index was likely "
        f"rebuilt with a non-ME5 encoder — revert or re-migrate."
    )


@pytest.mark.skipif(not CHUNKS.exists(), reason="Box 0 chunks not present")
def test_box_0_has_nontrivial_chunk_count():
    with open(CHUNKS, encoding="utf-8") as f:
        n = sum(1 for line in f if line.strip())
    # Current corpus (l0 v8.2 + mobius_box_0_complete_system_v{2,4,5,6} +
    # mobius_box_a_canonical_overview_en) yields 359 chunks. Allow ±20% as
    # a regression canary without over-constraining future corpus edits.
    assert 280 <= n <= 440, (
        f"Box 0 chunk count {n} is outside the expected 280-440 range. "
        f"If corpus was intentionally resized, adjust this bound."
    )


@pytest.mark.skipif(not MANIFEST.exists() or not INDEX.exists(),
                     reason="Box 0 artifacts not present")
def test_box_0_manifest_chunk_count_matches_index():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    idx = faiss.read_index(str(INDEX))
    assert data.get("chunk_count") == idx.ntotal, (
        f"Manifest chunk_count ({data.get('chunk_count')}) must match "
        f"index.ntotal ({idx.ntotal}). Mismatch indicates a stale "
        f"manifest from a pre-migration rebuild."
    )
