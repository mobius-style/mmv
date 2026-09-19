#!/usr/bin/env python3
"""Do the two chunkings fit inside ME5-large's 512-token window?"""
import gzip, json, random, collections
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
LIMIT = 512
SRC = {
 "EN clean (boundary, published)": "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/Wiki/wiki_chunks_clean.jsonl.gz",
 "JA 1536-slice (published)":      "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_ja_me5/wiki_chunks.jsonl.gz",
 "ZH 1536-slice (published)":      "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_zh_me5/wiki_chunks.jsonl.gz",
}
for name, path in SRC.items():
    texts=[]; rnd=random.Random(11)
    with gzip.open(path,"rt",encoding="utf-8") as f:
        for i,l in enumerate(f):
            if i>200000: break
            if i%17==0: texts.append(json.loads(l)["text"])
    texts=rnd.sample(texts, min(8000,len(texts)))
    n=[len(tok("passage: "+t, add_special_tokens=True)["input_ids"]) for t in texts]
    n.sort(); over=sum(1 for x in n if x>LIMIT)
    # how much text is lost on the truncated ones
    lost=[(x-LIMIT)/x for x in n if x>LIMIT]
    print(f"{name:34s} n={len(n)} tok p50={n[len(n)//2]:4d} p95={n[len(n)*19//20]:5d} max={n[-1]:5d}"
          f"  >512: {over/len(n)*100:5.1f}%  mean lost on those: {100*sum(lost)/len(lost) if lost else 0:4.1f}%", flush=True)
