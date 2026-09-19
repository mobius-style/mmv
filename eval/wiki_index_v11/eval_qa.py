#!/usr/bin/env python3
"""Fair A/B: retrieve by a generated content question (never the title verbatim)."""
import sys, os, json, random, importlib.util, urllib.request, concurrent.futures as cf
sys.path.insert(0, "/home/happy/.codex/bench/wiki_forensics")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import libzim, numpy as np, clean_v2
spec = importlib.util.spec_from_file_location("bp", "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/build_wiki_index_me5_bplus.py")
bp = importlib.util.module_from_spec(spec); spec.loader.exec_module(bp)
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
lang = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 400
STAGE = sys.argv[3] if len(sys.argv) > 3 else "all"
QFILE = f"/home/happy/.codex/bench/wiki_forensics/questions_{lang}.json"
LANGNAME = {"ja":"Japanese","zh":"Chinese","en":"English"}[lang]
ZIM = {"ja":"wikipedia_ja_all_mini_2026-06.zim","zh":"wikipedia_zh_all_mini_2026-05.zim","en":"wikipedia_en_all_mini_2026-06.zim"}[lang]

ar = libzim.Archive("/home/happy/デスクトップ/mobius_ai/kiwix/"+ZIM)
step = max(1, ar.entry_count // (N*8)); arts = []; eid = 0
while len(arts) < N and eid < ar.entry_count:
    try:
        e = ar._get_entry_by_id(eid)
        if not e.is_redirect:
            it = e.get_item()
            if "html" in str(it.mimetype).lower():
                raw = bytes(it.content).decode("utf-8","ignore")
                v2 = clean_v2.extract_text(raw)
                prose = "\n".join(l for l in v2.split("\n") if len(l) > 80)
                if len(prose) > 300: arts.append((e.title, raw, prose[:1200], eid))
    except Exception: pass
    eid += step
print(f"{lang}: {len(arts)} articles with substantive prose", flush=True)

PROMPT = ("Passage:\n{p}\n\n"
          "Write ONE specific question in {L} that this passage answers. "
          "Do not quote the subject's name verbatim — refer to it descriptively. "
          "Output only the question.")
def ask(args):
    title, prose = args
    body = json.dumps({"messages":[{"role":"user","content":PROMPT.format(p=prose, L=LANGNAME)}],
                       "max_tokens":80, "temperature":0.3}).encode()
    r = urllib.request.Request("http://127.0.0.1:8106/v1/chat/completions", data=body,
                               headers={"Content-Type":"application/json"})
    try:
        d = json.load(urllib.request.urlopen(r, timeout=180))
        return (d["choices"][0]["message"].get("content") or "").strip().split("\n")[0]
    except Exception as e:
        return ""
if STAGE in ("all","qgen"):
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        questions = list(ex.map(ask, [(t, p) for t, _, p, _e in arts]))
    json.dump({"eids":[a[3] for a in arts], "titles":[a[0] for a in arts], "questions":questions},
              open(QFILE,"w"), ensure_ascii=False)
    print("  saved", QFILE, flush=True)
    if STAGE == "qgen": sys.exit(0)
else:
    saved = json.load(open(QFILE)); questions = saved["questions"]
    assert [a[3] for a in arts] == saved["eids"], "article scan drifted"
keep = [i for i,q in enumerate(questions) if len(q) > 10]
print(f"  questions generated: {len(keep)}/{len(arts)}  e.g. {questions[keep[0]][:90]}", flush=True)

from sentence_transformers import SentenceTransformer
model = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda")
res = {}
for variant in ("current", "v2", "v2+title"):
    chunks, owner = [], []
    for i,(title, raw, _, _eid) in enumerate(arts):
        text = bp.strip_html(raw) if variant == "current" else clean_v2.extract_text(raw)
        cs = bp.chunk_text(text, tok)
        if variant == "v2+title": cs = [f"{title}\n{c}" for c in cs]
        for c in cs: chunks.append(c); owner.append(i)
    own = np.array(owner)
    emb = model.encode(["passage: "+c for c in chunks], batch_size=256, normalize_embeddings=True,
                       convert_to_numpy=True, show_progress_bar=False).astype("float32")
    q = model.encode([f"query: {questions[i]}" for i in keep], batch_size=256,
                     normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    S = q @ emb.T; order = np.argsort(-S, axis=1)[:, :10]
    hit1 = np.mean([own[order[r,0]] == keep[r] for r in range(len(keep))])
    rr = []
    for r in range(len(keep)):
        w = np.where(own[order[r]] == keep[r])[0]
        rr.append(1.0/(w[0]+1) if len(w) else 0.0)
    ntok = sorted(len(x) for x in tok(["passage: "+c for c in chunks], add_special_tokens=True)["input_ids"])
    res[variant] = dict(chunks=len(chunks), tok_p50=ntok[len(ntok)//2], tok_sum=sum(ntok),
                        recall1=round(100*float(hit1),1), mrr=round(100*float(np.mean(rr)),1))
    print(f"  {variant:9s} chunks={len(chunks):5d} tok_total={sum(ntok):7d} p50={res[variant]['tok_p50']:4d}"
          f"  QA recall@1={res[variant]['recall1']:5.1f}%  MRR={res[variant]['mrr']:5.1f}", flush=True)
json.dump({"questions": [questions[i] for i in keep[:20]], "res": res},
          open(f"/home/happy/.codex/bench/wiki_forensics/evalqa_{lang}.json","w"), ensure_ascii=False, indent=1)
