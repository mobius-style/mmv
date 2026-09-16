#!/usr/bin/env python3
"""Budget sweep on the dense-pool QA benchmark: is 480 the right chunk budget?"""
import sys, os, json, importlib.util, gc
sys.path.insert(0, "/home/happy/.codex/bench/wiki_forensics")
os.environ.setdefault("TOKENIZERS_PARALLELISM","false"); os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF","expandable_segments:True")
import libzim, numpy as np, torch
spec = importlib.util.spec_from_file_location("bp","/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/build_wiki_index_me5_bplus.py")
bp = importlib.util.module_from_spec(spec); spec.loader.exec_module(bp)
from transformers import AutoTokenizer
from sentence_transformers import SentenceTransformer
tok = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
lang = sys.argv[1]; DIST = 6000
ZIM = {"ja":"wikipedia_ja_all_mini_2026-06.zim","zh":"wikipedia_zh_all_mini_2026-05.zim","en":"wikipedia_en_all_mini_2026-06.zim"}[lang]
ar = libzim.Archive("/home/happy/デスクトップ/mobius_ai/kiwix/"+ZIM)
saved = json.load(open(f"questions_{lang}.json")); gold_eids, questions = saved["eids"], saved["questions"]
def art(eid):
    e = ar._get_entry_by_id(eid); return e.title, bp.extract_text(bytes(e.get_item().content).decode("utf-8","ignore"))
pool = [art(eid) for eid in gold_eids]; gold_n = len(pool)
step = max(1, ar.entry_count // (DIST*3)); eid = 7; seen = set(gold_eids)
while len(pool) - gold_n < DIST and eid < ar.entry_count:
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
print(f"{lang}: pool {len(pool)} articles, {len(keep)} questions", flush=True)
for budget in (160, 256, 360, 480):
    bp.TOKEN_BUDGET = budget
    chunks, owner = [], []
    for i,(title,text) in enumerate(pool):
        for c in bp.chunk_text(text, tok): chunks.append(f"{title}\n{c}"); owner.append(i)
    own = np.array(owner)
    emb = model.encode(["passage: "+c for c in chunks], batch_size=96, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False).astype("float32")
    torch.cuda.empty_cache(); gc.collect()
    order = np.vstack([np.argsort(-(q[i:i+64] @ emb.T), axis=1)[:, :10] for i in range(0, len(q), 64)])
    r1 = np.mean([own[order[r,0]] == keep[r] for r in range(len(keep))]); r5 = np.mean([keep[r] in own[order[r,:5]] for r in range(len(keep))])
    rr = [ (1.0/(np.where(own[order[r]]==keep[r])[0][0]+1)) if (own[order[r]]==keep[r]).any() else 0.0 for r in range(len(keep))]
    ntok = sorted(len(x) for x in tok(["passage: "+c for c in chunks], add_special_tokens=True)["input_ids"])
    print(f"  budget={budget:3d}  chunks={len(chunks):6d} (x{len(chunks)/len(pool):.2f}/article)  tok p50={ntok[len(ntok)//2]:3d} max={ntok[-1]:3d}"
          f"  recall@1={100*r1:5.1f}  recall@5={100*r5:5.1f}  MRR={100*np.mean(rr):5.1f}", flush=True)
