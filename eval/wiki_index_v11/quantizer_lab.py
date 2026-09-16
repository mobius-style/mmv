#!/usr/bin/env python3
"""Does a learned/adapted 4-bit quantiser beat FAISS's uniform SQ4 at identical size and decode cost?

Borrowed framing from neural texture compression: the win there comes from adapting the code
allocation to the data distribution (and decorrelating channels first), not from the network per se.
Both of those have zero-cost analogues here — non-uniform per-dimension levels (a 16-entry LUT,
still SIMD-friendly) and a random rotation before quantising (one matmul at query time).

Everything is measured two ways: rank fidelity against exact search, and the QA benchmark.
"""
import json, time, numpy as np, faiss
W = "/home/happy/.codex/bench/wiki_forensics/"
X = np.load(W+"e2e_ja_100000_emb.npy")            # 205,789 x 1024, unit norm
Q = np.load(W+"e2e_ja_100000_q.npy")
own = np.load(W+"e2e_ja_100000_own.npy")
saved = json.load(open(W+"questions_ja.json")); questions = saved["questions"]
keep = [i for i,q in enumerate(questions) if len(q) > 10]
print(f"{len(X):,} vectors, {len(Q)} queries", flush=True)

flat = faiss.IndexFlatIP(1024); flat.add(X); _, G = flat.search(Q, 10)
def rank_fidelity(I): return 100*np.mean([len(set(I[r]) & set(G[r]))/10 for r in range(len(Q))])
def qa(I):
    r1 = np.mean([own[I[r,0]] == keep[r] for r in range(len(keep))])
    rr = [(1.0/(np.where(own[I[r]]==keep[r])[0][0]+1)) if (own[I[r]]==keep[r]).any() else 0.0 for r in range(len(keep))]
    return 100*float(r1), 100*float(np.mean(rr))

def uniform_levels(A, bits=4, lo=None, hi=None):
    n = 1 << bits
    mn = A.min(0) if lo is None else np.quantile(A, lo, axis=0)
    mx = A.max(0) if hi is None else np.quantile(A, hi, axis=0)
    step = (mx - mn) / (n - 1)
    return mn[None,:] + np.arange(n)[:,None] * step[None,:]      # (n, d)

def lloyd_levels(A, bits=4, iters=6, sample=60000, rng=np.random.default_rng(0)):
    n = 1 << bits
    S = A[rng.choice(len(A), min(sample, len(A)), replace=False)]
    qs = (np.arange(n) + 0.5) / n
    lev = np.quantile(S, qs, axis=0)                              # (n, d) init
    for _ in range(iters):
        bounds = (lev[1:] + lev[:-1]) / 2                          # (n-1, d)
        new = np.empty_like(lev)
        for d in range(A.shape[1]):
            idx = np.searchsorted(bounds[:, d], S[:, d])
            sums = np.bincount(idx, weights=S[:, d], minlength=n)
            cnt  = np.bincount(idx, minlength=n)
            new[:, d] = np.where(cnt > 0, sums / np.maximum(cnt, 1), lev[:, d])
        lev = np.sort(new, axis=0)
    return lev

def quantise(A, lev, block=20000):
    """Encode to the nearest level per dimension and return the reconstruction."""
    out = np.empty_like(A)
    bounds = (lev[1:] + lev[:-1]) / 2
    for s in range(0, len(A), block):
        B = A[s:s+block]; R = np.empty_like(B)
        for d in range(A.shape[1]):
            idx = np.searchsorted(bounds[:, d], B[:, d])
            R[:, d] = lev[idx, d]
        out[s:s+block] = R
    return out

def evaluate(name, Xq, Qq, bytes_per_vec):
    ix = faiss.IndexFlatIP(1024); ix.add(np.ascontiguousarray(Xq, dtype="float32"))
    _, I = ix.search(np.ascontiguousarray(Qq, dtype="float32"), 10)
    r1, mrr = qa(I)
    print(f"  {name:38s} {bytes_per_vec:5d} B/vec  top-10 fidelity {rank_fidelity(I):5.1f}%   QA recall@1 {r1:5.1f}  MRR {mrr:5.1f}", flush=True)

t0 = time.time()
print("baselines:")
evaluate("exact (fp32)", X, Q, 4096)
lev8 = uniform_levels(X, 8); evaluate("SQ8 uniform min/max (reference)", quantise(X, lev8), Q, 1024)

print("4-bit variants (all 512 B/vector, all LUT-decodable):", flush=True)
lev4 = uniform_levels(X, 4); evaluate("SQ4 uniform min/max (shipped)", quantise(X, lev4), Q, 512)
lev4c = uniform_levels(X, 4, lo=0.001, hi=0.999); evaluate("SQ4 uniform, 0.1-99.9 pct clip", quantise(X, lev4c), Q, 512)
levL = lloyd_levels(X, 4); evaluate("SQ4 Lloyd-Max levels", quantise(X, levL), Q, 512)

rng = np.random.default_rng(7)
R, _ = np.linalg.qr(rng.standard_normal((1024, 1024)))
XR = (X @ R).astype("float32"); QR = (Q @ R).astype("float32")
levR = uniform_levels(XR, 4); evaluate("SQ4 uniform after random rotation", quantise(XR, levR), QR, 512)
levRL = lloyd_levels(XR, 4);  evaluate("SQ4 Lloyd-Max after random rotation", quantise(XR, levRL), QR, 512)
print(f"({time.time()-t0:.0f}s)")
