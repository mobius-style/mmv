#!/usr/bin/env python3
"""Can FAISS produce the clipping gain natively? ScalarQuantizer exposes range statistics:
RS_minmax (default), RS_meanstd, RS_quantiles, RS_optim. Test them in the real IVF,SQ4 path."""
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
nlist=4096   # the shipped partition, not the small-pool one
train=X[np.arange(0,len(X),max(1,len(X)//(nlist*40)))[:nlist*40]]
RS={"RS_minmax (FAISS default)":faiss.ScalarQuantizer.RS_minmax,
    "RS_meanstd":faiss.ScalarQuantizer.RS_meanstd,
    "RS_quantiles":faiss.ScalarQuantizer.RS_quantiles,
    "RS_optim":faiss.ScalarQuantizer.RS_optim}
print(f"IVF{nlist},SQ4 on {len(X):,} vectors — nprobe 128", flush=True)
for name,rs in RS.items():
    q=faiss.IndexFlatIP(1024)
    ix=faiss.IndexIVFScalarQuantizer(q,1024,nlist,faiss.ScalarQuantizer.QT_4bit,faiss.METRIC_INNER_PRODUCT)
    ix.sq.rangestat=rs
    t0=time.time(); ix.train(train); ix.add(X); tb=time.time()-t0
    ix.nprobe=128; _,I=ix.search(Q,10); r1,mrr=qa(I)
    print(f"  {name:28s} top-10 fidelity {fid(I):5.1f}%   QA recall@1 {r1:5.1f}  MRR {mrr:5.1f}   (train+add {tb:.0f}s)", flush=True)
