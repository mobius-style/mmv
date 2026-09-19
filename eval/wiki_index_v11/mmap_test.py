#!/usr/bin/env python3
"""Does mmap keep RAM flat for a big SQ8 index, and what does it cost in latency?"""
import numpy as np, faiss, os, time, psutil, tempfile
X = np.load("/home/happy/.codex/bench/wiki_forensics/e2e_ja_100000_emb.npy")
nlist = max(64, int(4*np.sqrt(len(X))))
ix = faiss.index_factory(1024, f"IVF{nlist},SQ8", faiss.METRIC_INNER_PRODUCT)
ix.train(X[::3][:nlist*40]); ix.add(X)
f = "/home/happy/.codex/bench/wiki_forensics/tmp_sq8.faiss"; faiss.write_index(ix, f)
size = os.path.getsize(f); del ix
Q = X[:200].copy()
proc = psutil.Process()
for flag, label in [(0, "read_index (in RAM)"), (faiss.IO_FLAG_MMAP, "read_index + IO_FLAG_MMAP")]:
    rss0 = proc.memory_info().rss
    ix = faiss.read_index(f, flag); ix.nprobe = 64
    ix.search(Q[:10], 10)                      # warm
    t0 = time.time(); ix.search(Q, 10); ms = (time.time()-t0)*1000/len(Q)
    rss1 = proc.memory_info().rss
    print(f"{label:28s} index {size/1e6:6.1f} MB | RSS +{(rss1-rss0)/1e6:7.1f} MB | {ms:.2f} ms/query", flush=True)
    del ix
os.remove(f)
