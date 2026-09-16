#!/usr/bin/env python3
"""Decisive test: run the QA benchmark THROUGH each index type, not just ANN-fidelity.
Large distractor pool so the ANN partition/quantization loss is realistic."""
import os, sys, json, importlib.util, time, gc
os.environ.setdefault("TOKENIZERS_PARALLELISM","false"); os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF","expandable_segments:True")
import libzim, numpy as np, faiss, torch
spec = importlib.util.spec_from_file_location("bp","/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/build_wiki_index_me5_bplus.py")
bp = importlib.util.module_from_spec(spec); spec.loader.exec_module(bp)
def main():
    lang = sys.argv[1]; NDIST = int(sys.argv[2]) if len(sys.argv)>2 else 100000
    CACHE = f"/home/happy/.codex/bench/wiki_forensics/e2e_{lang}_{NDIST}"
    ZIM = {"ja":"wikipedia_ja_all_mini_2026-06.zim","zh":"wikipedia_zh_all_mini_2026-05.zim","en":"wikipedia_en_all_mini_2026-06.zim"}[lang]
    saved = json.load(open(f"/home/happy/.codex/bench/wiki_forensics/questions_{lang}.json"))
    gold_eids, questions = saved["eids"], saved["questions"]
    keep = [i for i,q in enumerate(questions) if len(q) > 10]

    if os.path.exists(CACHE+"_emb.npy"):
        X = np.load(CACHE+"_emb.npy"); own = np.load(CACHE+"_own.npy"); Q = np.load(CACHE+"_q.npy")
    else:
        tok = bp._tok(); ar = libzim.Archive("/home/happy/デスクトップ/mobius_ai/kiwix/"+ZIM)
        def build_art(eid):
            e = ar._get_entry_by_id(eid)
            return e.title, bp.extract_text(bytes(e.get_item().content).decode("utf-8","ignore"))
        pool = [build_art(e) for e in gold_eids]; gn = len(pool); seen=set(gold_eids)
        step = max(1, ar.entry_count // (NDIST*2)); eid = 7
        while len(pool)-gn < NDIST and eid < ar.entry_count:
            if eid not in seen:
                try:
                    e = ar._get_entry_by_id(eid)
                    if not e.is_redirect and "html" in str(e.get_item().mimetype).lower():
                        raw = bytes(e.get_item().content).decode("utf-8","ignore")
                        if len(raw) > 1500:
                            t = bp.extract_text(raw)
                            if len(t) >= bp.MIN_ARTICLE_CHARS: pool.append((e.title, t))
                except Exception: pass
            eid += step
        print(f"{lang}: {len(pool)} articles ({gn} gold)", flush=True)
        chunks, owner = [], []
        for i,(title,text) in enumerate(pool):
            reserve = len(tok(title, add_special_tokens=False)["input_ids"]) + 4
            prose, facts = bp.split_prose_facts(text)
            for c in bp.chunk_text(prose, tok, reserve) + bp.chunk_text(facts, tok, reserve):
                chunks.append(f"{title}\n{c}"); owner.append(i)
        own = np.array(owner); print(f"  {len(chunks)} chunks ({len(chunks)/len(pool):.2f}/article)", flush=True)
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda:0", model_kwargs={"torch_dtype": torch.float16})
        t0=time.time(); X = m.encode(["passage: "+c for c in chunks], batch_size=128, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False).astype("float32")
        Q = m.encode([f"query: {questions[i]}" for i in keep], batch_size=64, normalize_embeddings=True, convert_to_numpy=True).astype("float32")
        print(f"  embedded in {time.time()-t0:.0f}s (single GPU fp16)", flush=True)
        np.save(CACHE+"_emb.npy", X); np.save(CACHE+"_own.npy", own); np.save(CACHE+"_q.npy", Q)
    print(f"{lang}: {len(X)} vectors, {len(Q)} questions", flush=True)

    def score(I):
        r1 = np.mean([own[I[r,0]] == keep[r] for r in range(len(Q))])
        r5 = np.mean([keep[r] in own[I[r,:5]] for r in range(len(Q))])
        rr = [(1.0/(np.where(own[I[r]]==keep[r])[0][0]+1)) if (own[I[r]]==keep[r]).any() else 0.0 for r in range(len(Q))]
        return 100*r1, 100*r5, 100*float(np.mean(rr))
    flat = faiss.IndexFlatIP(1024); flat.add(X); _, I = flat.search(Q, 10)
    base = score(I); print(f"  {'exact (ceiling)':28s} {'—':>9s}  recall@1={base[0]:5.1f} recall@5={base[1]:5.1f} MRR={base[2]:5.1f}", flush=True)
    nlist = max(64, int(4*np.sqrt(len(X)))); EN = 11_000_000
    train = X[np.arange(0, len(X), max(1, len(X)//(nlist*40)))[:nlist*40]]
    for name, factory, bpv in [("IVF,PQ64 (shipped type)", f"IVF{nlist},PQ64x8", 64),
                               ("OPQ256,IVF,PQ256",        f"OPQ256,IVF{nlist},PQ256x8", 256),
                               ("PCA256,IVF,SQ8",          f"PCA256,IVF{nlist},SQ8", 256),
                               ("PCA512,IVF,SQ8",          f"PCA512,IVF{nlist},SQ8", 512),
                               ("IVF,SQ4",                 f"IVF{nlist},SQ4", 512),
                               ("IVF,SQ8 (v11 default)",   f"IVF{nlist},SQ8", 1024)]:
        ix = faiss.index_factory(1024, factory, faiss.METRIC_INNER_PRODUCT)
        ix.train(train); ix.add(X)
        out=[]
        for npr in (32, 128):
            faiss.ParameterSpace().set_index_parameter(ix, "nprobe", npr)
            t0=time.time(); _, I = ix.search(Q, 10); ms=(time.time()-t0)*1000/len(Q)
            s = score(I); out.append(f"np{npr}: r@1={s[0]:5.1f} r@5={s[1]:5.1f} MRR={s[2]:5.1f} ({ms:.1f}ms)")
        print(f"  {name:28s} {bpv*EN/1e9:6.1f} GB@EN  " + " | ".join(out), flush=True)
        del ix; gc.collect()

if __name__ == '__main__':
    main()
