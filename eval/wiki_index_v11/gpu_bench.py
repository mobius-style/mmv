import os, sys, gzip, json, time
os.environ["TOKENIZERS_PARALLELISM"]="false"
from sentence_transformers import SentenceTransformer
texts=[]
with gzip.open("/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_ja_me5/wiki_chunks.jsonl.gz","rt",encoding="utf-8") as f:
    for i,l in enumerate(f):
        if i>=6000: break
        texts.append("passage: "+json.loads(l)["text"][:1000])
def main():
    mode=sys.argv[1]
    if mode=="pool":
        import torch
        kw={"model_kwargs":{"torch_dtype":torch.float16}} if os.environ.get("FP16") else {}
        m=SentenceTransformer("intfloat/multilingual-e5-large", device="cuda:0", **kw); pool=m.start_multi_process_pool(target_devices=["cuda:0","cuda:1"])
        m.encode(texts[:500], batch_size=128, pool=pool)   # warm-up
        t0=time.time(); m.encode(texts, batch_size=128, pool=pool); dt=time.time()-t0; m.stop_multi_process_pool(pool)
    else:
        import torch
        kw={"model_kwargs":{"torch_dtype":torch.float16}} if os.environ.get("FP16") else {}
        m=SentenceTransformer("intfloat/multilingual-e5-large", device=mode, **kw)
        m.encode(texts[:500], batch_size=128)
        t0=time.time(); m.encode(texts, batch_size=128, show_progress_bar=False); dt=time.time()-t0
    print(f"{mode:8s} {len(texts)/dt:7.1f} chunks/s  ({dt:.1f}s for {len(texts)})")

if __name__ == "__main__":
    main()
