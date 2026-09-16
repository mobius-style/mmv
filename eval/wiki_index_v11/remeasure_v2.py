#!/usr/bin/env python3
"""Corrections to two measurements the adversarial review showed were wrong.

A. footer string length — misc_measure.py §A reported len() of a hard-coded string that does not
   occur in any store. Measure the real footer as it appears in the published artifacts.
B. mean pairwise cosine — resource_and_coverage.py §C drew 2000+2000 indices from the FIRST 4,000
   vectors of embedding part 0 and allowed self-pairs. Draw disjoint random pairs across the whole
   shipped vector set, excluding self-pairs.
"""
import gzip, json, os, re, numpy as np
OLD = {"ja": "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_ja_me5",
       "zh": "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_zh_me5"}
NEW = {"en": "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_en_me5_2026-06_v11b",
       "ja": "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_ja_me5_2026-06_v11b",
       "zh": "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_zh_me5_2026-05_v11b"}
out=[]
def p(s):
    print(s, flush=True); out.append(s)

p("== A. the licence footer as it actually appears in the published stores")
pat = re.compile(r"This article is issued from Wikipedia.*?(?:media files\.|\Z)", re.S)
for lang in ("ja","zh"):
    f=os.path.join(OLD[lang],"wiki_chunks.jsonl.gz")
    seen={}
    with gzip.open(f,"rt",encoding="utf-8") as fh:
        for i,ln in enumerate(fh):
            if i>=20000: break
            m=pat.search(json.loads(ln)["text"])
            if m: seen[m.group(0)]=seen.get(m.group(0),0)+1
    if not seen:
        p(f"   {lang}: no match in the first 20,000 chunks"); continue
    top=sorted(seen.items(), key=lambda kv:-kv[1])
    s,n=top[0]
    p(f"   {lang}: {len(seen)} distinct footer string(s) in the first 20,000 chunks; "
      f"most common seen {n:,} times, {len(s)} characters")
    p(f"      {s!r}")

p("== B. mean pairwise cosine, disjoint random pairs across the whole shipped vector set")
rng=np.random.default_rng(11)
NPAIR=20000
for lang in ("en","ja","zh"):
    d=NEW[lang]
    parts=sorted(f for f in os.listdir(d) if f.startswith("emb_part") and f.endswith(".f16"))
    sizes=[os.path.getsize(os.path.join(d,f))//(1024*2) for f in parts]
    total=sum(sizes)
    idx=rng.choice(total, size=2*NPAIR, replace=False)
    a_idx, b_idx = idx[:NPAIR], idx[NPAIR:]
    def fetch(ids):
        v=np.empty((len(ids),1024), dtype=np.float32)
        order=np.argsort(ids); ids_s=ids[order]
        base=0; pi=0
        fh=open(os.path.join(d,parts[0]),"rb")
        for k,gid in enumerate(ids_s):
            while gid>=base+sizes[pi]:
                base+=sizes[pi]; pi+=1; fh.close()
                fh=open(os.path.join(d,parts[pi]),"rb")
            fh.seek((gid-base)*1024*2)
            v[order[k]]=np.frombuffer(fh.read(1024*2), dtype=np.float16).astype(np.float32)
        fh.close(); return v
    A=fetch(a_idx); B=fetch(b_idx)
    A/=np.linalg.norm(A,axis=1,keepdims=True); B/=np.linalg.norm(B,axis=1,keepdims=True)
    cos=np.sum(A*B,axis=1)
    p(f"   {lang}: {NPAIR:,} disjoint random pairs from all {total:,} shipped vectors — "
      f"mean cosine {cos.mean():.4f}, sd {cos.std():.4f}, p5 {np.percentile(cos,5):.4f}, "
      f"p95 {np.percentile(cos,95):.4f}")
open("remeasure_v2.log","w").write("\n".join(out)+"\n")
