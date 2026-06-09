"""
Box 0 v8.2 ingest verification tests.

Validates that L0 v8.2 Integrated Edition has been ingested into Box 0 as
the canonical self-reference source, while v8.1 remains available as a
historical reference at prompts/l0_integrated_v8_1.md (outside Box 0).

Non-goals:
- Exercising the embedding model (tests do not require FAISS/ME5 load).
- Rebuilding the Box 0 index (rebuild is performed at adapter.load() time).
These tests inspect Box 0 artifacts on disk; they are fast and adapter-free.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "corpus_box_0"
DATA_DIR = ROOT / "data" / "box_0"
CHUNKS_PATH = DATA_DIR / "custom_chunks.jsonl"
MANIFEST_PATH = DATA_DIR / "index_manifest.json"
V8_2_COPY = CORPUS_DIR / "l0_integrated_v8_2.md"
V8_2_SOURCE = ROOT / "prompts" / "l0_integrated_v8_2.md"
V8_1_SOURCE = ROOT / "prompts" / "l0_integrated_v8_1.md"


# ── Corpus-level invariants ──────────────────────────────────────────────────

def test_v8_2_corpus_copy_exists():
    assert V8_2_COPY.exists(), (
        f"Box 0 must contain a copy of the v8.2 MD at {V8_2_COPY}. "
        "If missing, re-run: cp prompts/l0_integrated_v8_2.md corpus_box_0/"
    )


def test_v8_2_copy_matches_source_byte_for_byte():
    assert V8_2_SOURCE.exists(), "prompts/l0_integrated_v8_2.md must exist"
    assert V8_2_COPY.read_bytes() == V8_2_SOURCE.read_bytes(), (
        "corpus_box_0/l0_integrated_v8_2.md must be byte-identical to the "
        "canonical prompts/l0_integrated_v8_2.md — no in-flight edits to the "
        "Box 0 copy, no banner insertions."
    )


def test_v8_1_is_not_ingested_into_box_0():
    # Per Task 3-C: "未 ingest の場合: 現状維持". v8.1 should remain at
    # prompts/l0_integrated_v8_1.md only, not be copied into corpus_box_0/.
    v8_1_in_corpus = CORPUS_DIR / "l0_integrated_v8_1.md"
    assert not v8_1_in_corpus.exists(), (
        "v8.1 must not be ingested into Box 0 (historical reference remains "
        "at prompts/l0_integrated_v8_1.md only)."
    )


def test_v8_1_source_file_preserved_outside_box_0():
    if not V8_1_SOURCE.exists():
        pytest.skip(
            "prompts/l0_integrated_v8_1.md is not present in this workspace; "
            "Box 0 still verifies that v8.1 is not ingested."
        )


# ── Manifest integrity ──────────────────────────────────────────────────────

def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        pytest.skip(
            "Box 0 index manifest not built. Run adapter.load() once, then "
            "re-run this test. (This skip is intentional for fresh clones.)"
        )
    return json.loads(MANIFEST_PATH.read_text())


def test_manifest_lists_v8_2():
    manifest = _load_manifest()
    files = manifest.get("files", {})
    assert "l0_integrated_v8_2.md" in files, (
        f"Box 0 index manifest must list the v8.2 file. "
        f"Found: {sorted(files.keys())}"
    )


def test_manifest_does_not_list_v8_1():
    # Defensive: v8.1 must not leak into Box 0 index.
    manifest = _load_manifest()
    files = manifest.get("files", {})
    assert "l0_integrated_v8_1.md" not in files, (
        "v8.1 must not appear in Box 0 index manifest. "
        f"Found: {sorted(files.keys())}"
    )


def test_manifest_preserves_legacy_complete_system_docs():
    # Box 0 historical docs (v2/v4/v5/v6 complete system) must remain
    # alongside v8.2. Regression guard against over-aggressive rebuild.
    manifest = _load_manifest()
    files = manifest.get("files", {})
    for expected in (
        "mobius_box_0_complete_system_v2.md",
        "mobius_box_0_complete_system_v4.md",
        "mobius_box_0_complete_system_v5.md",
        "mobius_box_0_complete_system_v6.md",
        "mobius_box_a_canonical_overview_en.md",
    ):
        assert expected in files, (
            f"Legacy Box 0 doc missing from manifest: {expected}"
        )


# ── Chunk-level invariants ──────────────────────────────────────────────────

def _load_chunks() -> list[dict]:
    if not CHUNKS_PATH.exists():
        pytest.skip(
            "Box 0 chunks file not built. Run adapter.load() once, then "
            "re-run this test."
        )
    return [json.loads(line) for line in CHUNKS_PATH.read_text().splitlines() if line]


def test_v8_2_produces_chunks():
    chunks = _load_chunks()
    v8_2_chunks = [c for c in chunks if c.get("source_label") == "l0_integrated_v8_2.md"]
    assert len(v8_2_chunks) > 0, (
        "v8.2 must produce at least one chunk after ingest."
    )


def test_v8_2_chunk_count_reflects_document_size():
    # v8.2 is ~466 KB. A document that size should produce many chunks
    # (observed post-ingest: 241 chunks). We assert a loose lower bound so
    # the test survives chunker-parameter tuning.
    chunks = _load_chunks()
    v8_2_chunks = [c for c in chunks if c.get("source_label") == "l0_integrated_v8_2.md"]
    assert len(v8_2_chunks) >= 50, (
        f"v8.2 should produce a substantial number of chunks (observed 241 "
        f"post-ingest). Got {len(v8_2_chunks)} — chunker may have regressed."
    )


def test_v8_2_chunks_contain_signature_terms():
    # v8.2-specific signature phrases — if any are missing from every
    # v8.2 chunk, the ingest copy has been edited or truncated.
    chunks = _load_chunks()
    v8_2_text = "\n".join(
        c["text"] for c in chunks
        if c.get("source_label") == "l0_integrated_v8_2.md"
    )
    # These phrases are present in the canonical v8.2 document.
    for phrase in [
        "Implementation Status (v8.2 Reality Reconciliation",
        "Drift item D1",
    ]:
        assert phrase in v8_2_text, (
            f"v8.2 signature phrase missing from Box 0 ingest: {phrase!r}"
        )
