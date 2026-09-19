#!/usr/bin/env python3
"""Strongest check available: run the QA questions against the REAL shipped index."""
import sys, os, json, gzip, glob, numpy as np, faiss, pathlib
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
lang, out = sys.argv[1], pathlib.Path(sys.argv[2])
saved = json.load(open(f"/home/happy/.codex/bench/wiki_forensics/questions_{lang}.json"))
titles, questions = saved["titles"], saved["questions"]
keep = [i for i,q in enumerate(questions) if len(q) > 10]
from sentence_transformers import SentenceTransformer
import torch
m = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda:0", model_kwargs={"torch_dtype": torch.float16})
Q = m.encode([f"query: {questions[i]}" for i in keep], batch_size=64, normalize_embeddings=True, convert_to_numpy=True).astype("float32")
ix = faiss.read_index(str(out/"wiki_index_ivfpq_me5.faiss"), faiss.IO_FLAG_MMAP)
titles_by_row = []
with gzip.open(out/"wiki_chunks.jsonl.gz","rt",encoding="utf-8") as f:
    for line in f: titles_by_row.append(json.loads(line)["title"])
titles_by_row = np.array(titles_by_row, dtype=object)
gold = [titles[i] for i in keep]
for nprobe in (32, 128):
    ix.nprobe = nprobe
    D, I = ix.search(Q, 10)
    hit1 = np.mean([titles_by_row[I[r,0]] == gold[r] for r in range(len(gold))])
    hit5 = np.mean([gold[r] in list(titles_by_row[I[r,:5]]) for r in range(len(gold))])
    rr = []
    for r in range(len(gold)):
        w = [j for j,t in enumerate(titles_by_row[I[r]]) if t == gold[r]]
        rr.append(1.0/(w[0]+1) if w else 0.0)
    print(f"{lang} nprobe={nprobe:3d}  recall@1={100*hit1:5.1f}  recall@5={100*hit5:5.1f}  MRR={100*np.mean(rr):5.1f}  "
          f"(gold article must be found among {ix.ntotal:,} chunks)", flush=True)
