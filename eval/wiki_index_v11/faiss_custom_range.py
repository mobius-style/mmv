#!/usr/bin/env python3
"""Ship the clipping gain inside a stock FAISS index: train IVF,SQ4 normally, then overwrite the
per-dimension (vmin, vdiff) range with percentile-clipped values. The file format is unchanged —
any FAISS reader opens it — only the trained range differs."""
import json, time, numpy as np, faiss
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
def build(name, clip=None, rangestat=None):
    q=faiss.IndexFlatIP(1024)
    ix=faiss.IndexIVFScalarQuantizer(q,1024,nlist,faiss.ScalarQuantizer.QT_4bit,faiss.METRIC_INNER_PRODUCT)
    if rangestat is not None: ix.sq.rangestat=rangestat
    ix.train(train)
    if clip is not None:
        lo,hi=np.quantile(train,clip[0],axis=0).astype("float32"),np.quantile(train,clip[1],axis=0).astype("float32")
        tr=faiss.vector_to_array(ix.sq.trained).copy()             # layout: [vmin_0..vmin_d-1, vdiff_0..vdiff_d-1]
        tr[:1024]=lo; tr[1024:]=(hi-lo)
        ix.sq.trained=faiss.FloatVector(); faiss.copy_array_to_vector(tr.astype("float32"), ix.sq.trained)
    ix.add(X); ix.nprobe=128
    _,I=ix.search(Q,10); r1,mrr=qa(I)
    print(f"  {name:42s} top-10 fidelity {fid(I):5.1f}%   QA recall@1 {r1:5.1f}  MRR {mrr:5.1f}", flush=True)
    return ix
print(f"IVF{nlist},SQ4 on {len(X):,} vectors, nprobe 128", flush=True)
build("stock RS_minmax (what we shipped)")
build("stock RS_optim")
build("range = 0.1-99.9 percentile", clip=(0.001,0.999))
build("range = 0.5-99.5 percentile", clip=(0.005,0.995))
build("range = 1-99 percentile", clip=(0.01,0.99))
