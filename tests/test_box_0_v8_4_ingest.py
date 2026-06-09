"""
Box 0 v8.4 current-authority ingest verification tests.

v8.2 remains in Box 0 as inherited constitutional substrate. v8.4 is the
current RC3.3 synchronization authority and must also be present in Box 0
for self-reference / self-description retrieval.
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

V8_4_MD_COPY = CORPUS_DIR / "l0_integrated_v8_4.md"
V8_4_MD_SOURCE = ROOT / "prompts" / "l0_integrated_v8_4.md"
V8_4_JSON_COPY = CORPUS_DIR / "mobius_l0_v8_4_protocol.json"
V8_4_JSON_SOURCE = ROOT / "prompts" / "mobius_l0_v8_4_protocol.json"


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        pytest.skip(
            "Box 0 index manifest not built. Rebuild Box 0, then re-run."
        )
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_chunks() -> list[dict]:
    if not CHUNKS_PATH.exists():
        pytest.skip("Box 0 chunks file not built. Rebuild Box 0, then re-run.")
    return [
        json.loads(line)
        for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_v8_4_corpus_sources_exist():
    assert V8_4_MD_COPY.exists()
    assert V8_4_JSON_COPY.exists()


def test_v8_4_corpus_sources_match_prompts_byte_for_byte():
    assert V8_4_MD_COPY.read_bytes() == V8_4_MD_SOURCE.read_bytes()
    assert V8_4_JSON_COPY.read_bytes() == V8_4_JSON_SOURCE.read_bytes()


def test_manifest_lists_v8_4_sources():
    files = _load_manifest().get("files", {})
    assert "l0_integrated_v8_4.md" in files
    assert "mobius_l0_v8_4_protocol.json" in files


def test_v8_4_chunks_contain_current_authority_terms():
    chunks = _load_chunks()
    v8_4_text = "\n".join(
        c["text"]
        for c in chunks
        if c.get("source_label") in {
            "l0_integrated_v8_4.md",
            "mobius_l0_v8_4_protocol.json",
        }
    )
    for phrase in [
        "L0 v8.4",
        "RC3.3",
        "date_bound_answer",
        "re_anchor",
    ]:
        assert phrase in v8_4_text
