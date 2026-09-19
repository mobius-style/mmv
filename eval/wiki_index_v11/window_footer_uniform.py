#!/usr/bin/env python3
"""Footer contamination and over-window rate on the PUBLISHED stores.
Full-file count for the footer; a uniform stride sample (not head-of-file) for tokens."""
import gzip, json, re, os, sys
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
W = "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/"
SRC = {"EN published (clean, 2026-04)": (W+"Wiki/wiki_chunks_clean.jsonl.gz", 5458524),
       "JA published (2026-06 build)":  (W+"data/wiki_ja_me5/wiki_chunks.jsonl.gz", 1550503),
       "ZH published (2026-06 build)":  (W+"data/wiki_zh_me5/wiki_chunks.jsonl.gz", 1638042)}
pat = re.compile(r"issued from Wikipedia")
N = 8000
for name,(p,total) in SRC.items():
    stride = max(1, total//N)
    hit=n=0; sample=[]; chars=0
    with gzip.open(p,"rt",encoding="utf-8") as f:
        for i,l in enumerate(f):
            d=json.loads(l); n+=1; chars+=len(d["text"])
            if pat.search(d["text"]): hit+=1
            if i % stride == 0 and len(sample) < N: sample.append(d["text"])
    ids = tok(["passage: "+t for t in sample], add_special_tokens=True)["input_ids"]
    ntok = sorted(len(x) for x in ids)
    over = [x for x in ntok if x > 512]
    lost = sum((x-512)/x for x in over)/len(over) if over else 0.0
    cpt = sum(len(t) for t in sample)/sum(len(x) for x in ids)
    print(f"{name}\n  chunks {n:,} | footer {hit:,} ({100*hit/n:.1f}%) | mean chunk {chars//n} chars\n"
          f"  uniform sample {len(ntok)} (stride {stride}): tokens p50={ntok[len(ntok)//2]} p95={ntok[len(ntok)*19//20]} "
          f"max={ntok[-1]} | >512: {100*len(over)/len(ntok):.1f}% | mean tokens lost on those: {100*lost:.1f}% | "
          f"chars/token {cpt:.2f}", flush=True)
