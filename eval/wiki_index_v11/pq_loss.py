#!/usr/bin/env python3
"""How much recall does IVFPQ(m=64) lose vs exact search, and does training on the
alphabetical head (old) vs a uniform sample (new) matter?  ~150k real ja chunks."""
import os, sys, gzip, json, time, numpy as np, faiss
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
from sentence_transformers import SentenceTransformer
N = int(sys.argv[1]) if len(sys.argv) > 1 else 150000
P = "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_ja_me5/wiki_chunks.jsonl.gz"
texts = []
with gzip.open(P,"rt",encoding="utf-8") as f:
    for i,l in enumerate(f):
        if i >= N: break
        texts.append(json.loads(l)["text"][:1200])
model = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda")
t0=time.time()
X = model.encode(["passage: "+t for t in texts], batch_size=128, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False).astype("float32")
print(f"embedded {len(X)} in {time.time()-t0:.0f}s", flush=True)
rng = np.random.default_rng(0); qi = rng.choice(len(X), 1000, replace=False)
Q = X[qi] + rng.normal(0, 0.02, X[qi].shape).astype("float32"); Q /= np.linalg.norm(Q, axis=1, keepdims=True)   # perturbed self-queries
flat = faiss.IndexFlatIP(1024); flat.add(X); _, G = flat.search(Q, 10)
def recall(I): return np.mean([len(set(I[r]) & set(G[r]))/10 for r in range(len(Q))])
d = 1024; nlist = 1024   # scaled for 150k vectors (~146/list; production 4096 lists for 6.4M ≈ 1,560/list)
for name, m, train_idx in [("PQ m=64, head-trained", 64, np.arange(min(len(X), nlist*64))),
                           ("PQ m=64, uniform-trained", 64, np.arange(0, len(X), max(1, len(X)//(nlist*64)))[:nlist*64]),
                           ("PQ m=128, uniform-trained", 128, np.arange(0, len(X), max(1, len(X)//(nlist*64)))[:nlist*64])]:
    ix = faiss.IndexIVFPQ(faiss.IndexFlatIP(d), d, nlist, m, 8, faiss.METRIC_INNER_PRODUCT)
    ix.train(X[train_idx]); ix.add(X)
    row = []
    for nprobe in (8, 32, 64, 128):
        ix.nprobe = nprobe; _, I = ix.search(Q, 10); row.append(f"nprobe {nprobe}: {100*recall(I):5.1f}%")
    print(f"{name:26s} bytes/vec={m}  recall@10 vs exact -> " + " | ".join(row), flush=True)
ix = faiss.IndexIVFScalarQuantizer(faiss.IndexFlatIP(d), d, nlist, faiss.ScalarQuantizer.QT_8bit, faiss.METRIC_INNER_PRODUCT)
ix.train(X[np.arange(0, len(X), max(1, len(X)//(nlist*64)))[:nlist*64]]); ix.add(X)
row=[]
for nprobe in (8,32,64,128):
    ix.nprobe=nprobe; _, I = ix.search(Q, 10); row.append(f"nprobe {nprobe}: {100*recall(I):5.1f}%")
print(f"{'SQ8 (1024 B/vec), uniform':26s} bytes/vec=1024 recall@10 vs exact -> " + " | ".join(row))
