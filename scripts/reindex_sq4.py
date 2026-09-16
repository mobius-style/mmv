#!/usr/bin/env python3
"""Re-index a v11 build from its stored fp16 vectors — no re-embedding.

IVF,SQ4 with a residual-quantile range (2026-09-15). FAISS trains the scalar quantiser's range as
the min/max of the residuals, which a few outliers stretch; clipping it to the 0.1-99.9 percentile
of the residual distribution costs nothing (same 4 bits, same LUT decode, same file format) and
measured, on 205,789 ja vectors / 303 questions at nprobe 128:
    stock min/max range : top-10 fidelity 81.6%  recall@1 62.4  MRR 66.2
    residual-quantile   : top-10 fidelity 85.2%  recall@1 63.4  MRR 66.9
The idea is the one transferable piece of neural texture compression: adapt the code allocation to
the data distribution. Learned levels (Lloyd-Max) and a decorrelating rotation were also measured
and did not beat it on these vectors.
"""
import sys, json, glob, time, pathlib
import numpy as np, faiss
out = pathlib.Path(sys.argv[1]); kind = sys.argv[2] if len(sys.argv) > 2 else "SQ4"
mf = json.loads((out/"wiki_manifest.json").read_text())
n = mf["chunk_count"]; parts = sorted(glob.glob(str(out/"emb_part*.f16")))
print(f"{out.name}: {n:,} chunks, {len(parts)} embedding parts", flush=True)
nlist = min(4096, n // 10)
QT = {"SQ4": faiss.ScalarQuantizer.QT_4bit, "SQ8": faiss.ScalarQuantizer.QT_8bit}[kind]
index = faiss.IndexIVFScalarQuantizer(faiss.IndexFlatIP(1024), 1024, nlist, QT, faiss.METRIC_INNER_PRODUCT)
CLIP = (0.001, 0.999)   # residual-quantile range; see the module docstring
# train on a uniform stride over the whole corpus
need = nlist * 64; rows_total = sum(pathlib.Path(p).stat().st_size // (1024*2) for p in parts)
stride = max(1, rows_total // need); train = []
t0 = time.time()
for p in parts:
    a = np.fromfile(p, dtype=np.float16).reshape(-1, 1024)
    train.append(a[::stride]); del a
train = np.concatenate(train)[:need].astype("float32")
print(f"  training on {len(train):,} vectors (stride {stride})", flush=True)
index.train(train)
# Re-fit the quantiser range on the residual distribution, clipped to CLIP.
assert index.by_residual, "this index encodes residuals; the range must be fitted on residuals"
_, assign = index.quantizer.search(train, 1)
cent = faiss.rev_swig_ptr(faiss.downcast_index(index.quantizer).get_xb(), nlist * 1024).reshape(nlist, 1024)
resid = train - cent[assign[:, 0]]
lo = np.quantile(resid, CLIP[0], axis=0).astype("float32")
hi = np.quantile(resid, CLIP[1], axis=0).astype("float32")
before = faiss.vector_to_array(index.sq.trained).copy()
faiss.copy_array_to_vector(np.concatenate([lo, hi - lo]).astype("float32"), index.sq.trained)
after = faiss.vector_to_array(index.sq.trained)
assert np.allclose(after[:1024], lo) and np.allclose(after[1024:], hi - lo), "range write failed"
print(f"  range refit on residuals: mean width {float(np.mean((hi-lo)/(before[1024:]+1e-9))):.3f}x of min/max", flush=True)
del train, resid
added = 0
for p in parts:
    a = np.fromfile(p, dtype=np.float16).reshape(-1, 1024).astype("float32")
    for i in range(0, len(a), 500_000):
        index.add(a[i:i+500_000]); added += len(a[i:i+500_000])
    del a
    print(f"  added {added:,}/{rows_total:,}", flush=True)
assert index.ntotal == n, f"ntotal {index.ntotal} != chunks {n}"
dst = out/"wiki_index_ivfpq_me5.faiss"
faiss.write_index(index, str(dst))
size = dst.stat().st_size
mf.update({"index_kind": f"IVF,{kind}", "quantizer": {"SQ4":"QT_4bit","SQ8":"QT_8bit"}[kind],
           "bytes_per_vector": size/n, "index_size_gb": round(size/1e9, 3), "recommended_nprobe": 128,
           "reindexed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "range_fit": f"residual quantiles {CLIP[0]}-{CLIP[1]} (measured +3.6 pt top-10 fidelity, +0.7 MRR over FAISS min/max on 205,789 ja vectors)",
           "reindex_note": "rebuilt from the stored fp16 vectors; no re-embedding"})
(out/"wiki_manifest.json").write_text(json.dumps(mf, ensure_ascii=False, indent=2))
print(f"  wrote {size/1e9:.2f} GB ({size/n:.0f} B/vector) in {time.time()-t0:.0f}s", flush=True)
