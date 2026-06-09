#!/usr/bin/env python3
"""
rebuild_faiss.py — Memory Capsule FAISS インデックス再構築
scripts/rebuild_faiss.py

SQLite に保存済みの Capsule から FAISS インデックスを再構築する。
routing_engine が close() を呼ばずに終了した場合に発生する
FAISS 空問題を修正する。

実行:
    cd ~/デスクトップ/mobius_ai/MOBIUS_MMV
    python scripts/rebuild_faiss.py
"""
import argparse
import os
import sys, json, time
sys.path.insert(0, "src/memory")
sys.path.insert(0, "src/adapters")

import sqlite3
import numpy as np
from pathlib import Path

DB_PATH    = Path("data/memory/capsules.db")
INDEX_PATH = Path("data/memory/capsule_index.faiss")
MODEL_NAME = "intfloat/multilingual-e5-large"
DIM        = 1024

def _default_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def rebuild(device: str | None = None, batch_size: int = 512):
    if not DB_PATH.exists():
        print("ERROR: capsules.db not found"); return

    conn = sqlite3.connect(str(DB_PATH))
    total = conn.execute("SELECT COUNT(*) FROM capsules").fetchone()[0]
    print(f"SQLite: {total} capsules", flush=True)

    if not total:
        print("No capsules to rebuild"); return

    # encoder ロード
    try:
        from sentence_transformers import SentenceTransformer
        _device = device or _default_device()
        encoder = SentenceTransformer(MODEL_NAME, device=_device)
        print(f"Encoder loaded: {MODEL_NAME} (device={_device})", flush=True)
    except ImportError:
        print("sentence-transformers not available, using random vectors")
        encoder = None

    import faiss
    index = faiss.IndexFlatIP(DIM)

    t0 = time.time()
    cursor = conn.execute(
        "SELECT capsule_id, faiss_id, memory_text FROM capsules ORDER BY faiss_id"
    )

    done = 0
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        batch = [r[2] for r in rows]
        if encoder:
            vecs = encoder.encode(batch, normalize_embeddings=True)
        else:
            rng = np.random.default_rng(42)
            vecs = rng.random((len(batch), DIM)).astype("float32")
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            vecs = vecs / norms
        index.add(vecs.astype("float32"))
        done += len(rows)
        if done == len(rows) or done % (batch_size * 10) == 0 or done == total:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0.0
            print(f"  {done:,}/{total:,} vectors added ({rate:.1f}/s)", flush=True)

    tmp_path = INDEX_PATH.with_suffix(".faiss.new")
    faiss.write_index(index, str(tmp_path))
    os.replace(tmp_path, INDEX_PATH)
    elapsed = time.time() - t0
    print(f"\n✅ FAISS rebuilt: {index.ntotal} vectors in {elapsed:.1f}s")
    print(f"   Saved to: {INDEX_PATH} ({INDEX_PATH.stat().st_size//1024}KB)")
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--batch-size", type=int, default=512)
    args = parser.parse_args()
    rebuild(
        device=None if args.device == "auto" else args.device,
        batch_size=args.batch_size,
    )
