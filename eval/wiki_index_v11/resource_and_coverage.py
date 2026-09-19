#!/usr/bin/env python3
"""Numbers the document asserted without a log. Everything here prints to a file that ships."""
import os, sys, gzip, json, time, importlib.util, numpy as np
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
import torch
from sentence_transformers import SentenceTransformer
W="/home/happy/.codex/bench/wiki_forensics/"
B="/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/"

print("== A. embedding throughput (6,000 ja chunks, batch 128)", flush=True)
texts=[]
with gzip.open(B+"data/wiki_ja_me5_2026-06_v11b/wiki_chunks.jsonl.gz","rt",encoding="utf-8") as f:
    for i,l in enumerate(f):
        if i>=6000: break
        texts.append("passage: "+json.loads(l)["text"])
def bench(dev, fp16, pool=False):
    kw={"model_kwargs":{"torch_dtype":torch.float16}} if fp16 else {}
    m=SentenceTransformer("intfloat/multilingual-e5-large", device="cuda:0" if pool else dev, **kw)
    p=m.start_multi_process_pool(target_devices=["cuda:0","cuda:1"]) if pool else None
    kw2={"pool":p} if pool else {"show_progress_bar":False,"convert_to_numpy":True}
    m.encode(texts[:500], batch_size=128, **kw2)
    t0=time.time(); m.encode(texts, batch_size=128, **kw2); dt=time.time()-t0
    if pool: m.stop_multi_process_pool(p)
    del m; torch.cuda.empty_cache()
    return len(texts)/dt
if __name__ == "__main__":
    r={}
    for name,args in (("GPU0 fp32",("cuda:0",False,False)), ("GPU1 fp32",("cuda:1",False,False)),
                      ("GPU0 fp16",("cuda:0",True,False)), ("both GPUs fp32",(None,False,True)),
                      ("both GPUs fp16",(None,True,True))):
        r[name]=bench(*args); print(f"   {name:16s} {r[name]:7.1f} chunks/s", flush=True)
    print(f"   dual-GPU speed-up (fp32) {r['both GPUs fp32']/r['GPU0 fp32']:.2f}x | fp16 speed-up (GPU0) {r['GPU0 fp16']/r['GPU0 fp32']:.2f}x | combined {r['both GPUs fp16']/r['GPU0 fp32']:.2f}x", flush=True)

    print("== B. fp16 vs fp32 embeddings, same texts (3,000 ja chunks)", flush=True)
    m32=SentenceTransformer("intfloat/multilingual-e5-large", device="cuda:0")
    A=m32.encode(texts[:3000], batch_size=128, normalize_embeddings=True, convert_to_numpy=True); del m32; torch.cuda.empty_cache()
    m16=SentenceTransformer("intfloat/multilingual-e5-large", device="cuda:0", model_kwargs={"torch_dtype":torch.float16})
    C=m16.encode(texts[:3000], batch_size=128, normalize_embeddings=True, convert_to_numpy=True).astype("float32"); del m16; torch.cuda.empty_cache()
    cos=np.sum(A*C,axis=1); print(f"   same-text cosine: mean {cos.mean():.6f} min {cos.min():.6f}", flush=True)
    q=A[:300]; G=np.argsort(-(q@A.T),axis=1)[:,:10]; H=np.argsort(-(q@C.T),axis=1)[:,:10]
    print(f"   top-1 agreement {100*np.mean(G[:,0]==H[:,0]):.1f}%  top-10 agreement {100*np.mean([len(set(G[i])&set(H[i]))/10 for i in range(300)]):.1f}%", flush=True)

    print("== C. mean pairwise cosine of shipped chunks (4,000 random pairs per language)", flush=True)
    for lang,d in (("en","wiki_en_me5_2026-06_v11b"),("ja","wiki_ja_me5_2026-06_v11b"),("zh","wiki_zh_me5_2026-05_v11b")):
        import glob
        parts=sorted(glob.glob(B+f"data/{d}/emb_part*.f16"))
        a=np.fromfile(parts[0], dtype=np.float16, count=4000*1024).reshape(-1,1024).astype("float32")
        rng=np.random.default_rng(1); i=rng.choice(len(a),2000,replace=False); j=rng.choice(len(a),2000,replace=False)
        print(f"   {lang}: mean pairwise cosine {float(np.mean(np.sum(a[i]*a[j],axis=1))):.4f}", flush=True)

    print("== D. indexed-article coverage, v11b extractor vs the previous one, 2,000 sampled articles", flush=True)
    import libzim
    spec=importlib.util.spec_from_file_location("bp", B+"build_wiki_index_me5_bplus.py")
    bp=importlib.util.module_from_spec(spec); spec.loader.exec_module(bp)
    import re as _re
    _T=_re.compile(r"<[^>]+>"); _S=_re.compile(r"\s+"); _BL=_re.compile(r"<(script|style)\b[^>]*>.*?</\1>", _re.I|_re.S)
    def old_strip(h): return _S.sub(" ", _T.sub(" ", _BL.sub(" ", h))).strip()
    for lang,z in (("ja","wikipedia_ja_all_mini_2026-06.zim"),("zh","wikipedia_zh_all_mini_2026-05.zim"),("en","wikipedia_en_all_mini_2026-06.zim")):
        ar=libzim.Archive("/home/happy/デスクトップ/mobius_ai/kiwix/"+z)
        step=max(1,ar.entry_count//6000); eid=0; n=0; oldk=0; newk=0
        while n<2000 and eid<ar.entry_count:
            try:
                e=ar._get_entry_by_id(eid)
                if not e.is_redirect and "html" in str(e.get_item().mimetype).lower():
                    raw=bytes(e.get_item().content).decode("utf-8","ignore"); n+=1
                    if len(old_strip(raw))>=80: oldk+=1
                    if len(bp.extract_text(raw))>=bp.MIN_ARTICLE_CHARS: newk+=1
            except Exception: pass
            eid+=step
        print(f"   {lang}: previous rule {100*oldk/n:.1f}% of {n} sampled articles indexed | v11b {100*newk/n:.1f}%", flush=True)
