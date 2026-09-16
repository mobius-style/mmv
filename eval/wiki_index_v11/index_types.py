#!/usr/bin/env python3
"""Which index type gives acceptable ANN fidelity for ME5 vectors, and at what size?
Saves the embeddings so variants can be re-run without re-embedding."""
import os, sys, gzip, json, time, numpy as np, faiss
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 150000
cache = f"/home/happy/.codex/bench/wiki_forensics/emb_ja_{N}.npy"
if os.path.exists(cache):
    X = np.load(cache)
else:
    from sentence_transformers import SentenceTransformer
    texts = []
    with gzip.open("/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_ja_me5/wiki_chunks.jsonl.gz","rt",encoding="utf-8") as f:
        for i,l in enumerate(f):
            if i >= N: break
            texts.append(json.loads(l)["text"][:1200])
    model = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda")
    X = model.encode(["passage: "+t for t in texts], batch_size=128, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False).astype("float32")
    np.save(cache, X)
print(f"vectors {len(X)}", flush=True)
rng = np.random.default_rng(0); qi = rng.choice(len(X), 1000, replace=False)
Q = X[qi] + rng.normal(0, 0.02, X[qi].shape).astype("float32"); Q /= np.linalg.norm(Q, axis=1, keepdims=True)
flat = faiss.IndexFlatIP(1024); flat.add(X); _, G = flat.search(Q, 10)
def recall(I): return np.mean([len(set(I[r]) & set(G[r]))/10 for r in range(len(Q))])
d, nlist = 1024, 1024
train = X[np.arange(0, len(X), max(1, len(X)//(nlist*64)))[:nlist*64]]
def run(name, factory, bytes_per_vec):
    ix = faiss.index_factory(d, factory, faiss.METRIC_INNER_PRODUCT)
    t0=time.time(); ix.train(train); ix.add(X); tb=time.time()-t0
    row=[]
    for nprobe in (32, 64, 128):
        faiss.ParameterSpace().set_index_parameter(ix, "nprobe", nprobe)
        t0=time.time(); _, I = ix.search(Q, 10); ms=(time.time()-t0)*1000/len(Q)
        row.append(f"np{nprobe}: {100*recall(I):5.1f}% ({ms:.2f} ms/q)")
    gb = bytes_per_vec * 9.6e6 / 1e9
    print(f"{name:22s} {bytes_per_vec:5d} B/vec  EN@9.6M≈{gb:5.1f} GB | " + " | ".join(row) + f" | build {tb:.0f}s", flush=True)
run("IVF,PQ64 (current)", f"IVF{nlist},PQ64x8", 64)
run("OPQ64,IVF,PQ64",      f"OPQ64,IVF{nlist},PQ64x8", 64)
run("OPQ128,IVF,PQ128",    f"OPQ128,IVF{nlist},PQ128x8", 128)
run("IVF,PQ256",           f"IVF{nlist},PQ256x8", 256)
run("OPQ256,IVF,PQ256",    f"OPQ256,IVF{nlist},PQ256x8", 256)
run("IVF,SQ4",             f"IVF{nlist},SQ4", 512)
run("IVF,SQ8",             f"IVF{nlist},SQ8", 1024)
run("IVF,SQfp16",          f"IVF{nlist},SQfp16", 2048)
