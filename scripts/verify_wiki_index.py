#!/usr/bin/env python3
"""Acceptance check for a freshly built ME5 wiki index: alignment, token budget, smoke search."""
import sys, json, gzip, pathlib, random, os
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
out, lang = pathlib.Path(sys.argv[1]), sys.argv[2]
mf = json.loads((out/"wiki_manifest.json").read_text())
print("manifest:", json.dumps({k:v for k,v in mf.items() if k!='built_at'}, ensure_ascii=False))
import faiss, numpy as np
ix = faiss.read_index(str(out/"wiki_index_ivfpq_me5.faiss"))
print("faiss ntotal", ix.ntotal, "d", ix.d)
rows = []
with gzip.open(out/"wiki_chunks.jsonl.gz","rt",encoding="utf-8") as f:
    for i,l in enumerate(f): rows.append(json.loads(l))
aligned = len(rows) == ix.ntotal
print("chunk lines", len(rows), "ALIGNED" if aligned else "*** MISALIGNED ***")
FAIL = []
if not aligned: FAIL.append(f"row count {len(rows)} != ntotal {ix.ntotal}")
if mf.get("chunk_count") != ix.ntotal: FAIL.append(f"manifest chunk_count {mf.get('chunk_count')} != ntotal {ix.ntotal}")
if mf.get("index_kind") != "IVF,SQ4": FAIL.append(f"index_kind {mf.get('index_kind')!r} is not IVF,SQ4")
import os
offp = out/"line_offsets.npy"
if offp.exists():
    import numpy as _np
    if len(_np.load(offp)) != ix.ntotal: FAIL.append("line_offsets.npy length != ntotal")
else: FAIL.append("line_offsets.npy missing")
uniq = len({r["chunk_id"] for r in rows}) == len(rows)
print("unique chunk_id", uniq)
if not uniq: FAIL.append("chunk_id collision in the shipped store")
from transformers import AutoTokenizer
tk = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
smp = random.Random(5).sample(rows, min(4000, len(rows)))
n = sorted(len(x) for x in tk(["passage: "+r["text"] for r in smp], add_special_tokens=True)["input_ids"])
over = 100*sum(1 for x in n if x>512)/len(n)
print(f"tokens p50={n[len(n)//2]} p95={n[len(n)*19//20]} max={n[-1]}  >512: {over:.2f}%")
if over > 0.0: FAIL.append(f"{over:.2f}% of sampled chunks exceed the 512-token window")
from sentence_transformers import SentenceTransformer
m = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda")
Q = {"en":["query: What causes auroras?","query: 量子力学の基本原理"],
     "ja":["query: 量子力学の基本原理","query: What causes auroras?"],
     "zh":["query: 量子力学的基本原理","query: What causes auroras?"]}[lang]
v = np.asarray(m.encode(Q, normalize_embeddings=True), dtype="float32"); ix.nprobe = 32
D, I = ix.search(v, 5)
for q, d, idx in zip(Q, D, I):
    print(" ", q, "->", [(rows[j]["title"][:40], round(float(s),3)) for s, j in zip(d, idx) if j >= 0])

if FAIL:
    print("\n*** ACCEPTANCE FAILED ***")
    for f in FAIL: print("  -", f)
    raise SystemExit(1)
print("\nACCEPTANCE PASSED")
