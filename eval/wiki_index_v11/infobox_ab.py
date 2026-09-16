#!/usr/bin/env python3
"""Does keeping the (linearized) infobox hurt prose retrieval? prose-only vs prose+infobox, dense pool."""
import sys, os, json, importlib.util, gc, re
os.environ.setdefault("TOKENIZERS_PARALLELISM","false"); os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF","expandable_segments:True")
import libzim, numpy as np, torch
spec = importlib.util.spec_from_file_location("bp","/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/build_wiki_index_me5_bplus.py")
bp = importlib.util.module_from_spec(spec); spec.loader.exec_module(bp)
from sentence_transformers import SentenceTransformer
tok = bp._tok(); lang = sys.argv[1]
ZIM = {"ja":"wikipedia_ja_all_mini_2026-06.zim","zh":"wikipedia_zh_all_mini_2026-05.zim","en":"wikipedia_en_all_mini_2026-06.zim"}[lang]
ar = libzim.Archive("/home/happy/デスクトップ/mobius_ai/kiwix/"+ZIM)
saved = json.load(open(f"questions_{lang}.json")); gold, questions = saved["eids"], saved["questions"]
def art(eid):
    e = ar._get_entry_by_id(eid); return e.title, bp.extract_text(bytes(e.get_item().content).decode("utf-8","ignore"))
pool = [art(e) for e in gold]; gn = len(pool); step = max(1, ar.entry_count // 18000); eid = 7; seen = set(gold)
while len(pool) - gn < 6000 and eid < ar.entry_count:
    if eid not in seen:
        try:
            e = ar._get_entry_by_id(eid)
            if not e.is_redirect and "html" in str(e.get_item().mimetype).lower():
                raw = bytes(e.get_item().content).decode("utf-8","ignore")
                if len(raw) > 2500: pool.append((e.title, bp.extract_text(raw)))
        except Exception: pass
    eid += step
keep = [i for i,q in enumerate(questions) if len(q) > 10]
model = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda")
q = model.encode([f"query: {questions[i]}" for i in keep], batch_size=128, normalize_embeddings=True, convert_to_numpy=True).astype("float32")
SENT_END = ("。","．",".","!","?","！","？")
def prose_only(text):   # drop short non-sentence lines (infobox rows, headers)
    return "\n".join(l for l in text.split("\n") if len(l) >= 60 or l.rstrip().endswith(SENT_END))
print(f"{lang}: pool {len(pool)}, questions {len(keep)}", flush=True)
def facts_only(text):
    return "\n".join(l for l in text.split("\n") if not (len(l) >= 60 or l.rstrip().endswith(SENT_END)))
VARIANTS = (("prose+infobox", lambda t: [t]), ("prose-only", lambda t: [prose_only(t)]), ("split: prose | facts", lambda t: [prose_only(t), facts_only(t)]))
for name, fn in VARIANTS:
    chunks, owner = [], []
    for i,(title,text) in enumerate(pool):
        reserve = len(tok(title, add_special_tokens=False)["input_ids"]) + 4
        for part in fn(text):
            for c in bp.chunk_text(part, tok, reserve): chunks.append(f"{title}\n{c}"); owner.append(i)
    own = np.array(owner)
    emb = model.encode(["passage: "+c for c in chunks], batch_size=96, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False).astype("float32")
    torch.cuda.empty_cache(); gc.collect()
    order = np.vstack([np.argsort(-(q[i:i+64] @ emb.T), axis=1)[:, :10] for i in range(0, len(q), 64)])
    r1 = np.mean([own[order[r,0]] == keep[r] for r in range(len(keep))]); r5 = np.mean([keep[r] in own[order[r,:5]] for r in range(len(keep))])
    rr = [(1.0/(np.where(own[order[r]]==keep[r])[0][0]+1)) if (own[order[r]]==keep[r]).any() else 0.0 for r in range(len(keep))]
    ntok = sum(len(x) for x in tok(chunks, add_special_tokens=False)["input_ids"])
    print(f"  {name:14s} chunks={len(chunks):6d} tokens={ntok:8d}  recall@1={100*r1:5.1f}  recall@5={100*r5:5.1f}  MRR={100*np.mean(rr):5.1f}", flush=True)
