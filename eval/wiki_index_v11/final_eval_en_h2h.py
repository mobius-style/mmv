#!/usr/bin/env python3
"""English head-to-head: the published ME5 store/index (2026-04) against v11b.

Questions come from the OLD store's own chunk text (build_en_control.py), so the old artifact is
scored on questions drawn from exactly what it encoded. Gold articles are present in both stores by
construction. Whole corpus on both sides, nprobe 128 (and 32 for reference).
"""
import json, gzip, pathlib, numpy as np, faiss, torch, os
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
from sentence_transformers import SentenceTransformer

OLD_DIR = pathlib.Path("/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/Wiki")
NEW_DIR = pathlib.Path("/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_en_me5_2026-06_v11b")
OLD_CHUNKS, NEW_CHUNKS = OLD_DIR/"wiki_chunks_clean.jsonl.gz", NEW_DIR/"wiki_chunks.jsonl.gz"
OLD_INDEX, NEW_INDEX  = OLD_DIR/"wiki_index_ivfpq_me5.faiss", NEW_DIR/"wiki_index_ivfpq_me5.faiss"

def titles_of(p):
    out=[]
    with gzip.open(p,"rt",encoding="utf-8") as f:
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

saved=json.load(open("questions_en_oldstore.json"))
keep=[i for i,q in enumerate(saved["questions"]) if len(q)>10]
gold=[saved["titles"][i] for i in keep]
qs=[saved["questions"][i] for i in keep]
print(f"en control set: {len(keep)} questions generated from the OLD store's own text", flush=True)

m = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda:0",
                        model_kwargs={"torch_dtype": torch.float16})
Q = m.encode([f"query: {q}" for q in qs], batch_size=64, normalize_embeddings=True,
             convert_to_numpy=True).astype("float32")
del m; torch.cuda.empty_cache()

for label, cpath, ipath in (("old (published 2026-04)", OLD_CHUNKS, OLD_INDEX),
                            ("new (v11b)",              NEW_CHUNKS, NEW_INDEX)):
    rows = titles_of(cpath)
    ix = faiss.read_index(str(ipath), faiss.IO_FLAG_MMAP)
    print(f"\n{label}: {len(rows):,} chunks | index {type(ix).__name__} ntotal={ix.ntotal:,}", flush=True)
    for npb in (32,128):
        ix.nprobe=npb; _,I = ix.search(Q,10); a,b,c = score(I, rows, gold)
        print(f"    nprobe={npb:3d}  recall@1={a:5.1f} recall@5={b:5.1f} MRR={c:5.1f}", flush=True)
    del ix, rows

# title-leak diagnostic, same as fix_verification.log section E
leak=sum(1 for g,q in zip(gold,qs) if g.lower() in q.lower())
print(f"\ngold title appears verbatim in the question: {leak}/{len(gold)} ({100*leak/len(gold):.1f} %)", flush=True)
noq=sum(1 for q in qs if "?" not in q)
print(f"items with no question mark: {noq}/{len(qs)}", flush=True)
