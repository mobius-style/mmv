#!/usr/bin/env python3
"""Same QA questions, but against a dense pool of distractors — does cleaning help when the
index is big enough that near-duplicates compete?"""
import sys, os, json, importlib.util
sys.path.insert(0, "/home/happy/.codex/bench/wiki_forensics")
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF","expandable_segments:True")
import libzim, numpy as np, clean_v2
spec = importlib.util.spec_from_file_location("bp","/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/build_wiki_index_me5_bplus.py")
bp = importlib.util.module_from_spec(spec); spec.loader.exec_module(bp)
from transformers import AutoTokenizer
from sentence_transformers import SentenceTransformer
tok = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
lang = sys.argv[1]; DIST = int(sys.argv[2]) if len(sys.argv)>2 else 6000
ZIM = {"ja":"wikipedia_ja_all_mini_2026-06.zim","zh":"wikipedia_zh_all_mini_2026-05.zim","en":"wikipedia_en_all_mini_2026-06.zim"}[lang]
ar = libzim.Archive("/home/happy/デスクトップ/mobius_ai/kiwix/"+ZIM)
saved = json.load(open(f"/home/happy/.codex/bench/wiki_forensics/questions_{lang}.json"))
gold_eids, questions = saved["eids"], saved["questions"]
def raw_of(eid):
    e = ar._get_entry_by_id(eid)
    return e.title, bytes(e.get_item().content).decode("utf-8","ignore")
pool = [(eid, *raw_of(eid)) for eid in gold_eids]          # gold articles first
gold_n = len(pool)
step = max(1, ar.entry_count // (DIST*3)); eid = 7
seen = set(gold_eids)
while len(pool) - gold_n < DIST and eid < ar.entry_count:
    if eid not in seen:
        try:
            e = ar._get_entry_by_id(eid)
            if not e.is_redirect:
                it = e.get_item()
                if "html" in str(it.mimetype).lower():
                    raw = bytes(it.content).decode("utf-8","ignore")
                    if len(raw) > 2500: pool.append((eid, e.title, raw))
        except Exception: pass
    eid += step
print(f"{lang}: gold {gold_n} + distractors {len(pool)-gold_n} articles", flush=True)
model = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda")
keep = [i for i,q in enumerate(questions) if len(q) > 10]
out = {}
for variant in ("current","v2","v2+title"):
    chunks, owner = [], []
    for i,(eid,title,raw) in enumerate(pool):
        text = bp.strip_html(raw) if variant=="current" else clean_v2.extract_text(raw)
        cs = bp.chunk_text(text, tok)
        if variant=="v2+title": cs = [f"{title}\n{c}" for c in cs]
        for c in cs: chunks.append(c); owner.append(i)
    import torch, gc
    torch.cuda.empty_cache(); gc.collect()
    own = np.array(owner)
    emb = model.encode(["passage: "+c for c in chunks], batch_size=96, normalize_embeddings=True,
                       convert_to_numpy=True, show_progress_bar=False).astype("float32")
    q = model.encode([f"query: {questions[i]}" for i in keep], batch_size=256,
                     normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    torch.cuda.empty_cache(); gc.collect()
    order = np.vstack([np.argsort(-(q[i:i+64] @ emb.T), axis=1)[:, :10] for i in range(0, len(q), 64)])
    hit1 = np.mean([own[order[r,0]] == keep[r] for r in range(len(keep))])
    hit5 = np.mean([keep[r] in own[order[r,:5]] for r in range(len(keep))])
    rr = []
    for r in range(len(keep)):
        w = np.where(own[order[r]] == keep[r])[0]; rr.append(1.0/(w[0]+1) if len(w) else 0.0)
    out[variant] = dict(pool_chunks=len(chunks), recall1=round(100*float(hit1),1),
                        recall5=round(100*float(hit5),1), mrr=round(100*float(np.mean(rr)),1))
    print(f"  {variant:9s} pool={len(chunks):6d} chunks  recall@1={out[variant]['recall1']:5.1f}%"
          f"  recall@5={out[variant]['recall5']:5.1f}%  MRR={out[variant]['mrr']:5.1f}", flush=True)
json.dump(out, open(f"/home/happy/.codex/bench/wiki_forensics/evalscale_{lang}.json","w"), indent=1)
