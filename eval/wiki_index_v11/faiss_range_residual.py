#!/usr/bin/env python3
"""Why the clipped range made FAISS worse: IndexIVFScalarQuantizer encodes the RESIDUAL from the
coarse centroid, so the trained range describes residuals — my quantiles were taken over raw
vectors. Redo it on residuals, and compare against the stock options."""
import json, numpy as np, faiss
W="/home/happy/.codex/bench/wiki_forensics/"
X=np.load(W+"e2e_ja_100000_emb.npy"); Q=np.load(W+"e2e_ja_100000_q.npy"); own=np.load(W+"e2e_ja_100000_own.npy")
saved=json.load(open(W+"questions_ja.json")); keep=[i for i,q in enumerate(saved["questions"]) if len(q)>10]
flat=faiss.IndexFlatIP(1024); flat.add(X); _,G=flat.search(Q,10)
def fid(I): return 100*np.mean([len(set(I[r])&set(G[r]))/10 for r in range(len(Q))])
def qa(I):
    r1=np.mean([own[I[r,0]]==keep[r] for r in range(len(keep))])
    rr=[(1.0/(np.where(own[I[r]]==keep[r])[0][0]+1)) if (own[I[r]]==keep[r]).any() else 0.0 for r in range(len(keep))]
    return 100*float(r1),100*float(np.mean(rr))
nlist=4096; train=X[np.arange(0,len(X),max(1,len(X)//(nlist*40)))[:nlist*40]]
def run(name, clip=None, rangestat=None):
    ix=faiss.IndexIVFScalarQuantizer(faiss.IndexFlatIP(1024),1024,nlist,
        faiss.ScalarQuantizer.QT_4bit,faiss.METRIC_INNER_PRODUCT)
    if rangestat is not None: ix.sq.rangestat=rangestat
    ix.train(train)
    extra=f"by_residual={bool(ix.by_residual)}"
    if clip is not None:
        base = train
        if ix.by_residual:
            _, A = ix.quantizer.search(train, 1)
            cent = faiss.vector_to_array(ix.quantizer.xb).reshape(-1,1024) if hasattr(ix.quantizer,'xb') else None
            cent = faiss.rev_swig_ptr(faiss.downcast_index(ix.quantizer).get_xb(), nlist*1024).reshape(nlist,1024)
            base = train - cent[A[:,0]]
        lo=np.quantile(base,clip[0],axis=0).astype("float32"); hi=np.quantile(base,clip[1],axis=0).astype("float32")
        faiss.copy_array_to_vector(np.concatenate([lo,hi-lo]).astype("float32"), ix.sq.trained)
        extra += f" | clip on {'residuals' if ix.by_residual else 'raw'}"
    ix.add(X); ix.nprobe=128; _,I=ix.search(Q,10); r1,mrr=qa(I)
    print(f"  {name:40s} fidelity {fid(I):5.1f}%  recall@1 {r1:5.1f}  MRR {mrr:5.1f}   [{extra}]", flush=True)
print(f"IVF{nlist},SQ4, {len(X):,} vectors, nprobe 128")
run("stock RS_minmax (shipped)")
run("stock RS_optim")
run("clip 0.1-99.9 pct on residuals", clip=(0.001,0.999))
run("clip 1-99 pct on residuals", clip=(0.01,0.99))
