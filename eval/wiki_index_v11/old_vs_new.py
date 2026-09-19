#!/usr/bin/env python3
"""The comparison that matters: same questions, old published artifact vs new one, full scale.
Restricted to gold articles present in BOTH stores, so the older dump is not penalised for
articles that did not exist yet."""
import sys, os, json, gzip, numpy as np, faiss, pathlib
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
lang = sys.argv[1]
OLD = {"ja": "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_ja_me5",
       "zh": "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_zh_me5"}[lang]
NEW = {"ja": "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_ja_me5_2026-06_bplus",
       "zh": "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_zh_me5_2026-05_bplus"}[lang]
saved = json.load(open(f"questions_{lang}.json")); titles, questions = saved["titles"], saved["questions"]
def load_titles(d):
    out = []
    with gzip.open(pathlib.Path(d)/"wiki_chunks.jsonl.gz","rt",encoding="utf-8") as f:
        for line in f: out.append(json.loads(line)["title"])
    return np.array(out, dtype=object)
tn, to = load_titles(NEW), load_titles(OLD)
set_old, set_new = set(to.tolist()), set(tn.tolist())
keep = [i for i,q in enumerate(questions) if len(q) > 10 and titles[i] in set_old and titles[i] in set_new]
print(f"{lang}: {len(keep)} questions whose gold article exists in both stores "
      f"(old {len(to):,} chunks / new {len(tn):,} chunks)", flush=True)
import torch
from sentence_transformers import SentenceTransformer
m = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda:0", model_kwargs={"torch_dtype": torch.float16})
Q = m.encode([f"query: {questions[i]}" for i in keep], batch_size=64, normalize_embeddings=True, convert_to_numpy=True).astype("float32")
gold = [titles[i] for i in keep]
for label, d, rows in (("old (published)", OLD, to), ("new (v11, SQ4)", NEW, tn)):
    ix = faiss.read_index(str(pathlib.Path(d)/"wiki_index_ivfpq_me5.faiss"), faiss.IO_FLAG_MMAP)
    for nprobe in (128,):
        ix.nprobe = nprobe; D, I = ix.search(Q, 10)
        h1 = np.mean([rows[I[r,0]] == gold[r] for r in range(len(gold))])
        h5 = np.mean([gold[r] in list(rows[I[r,:5]]) for r in range(len(gold))])
        rr = []
        for r in range(len(gold)):
            w = [j for j,t in enumerate(rows[I[r]]) if t == gold[r]]
            rr.append(1.0/(w[0]+1) if w else 0.0)
        print(f"  {label:18s} nprobe={nprobe}  recall@1={100*h1:5.1f}  recall@5={100*h5:5.1f}  MRR={100*np.mean(rr):5.1f}", flush=True)
    del ix
