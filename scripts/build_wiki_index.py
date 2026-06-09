#!/usr/bin/env python3
"""
build_wiki_index_v10.py — Phase C Box B: Wikipedia ZIM → FAISS IndexIVFPQ
v10: チェックポイント方式（4分割）+ 進捗ゲージ

変更点（v9からの改善）:
  - 21.9Mチャンクを4Partに分割して逐次保存
  - 途中で落ちても完了済みPartはスキップして再開
  - 全Part完了後にmerge_from()で統合
  - Part単位・全体の進捗ゲージ（tqdm）を表示

Author: Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations
import argparse, gzip, json, os, re, sys, time
import multiprocessing as mp
from datetime import datetime, timezone
from pathlib import Path

def check_deps():
    missing = []
    for pkg in ["libzim","sentence_transformers","faiss","numpy","torch","psutil","tqdm"]:
        try: __import__(pkg)
        except ImportError: missing.append(pkg)
    if missing:
        print(f"ERROR: missing: {missing}")
        sys.exit(1)

check_deps()

import numpy as np
import faiss
import torch
import psutil
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
import libzim

# ── 定数 ─────────────────────────────────────────────────────────────────────
MODEL_NAME     = "intfloat/multilingual-e5-large"
DIM            = 1024
CHUNK_CHARS    = 1536
OVERLAP_CHARS  = 256
NLIST          = 4096
M_PQ           = 48
NBITS          = 8
DEFAULT_BATCH  = 1024
RAM_RESERVE_GB = 10.0
N_PARTS        = 4

def calc_buffer_size() -> int:
    available_gb    = psutil.virtual_memory().available / 1e9
    usable_gb       = max(0, available_gb - RAM_RESERVE_GB) * 0.40
    bytes_per_chunk = 3200  # 実測値ベース
    calc_buf        = int(usable_gb * 1e9 / bytes_per_chunk)
    return max(2_000_000, min(calc_buf, 8_000_000))

# ── HTML除去・チャンク ────────────────────────────────────────────────────────
_TAG_RE = re.compile(r"<[^>]+>")
_SPC_RE = re.compile(r"\s+")

def strip_html(html: str) -> str:
    return _SPC_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()

def chunk_text(text: str) -> list[str]:
    if not text or len(text) < 80: return []
    if len(text) <= CHUNK_CHARS: return [text]
    chunks, start = [], 0
    while start < len(text):
        chunk = text[start:start + CHUNK_CHARS].strip()
        if chunk: chunks.append(chunk)
        start += CHUNK_CHARS - OVERLAP_CHARS
    return chunks

# ── CPUワーカー ───────────────────────────────────────────────────────────────
def _worker_write_to_tmpfile(args: tuple) -> tuple[str, int, int]:
    zim_path, start, end, w_max, worker_id, tmp_dir = args
    tmp_path = os.path.join(tmp_dir, f"worker_{worker_id:03d}.jsonl.gz")
    try:
        archive = libzim.Archive(zim_path)
    except Exception as e:
        print(f"  [worker {worker_id}] open failed: {e}", flush=True)
        return tmp_path, 0, 0
    article_count = chunk_count = 0
    with gzip.open(tmp_path, "wt", encoding="utf-8") as f:
        for entry_id in range(start, end):
            if w_max and article_count >= w_max: break
            try:
                entry = archive._get_entry_by_id(entry_id)
                if entry.is_redirect: continue
                item = entry.get_item()
                if "html" not in str(item.mimetype).lower(): continue
                raw  = bytes(item.content).decode("utf-8", errors="ignore")
                text = strip_html(raw)
                if len(text) < 80: continue
                url = f"https://en.wikipedia.org/wiki/{entry.path.replace(' ','_')}"
                for ci, chunk in enumerate(chunk_text(text)):
                    f.write(json.dumps({
                        "title": entry.title, "url": url,
                        "text": chunk, "chunk_index": ci,
                        "license": "CC BY-SA 4.0",
                    }, ensure_ascii=False) + "\n")
                    chunk_count += 1
                article_count += 1
            except Exception:
                continue
    print(f"  [worker {worker_id}] done: {article_count:,} articles {chunk_count:,} chunks", flush=True)
    return tmp_path, article_count, chunk_count

# ── Stage 1: ZIM → chunks.jsonl.gz ──────────────────────────────────────────
def stage1_zim_to_chunks(zim_path, chunks_path, manifest_path, max_articles, n_workers):
    print(f"[Stage 1] ZIM → chunks.jsonl.gz  workers={n_workers}")
    archive     = libzim.Archive(zim_path)
    entry_count = archive.entry_count
    art_count   = archive.article_count
    print(f"  entry_count={entry_count:,}  article_count={art_count:,}")
    del archive

    tmp_dir    = str(chunks_path.parent / "tmp_workers")
    os.makedirs(tmp_dir, exist_ok=True)
    chunk_size = entry_count // n_workers
    ranges = []
    for i in range(n_workers):
        s     = i * chunk_size
        e     = entry_count if i == n_workers-1 else (i+1)*chunk_size
        w_max = (max_articles // n_workers) if max_articles else 0
        ranges.append((zim_path, s, e, w_max, i, tmp_dir))

    print(f"  Launching {n_workers} workers...")
    t0 = time.time()
    with mp.Pool(processes=n_workers) as pool:
        results = pool.map(_worker_write_to_tmpfile, ranges)

    total_art = sum(r[1] for r in results)
    total_chk = sum(r[2] for r in results)
    print(f"  Workers done: {total_art:,} articles {total_chk:,} chunks ({time.time()-t0:.0f}s)")

    print(f"  Merging {n_workers} tmp files...")
    chunk_count = 0
    with gzip.open(chunks_path, "wt", encoding="utf-8") as f_out:
        for tmp_path, _, _ in results:
            if not os.path.exists(tmp_path): continue
            with gzip.open(tmp_path, "rt", encoding="utf-8") as f_in:
                for line in f_in:
                    try:
                        meta = json.loads(line)
                        meta["chunk_id"] = chunk_count
                        f_out.write(json.dumps(meta, ensure_ascii=False) + "\n")
                        chunk_count += 1
                    except Exception:
                        continue
            os.remove(tmp_path)
    try: os.rmdir(tmp_dir)
    except: pass
    print(f"  Merge done: {chunk_count:,} chunks")

    manifest_path.write_text(json.dumps({
        "stage1_done": True, "chunk_count": chunk_count,
        "zim_source": Path(zim_path).name, "n_workers": n_workers,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    return chunk_count

# ── FAISS Training（保存・再利用）────────────────────────────────────────────
def load_or_train_index(chunks_path, trained_path, chunk_count, batch_size, model, pool):
    nlist     = min(NLIST, chunk_count // 10)
    quantizer = faiss.IndexFlatIP(DIM)
    index     = faiss.IndexIVFPQ(quantizer, DIM, nlist, M_PQ, NBITS)

    if trained_path.exists():
        print(f"\n  [FAISS Training] 保存済みを読み込み: {trained_path.name}")
        index = faiss.read_index(str(trained_path))
        return index, nlist

    train_size = min(chunk_count, nlist * 64)
    print(f"\n  [FAISS Training] {train_size:,} samples...")
    train_texts = []
    with gzip.open(chunks_path, "rt", encoding="utf-8") as f:
        for line in f:
            if len(train_texts) >= train_size: break
            try: train_texts.append(json.loads(line)["text"])
            except: continue

    if pool:
        train_emb = model.encode(train_texts, batch_size=batch_size,
                                 show_progress_bar=True, convert_to_numpy=True, pool=pool)
    else:
        train_emb = model.encode(train_texts, batch_size=batch_size,
                                 show_progress_bar=True, convert_to_numpy=True)

    train_emb = np.array(train_emb, dtype=np.float32)
    faiss.normalize_L2(train_emb)
    index.train(train_emb)
    del train_texts, train_emb

    faiss.write_index(index, str(trained_path))
    print(f"  Training saved: {trained_path.name}")
    return index, nlist

# ── Stage 2: チェックポイント方式パイプライン ─────────────────────────────────
def stage2_checkpoint_pipeline(chunks_path, out_dir, manifest_path,
                                chunk_count, batch_size, model):
    gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
    buf_size  = calc_buffer_size()
    ram_gb    = buf_size * 3200 / 1e9

    print(f"\n[Stage 2] チェックポイント方式パイプライン")
    print(f"  RAM available:  {psutil.virtual_memory().available/1e9:.1f}GB")
    print(f"  Buffer size:    {buf_size:,} chunks ({ram_gb:.1f}GB)")
    print(f"  GPU:            {gpu_count}")
    print(f"  Total chunks:   {chunk_count:,}")
    print(f"  Parts:          {N_PARTS}")

    pool = None
    if gpu_count >= 2:
        pool = model.start_multi_process_pool(target_devices=["cuda:0","cuda:1"])
        print(f"  Multi-GPU pool: cuda:0 + cuda:1")

    trained_path = out_dir / "wiki_index_trained.faiss"
    base_index, nlist = load_or_train_index(
        chunks_path, trained_path, chunk_count, batch_size, model, pool)

    # Part範囲を計算
    part_size = chunk_count // N_PARTS
    parts = []
    for i in range(N_PARTS):
        s = i * part_size
        e = chunk_count if i == N_PARTS-1 else (i+1)*part_size
        parts.append((s, e))

    t_total   = time.time()
    completed = []

    # 全体進捗バー
    total_bar = tqdm(total=chunk_count, desc="[Total]",
                     unit="chunks", position=0,
                     bar_format="{desc}: {percentage:3.0f}%|{bar:20}| "
                                "{n_fmt}/{total_fmt} {rate_fmt} ETA {remaining}")

    for part_idx, (p_start, p_end) in enumerate(parts):
        part_num  = part_idx + 1
        part_path = out_dir / f"faiss_part{part_num}.faiss"

        if part_path.exists():
            part_size_actual = p_end - p_start
            print(f"\n  [Part {part_num}/{N_PARTS}] スキップ（完了済み）: {part_path.name}")
            total_bar.update(part_size_actual)
            completed.append(part_path)
            continue

        print(f"\n  [Part {part_num}/{N_PARTS}] {p_start:,} 〜 {p_end:,} ({p_end-p_start:,} chunks)")

        # 訓練済みインデックスを読み込み（このPartのベース）
        part_index = faiss.read_index(str(trained_path))

        part_bar = tqdm(total=p_end-p_start,
                        desc=f"[Part {part_num}/{N_PARTS}]",
                        unit="chunks", position=1, leave=False,
                        bar_format="{desc}: {percentage:3.0f}%|{bar:20}| "
                                   "{n_fmt}/{total_fmt} {rate_fmt} ETA {remaining}")

        def flush(texts):
            if not texts: return
            if pool:
                emb = model.encode(texts, batch_size=batch_size,
                                   show_progress_bar=False,
                                   convert_to_numpy=True, pool=pool)
            else:
                emb = model.encode(texts, batch_size=batch_size,
                                   show_progress_bar=False, convert_to_numpy=True)
            emb = np.array(emb, dtype=np.float32)
            faiss.normalize_L2(emb)
            part_index.add(emb)
            del emb
            del texts

        buf_texts  = []
        global_idx = 0
        t_part     = time.time()

        with gzip.open(chunks_path, "rt", encoding="utf-8") as f:
            for line in f:
                if global_idx < p_start:
                    global_idx += 1
                    continue
                if global_idx >= p_end:
                    break
                try:
                    buf_texts.append(json.loads(line)["text"])
                except:
                    global_idx += 1
                    continue
                global_idx += 1

                if len(buf_texts) >= buf_size:
                    n = len(buf_texts)
                    flush(buf_texts)
                    buf_texts = []
                    part_bar.update(n)
                    total_bar.update(n)
                    ram_now = psutil.virtual_memory().available / 1e9
                    tqdm.write(f"  [Part {part_num}] {part_index.ntotal:,} vectors "
                               f"RAM={ram_now:.1f}GB")

        if buf_texts:
            n = len(buf_texts)
            flush(buf_texts)
            part_bar.update(n)
            total_bar.update(n)

        part_bar.close()

        # Part保存
        faiss.write_index(part_index, str(part_path))
        elapsed = time.time() - t_part
        print(f"\n  [Part {part_num}] 保存完了: {part_path.name} "
              f"({part_index.ntotal:,} vectors, {elapsed:.0f}s)")
        completed.append(part_path)
        del part_index

    total_bar.close()

    if pool:
        model.stop_multi_process_pool(pool)

    # Stage 3: マージ
    print(f"\n[Stage 3] {N_PARTS}パートをマージ...")
    final_path = out_dir / "wiki_index_ivfpq.faiss"
    merged = faiss.read_index(str(completed[0]))
    for p in completed[1:]:
        idx = faiss.read_index(str(p))
        merged.merge_from(idx, merged.ntotal)
        del idx
        print(f"  merged: {p.name} → total {merged.ntotal:,}")

    faiss.write_index(merged, str(final_path))
    index_gb  = final_path.stat().st_size / 1e9
    memory_gb = round(chunk_count * M_PQ / 1e9, 3)
    print(f"  wiki_index_ivfpq.faiss: {index_gb:.2f}GB (~{memory_gb:.2f}GB in memory)")

    # 後片付け
    for p in completed:
        p.unlink()
    if trained_path.exists():
        trained_path.unlink()
    print(f"  チェックポイントファイル削除完了")

    # manifest更新
    manifest = json.loads(manifest_path.read_text())
    manifest.update({
        "stage2_done": True, "model": MODEL_NAME,
        "dim": DIM, "index_type": "IndexIVFPQ",
        "nlist": nlist, "m": M_PQ, "nbits": NBITS,
        "buffer_size_chunks": buf_size,
        "index_size_gb": round(index_gb, 3),
        "chunks_size_gb": round(chunks_path.stat().st_size / 1e9, 3),
        "index_memory_gb": memory_gb,
        "gpu_count": gpu_count, "batch_size_used": batch_size,
        "n_parts": N_PARTS,
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    total_elapsed = time.time() - t_total
    print(f"\n=== Build complete ===")
    print(f"  Total vectors: {merged.ntotal:,}")
    print(f"  Index:         {index_gb:.2f}GB")
    print(f"  Memory:        ~{memory_gb:.2f}GB")
    print(f"  Total time:    {total_elapsed/3600:.1f}h")

# ── メイン ────────────────────────────────────────────────────────────────────
def build(zim_path, out_dir, batch_size, max_articles, skip_stage1, n_workers):
    out           = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chunks_path   = out / "wiki_chunks.jsonl.gz"
    manifest_path = out / "wiki_manifest.json"

    if skip_stage1 and chunks_path.exists() and manifest_path.exists():
        print(f"[Stage 1] Skipped (--skip-stage1)")
        chunk_count = json.loads(manifest_path.read_text())["chunk_count"]
        print(f"  chunk_count: {chunk_count:,}")
    else:
        chunk_count = stage1_zim_to_chunks(
            zim_path, chunks_path, manifest_path, max_articles, n_workers)

    print()
    print("[Loading embedding model...]")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  device={device}  GPUs={torch.cuda.device_count()}")
    model = SentenceTransformer(MODEL_NAME, device=device)

    for bs in [batch_size, batch_size//2, 256, 128, 64]:
        try:
            model.encode(["test"] * bs, batch_size=bs, show_progress_bar=False)
            if torch.cuda.is_available(): torch.cuda.empty_cache()
            print(f"  batch_size={bs} OK")
            batch_size = bs
            break
        except RuntimeError:
            if torch.cuda.is_available(): torch.cuda.empty_cache()

    stage2_checkpoint_pipeline(
        chunks_path, out, manifest_path, chunk_count, batch_size, model)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="MOBIUS Phase C — Wikipedia Index Builder v10")
    ap.add_argument("--zim",          required=True)
    ap.add_argument("--out",          default="data/box_b/")
    ap.add_argument("--batch-size",   type=int, default=DEFAULT_BATCH)
    ap.add_argument("--max-articles", type=int, default=0)
    ap.add_argument("--skip-stage1",  action="store_true")
    ap.add_argument("--workers",      type=int, default=max(1, mp.cpu_count()-2))
    args = ap.parse_args()

    max_str   = 'ALL' if not args.max_articles else f'{args.max_articles:,}'
    ram_total = psutil.virtual_memory().total / 1e9
    ram_avail = psutil.virtual_memory().available / 1e9
    buf_size  = calc_buffer_size()

    print("================================================================")
    print(" MOBIUS Phase C — Box B: Wikipedia Index Builder v10")
    print("================================================================")
    print(f" ZIM:         {args.zim}")
    print(f" Out:         {args.out}")
    print(f" Batch:       {args.batch_size}")
    print(f" Max:         {max_str}")
    print(f" Workers:     {args.workers} / {mp.cpu_count()} cores")
    print(f" RAM:         {ram_avail:.1f}GB avail / {ram_total:.1f}GB total")
    print(f" Buffer:      {buf_size:,} chunks ({buf_size*3200/1e9:.1f}GB)")
    print(f" Skip Stage1: {args.skip_stage1}")
    print(f" Parts:       {N_PARTS}（チェックポイント方式）")
    print()

    build(args.zim, args.out, args.batch_size,
          args.max_articles, args.skip_stage1, args.workers)
