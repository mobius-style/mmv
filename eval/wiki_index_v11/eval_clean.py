#!/usr/bin/env python3
"""A/B the current extractor vs clean_v2 on retrieval quality, not aesthetics."""
import sys, os, json, random, importlib.util
sys.path.insert(0, "/home/happy/.codex/bench/wiki_forensics")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import libzim, numpy as np, clean_v2
spec = importlib.util.spec_from_file_location("bp", "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/build_wiki_index_me5_bplus.py")
bp = importlib.util.module_from_spec(spec); spec.loader.exec_module(bp)
from transformers import AutoTokenizer
from sentence_transformers import SentenceTransformer
tok = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
model = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda")

N = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
lang = sys.argv[1]
ZIM = {"ja":"wikipedia_ja_all_mini_2026-06.zim","zh":"wikipedia_zh_all_mini_2026-05.zim","en":"wikipedia_en_all_mini_2026-06.zim"}[lang]
ar = libzim.Archive("/home/happy/デスクトップ/mobius_ai/kiwix/"+ZIM)
step = max(1, ar.entry_count // (N*4)); arts = []; eid = 0
while len(arts) < N and eid < ar.entry_count:
    try:
        e = ar._get_entry_by_id(eid)
        if not e.is_redirect:
            it = e.get_item()
            if "html" in str(it.mimetype).lower():
                raw = bytes(it.content).decode("utf-8","ignore")
                if len(raw) > 2500: arts.append((e.title, raw))
    except Exception: pass
    eid += step
print(f"{lang}: {len(arts)} articles")

def build(variant):
    chunks, owner = [], []
    for i,(title, raw) in enumerate(arts):
        text = bp.strip_html(raw) if variant == "current" else clean_v2.extract_text(raw)
        cs = bp.chunk_text(text, tok)
        if variant == "v2+title":
            cs = [f"{title}\n{c}" for c in cs]
        for c in cs: chunks.append(c); owner.append(i)
    return chunks, np.array(owner)

res = {}
for variant in ("current", "v2", "v2+title"):
    ch, own = build(variant)
    ntok = sorted(len(x) for x in tok(["passage: "+c for c in ch], add_special_tokens=True)["input_ids"])
    emb = model.encode(["passage: "+c for c in ch], batch_size=256, normalize_embeddings=True,
                       convert_to_numpy=True, show_progress_bar=False).astype("float32")
    q = model.encode([f"query: {t}" for t,_ in arts], batch_size=256, normalize_embeddings=True,
                     convert_to_numpy=True).astype("float32")
    S = q @ emb.T                                   # exact search over the pool
    order = np.argsort(-S, axis=1)[:, :10]
    hit1 = np.mean(own[order[:,0]] == np.arange(len(arts)))
    rr = []
    for i in range(len(arts)):
        r = np.where(own[order[i]] == i)[0]
        rr.append(1.0/(r[0]+1) if len(r) else 0.0)
    rnd = random.Random(3); idx = [rnd.randrange(len(ch)) for _ in range(4000)]
    pair = float(np.mean(np.sum(emb[idx[:2000]] * emb[idx[2000:]], axis=1)))
    foot = sum(1 for c in ch if "issued from Wikipedia" in c) / len(ch)
    res[variant] = dict(chunks=len(ch), tok_p50=ntok[len(ntok)//2], tok_p95=ntok[len(ntok)*19//20],
                        over512=100*sum(1 for x in ntok if x>512)/len(ntok),
                        recall1=100*float(hit1), mrr=100*float(np.mean(rr)),
                        mean_pair_cos=round(pair,4), footer=round(100*foot,1))
    print(f"  {variant:9s} chunks={res[variant]['chunks']:5d} tok p50={res[variant]['tok_p50']:4d} "
          f">512={res[variant]['over512']:.2f}%  recall@1={res[variant]['recall1']:5.1f}%  MRR={res[variant]['mrr']:5.1f}  "
          f"pairwise-cos={res[variant]['mean_pair_cos']:.4f}  footer={res[variant]['footer']}%", flush=True)
json.dump(res, open(f"/home/happy/.codex/bench/wiki_forensics/eval_{lang}.json","w"), indent=1)
