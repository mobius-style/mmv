#!/usr/bin/env python3
"""Second attempt: write the clipped range INTO the existing trained vector (the previous attempt
replaced the SWIG object, which silently produced a worse index). Verify the write round-trips."""
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
    tr=faiss.vector_to_array(ix.sq.trained)
    note=f"trained={len(tr)} floats"
    if clip is not None:
        lo=np.quantile(train,clip[0],axis=0).astype("float32"); hi=np.quantile(train,clip[1],axis=0).astype("float32")
        new=np.concatenate([lo,(hi-lo)]).astype("float32")
        assert len(new)==len(tr), (len(new),len(tr))
        faiss.copy_array_to_vector(new, ix.sq.trained)          # write in place
        back=faiss.vector_to_array(ix.sq.trained)
        note += f" | write round-trip {'OK' if np.allclose(back,new) else 'FAILED'}"
        note += f" | range shrink {float(np.mean((hi-lo)/(tr[1024:]+1e-9))):.3f}x"
    ix.add(X); ix.nprobe=128; _,I=ix.search(Q,10); r1,mrr=qa(I)
    print(f"  {name:36s} fidelity {fid(I):5.1f}%  recall@1 {r1:5.1f}  MRR {mrr:5.1f}   [{note}]", flush=True)
print(f"IVF{nlist},SQ4, {len(X):,} vectors, nprobe 128")
run("stock (RS_minmax) = shipped")
run("RS_optim", rangestat=faiss.ScalarQuantizer.RS_optim)
run("clip 0.1-99.9 pct (in-place write)", clip=(0.001,0.999))
run("clip 0.5-99.5 pct (in-place write)", clip=(0.005,0.995))
