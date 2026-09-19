import gzip, json, time, re, os
import numpy as np
BASE="/home/happy/.codex/bench/wiki_publish"
out=[]
def p(s):
    print(s, flush=True); out.append(s)

p("== A. footer boilerplate length (the string the extractor strips)")
en_footer=("This article is issued from Wikipedia. The text is licensed under Creative Commons "
           "- Attribution - Sharealike. Additional terms may apply for the media files.")
p(f"   en footer: {len(en_footer)} characters")

p("== B. deep read of the shipped chunk store (seek to the 99th-percentile line)")
try:
    import indexed_gzip
except ImportError:
    indexed_gzip=None
for lang in ("ja","en"):
    f=os.path.join(BASE,lang,"wiki_chunks.jsonl.gz")
    if not os.path.exists(f):
        p(f"   {lang}: missing {f}"); continue
    size=os.path.getsize(f)
    arr=np.load(os.path.join(BASE,lang,"line_offsets.npy"), mmap_mode="r")
    target=int(arr[int(len(arr)*0.99)])
    t=time.time()
    with gzip.open(f,"rb") as fh:
        fh.seek(target); fh.readline()
    naive=time.time()-t
    fast=float("nan")
    gz=os.path.join(BASE,lang,"line_offsets.gzidx")
    if indexed_gzip is not None and os.path.exists(gz):
        t=time.time()
        fh=indexed_gzip.IndexedGzipFile(f, index_file=gz)
        fh.seek(target); fh.readline(); fh.close()
        fast=time.time()-t
    p(f"   {lang}: {size/1e9:.2f} GB compressed, {len(arr):,} lines — "
      f"python gzip {naive:.1f} s | indexed_gzip + .gzidx {fast:.2f} s")

p("== C. 60-char prose/facts rule: lines that look like infobox rows but are ≥60 chars")
pat=re.compile(r'^[^\s:：][^:：]{0,40}[:：]\s?\S')
for lang in ("en","ja","zh"):
    f=os.path.join(BASE,lang,"wiki_chunks.jsonl.gz")
    if not os.path.exists(f): continue
    long_lines=0; hit=0; nch=0
    with gzip.open(f,"rt",encoding="utf-8") as fh:
        for i,ln in enumerate(fh):
            if i>=300000: break
            nch+=1
            body=json.loads(ln)["text"].split("\n")[1:]
            for seg in body:
                seg=seg.strip()
                if len(seg)<60: continue
                long_lines+=1
                if pat.match(seg): hit+=1
    p(f"   {lang}: {hit:,} of {long_lines:,} lines ≥60 chars ({100*hit/max(long_lines,1):.1f} %) "
      f"still read as 'key: value' — first {nch:,} shipped chunks")

p("== D. 48-bit chunk_id collision probability, analytic (birthday bound)")
for lang,n in (("en",15648632),("ja",3009820),("zh",3367718)):
    for bits in (48,80):
        lam=n*n/(2*2**bits)
        p(f"   {lang} n={n:,} at {bits} bits: expected collisions {lam:.3g}, "
          f"P(at least one) {1-np.exp(-lam):.3%}")
open("misc_measure.log","w").write("\n".join(out)+"\n")
