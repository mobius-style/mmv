#!/usr/bin/env python3
"""Final evaluation of a shipped v11b artifact.
  A. acceptance on the full corpus (nprobe 32 / 128) with the new-extractor question set
  B. head-to-head against the previously published artifact, on BOTH question sets:
       - questions generated from the new extractor's text (favours v11 by construction)
       - questions generated from the OLD extractor's text (favours the old artifact if anything)
  C. decomposition: how much of the gap is the index type, and how much is chunk multiplicity
Usage: final_eval.py <lang> <new_dir> [old_dir]
"""
import sys, os, json, gzip, pathlib, numpy as np, faiss, torch
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
lang, new_dir = sys.argv[1], pathlib.Path(sys.argv[2])
old_dir = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else None
W = "/home/happy/.codex/bench/wiki_forensics/"
from sentence_transformers import SentenceTransformer
m = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda:0", model_kwargs={"torch_dtype": torch.float16})

def titles_of(d):
    out=[]
    with gzip.open(d/"wiki_chunks.jsonl.gz","rt",encoding="utf-8") as f:
        for line in f: out.append(json.loads(line)["title"])
    return np.array(out, dtype=object)

def score(I, rows, gold):
    h1=np.mean([rows[I[r,0]]==gold[r] for r in range(len(gold))])
    h5=np.mean([gold[r] in list(rows[I[r,:5]]) for r in range(len(gold))])
    rr=[]
    for r in range(len(gold)):
        w=[j for j,t in enumerate(rows[I[r]]) if t==gold[r]]
        rr.append(1.0/(w[0]+1) if w else 0.0)
    return 100*float(h1), 100*float(h5), 100*float(np.mean(rr))

tn = titles_of(new_dir); print(f"{lang}: new store {len(tn):,} chunks", flush=True)
ixn = faiss.read_index(str(new_dir/"wiki_index_ivfpq_me5.faiss"), faiss.IO_FLAG_MMAP)
QSETS = [("questions from the new extractor", f"{W}questions_{lang}.json")]
alt = pathlib.Path(f"{W}questions_{lang}_oldextract.json")
if alt.exists(): QSETS.append(("questions from the OLD extractor (control)", str(alt)))

for qname, qfile in QSETS:
    saved=json.load(open(qfile)); titles, questions = saved["titles"], saved["questions"]
    keep=[i for i,q in enumerate(questions) if len(q)>10]
    Q=m.encode([f"query: {questions[i]}" for i in keep], batch_size=64, normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    gold=[titles[i] for i in keep]
    print(f"\n[A] {qname}: {len(keep)} questions, full corpus", flush=True)
    for np_ in (32,128):
        ixn.nprobe=np_; _,I=ixn.search(Q,10); a,b,c = score(I,tn,gold)
        print(f"    v11b nprobe={np_:3d}  recall@1={a:5.1f} recall@5={b:5.1f} MRR={c:5.1f}", flush=True)
    if old_dir and old_dir.exists():
        to = titles_of(old_dir)
        so, sn = set(to.tolist()), set(tn.tolist())
        both=[r for r,g in enumerate(gold) if g in so and g in sn]
        print(f"[B] head-to-head on {len(both)} questions whose gold article is in both stores", flush=True)
        ixo = faiss.read_index(str(old_dir/"wiki_index_ivfpq_me5.faiss"), faiss.IO_FLAG_MMAP)
        for label, ix, rows in (("old (published)", ixo, to), ("new (v11b)", ixn, tn)):
            ix.nprobe=128; _,I=ix.search(Q[both],10); a,b,c=score(I,rows,[gold[r] for r in both])
            print(f"    {label:18s} nprobe=128  recall@1={a:5.1f} recall@5={b:5.1f} MRR={c:5.1f}", flush=True)
        del ixo
