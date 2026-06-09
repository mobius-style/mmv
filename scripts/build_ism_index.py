#!/usr/bin/env python3
"""
build_ism_index.py — ISM + QK FAISS index builder

Input:  data/raf/teacher_data_raw.jsonl
Output:
  data/raf/ism_index.faiss    (intent layer index)
  data/raf/ism_chunks.jsonl   (chunk metadata)
  data/raf/qk_index.faiss     (entitlement layer index)
  data/raf/qk_chunks.jsonl    (chunk metadata)

Embedding: intfloat/multilingual-e5-large (device=cuda:0, Principle G解除)

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import faiss
import numpy as np

ROOT = Path(__file__).parent.parent

TEACHER_PATH = ROOT / "data" / "raf" / "teacher_data_raw.jsonl"
ISM_INDEX    = ROOT / "data" / "raf" / "ism_index.faiss"
ISM_CHUNKS   = ROOT / "data" / "raf" / "ism_chunks.jsonl"
QK_INDEX     = ROOT / "data" / "raf" / "qk_index.faiss"
QK_CHUNKS    = ROOT / "data" / "raf" / "qk_chunks.jsonl"

MODEL_NAME = "intfloat/multilingual-e5-large"


def load_teacher_data() -> list[dict]:
    if not TEACHER_PATH.exists():
        print(f"[ERROR] {TEACHER_PATH} not found. Run wall_ball_generator.py first.")
        sys.exit(1)
    entries = []
    with open(TEACHER_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def build_index(entries: list[dict], text_key: str, label_key: str,
                index_path: Path, chunks_path: Path, model) -> int:
    """Build a FAISS IndexFlatIP from entries."""
    texts = []
    chunks = []
    for e in entries:
        text = e.get(text_key, "")
        if not text:
            continue
        texts.append("passage: " + text)
        chunks.append(e)

    if not texts:
        print(f"  No texts for {index_path.name}")
        return 0

    print(f"  Encoding {len(texts)} texts...")
    vectors = model.encode(texts, convert_to_numpy=True,
                           normalize_embeddings=True, show_progress_bar=False)
    vectors = vectors.astype(np.float32)

    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)

    faiss.write_index(index, str(index_path))
    with open(chunks_path, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"  {index_path.name}: {index.ntotal} vectors, dim={dim}")
    return index.ntotal


def main():
    entries = load_teacher_data()
    print(f"Loaded {len(entries)} teacher labels")

    from sentence_transformers import SentenceTransformer
    print(f"Loading {MODEL_NAME} (device=cuda:0)...")
    model = SentenceTransformer(MODEL_NAME, device="cuda:0")

    # ISM index: keyed on query text, labeled by intent_type
    print("\n=== Building ISM index ===")
    n_ism = build_index(entries, "query", "intent_type",
                        ISM_INDEX, ISM_CHUNKS, model)

    # QK index: keyed on query text, labeled by qk_entitlement
    print("\n=== Building QK index ===")
    n_qk = build_index(entries, "query", "qk_entitlement",
                       QK_INDEX, QK_CHUNKS, model)

    print(f"\nDone. ISM={n_ism} vectors, QK={n_qk} vectors")


if __name__ == "__main__":
    main()
