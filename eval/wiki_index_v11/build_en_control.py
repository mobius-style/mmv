#!/usr/bin/env python3
"""English head-to-head control set.

The published English store came from a cleaning pass whose script no longer exists, so the ja/zh
control (re-run the OLD extractor over the ZIM) cannot be reproduced for English. Instead the
questions are generated from the OLD STORE'S OWN CHUNK TEXT — exactly the text the old index
encoded. Every question is therefore answerable from what the old artifact could see, and the new
artifact gets no credit for text only it recovered.

Articles are sampled by uniform stride over the old store, restricted to titles present in BOTH
stores, so both sides are scored on the same gold set.
"""
import gzip, json, os, pickle, urllib.request, concurrent.futures as cf

OLD = "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/Wiki/wiki_chunks_clean.jsonl.gz"
NEW = "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/data/wiki_en_me5_2026-06_v11b/wiki_chunks.jsonl.gz"
CACHE, N_WANT = "en_control_sample.pkl", 400

if os.path.exists(CACHE):
    sample = pickle.load(open(CACHE, "rb"))
    print(f"reusing cached sample of {len(sample)} articles", flush=True)
else:
    print("pass 1: titles in the new store", flush=True)
    new_titles = set()
    with gzip.open(NEW, "rt", encoding="utf-8") as f:
        for line in f:
            new_titles.add(json.loads(line)["title"])
    print(f"  new store: {len(new_titles):,} distinct titles", flush=True)

    print("pass 2: old store — collect text per article, keep those present in both", flush=True)
    arts, cur_t, cur_x, n_old = [], None, [], 0
    with gzip.open(OLD, "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line); t = d["title"]
            if t != cur_t:
                if cur_t is not None:
                    n_old += 1
                    if cur_t in new_titles: arts.append((cur_t, " ".join(cur_x)[:1200]))
                cur_t, cur_x = t, []
            if len(" ".join(cur_x)) < 1300: cur_x.append(d["text"])
        if cur_t is not None:
            n_old += 1
            if cur_t in new_titles: arts.append((cur_t, " ".join(cur_x)[:1200]))
    print(f"  old store: {n_old:,} distinct titles, {len(arts):,} of them also in v11b", flush=True)
    arts = [a for a in arts if len(a[1]) > 300]
    step = max(1, len(arts) // N_WANT)
    sample = arts[::step][:N_WANT]
    pickle.dump(sample, open(CACHE, "wb"))
    print(f"  sampled {len(sample)} articles by uniform stride (every {step})", flush=True)

PROMPT = ("Passage:\n{p}\n\nWrite ONE specific question in English that this passage answers. "
          "Do not quote the subject's name verbatim — refer to it descriptively. Output only the question.")

def ask(p):
    body = json.dumps({"messages": [{"role": "user", "content": PROMPT.format(p=p)}],
                       "max_tokens": 120, "temperature": 0.3,
                       # Gemma-4 spends the entire budget on thinking and returns empty content
                       # unless thinking is disabled explicitly (known trap, see memory).
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    r = urllib.request.Request("http://127.0.0.1:8106/v1/chat/completions", data=body,
                               headers={"Content-Type": "application/json"})
    try:
        return (json.load(urllib.request.urlopen(r, timeout=300))["choices"][0]["message"].get("content") or "").strip().split("\n")[0]
    except Exception:
        return ""

with cf.ThreadPoolExecutor(max_workers=4) as ex:
    qs = list(ex.map(ask, [x[1] for x in sample]))
ok = sum(1 for q in qs if len(q) > 10)
json.dump({"titles": [x[0] for x in sample], "questions": qs},
          open("questions_en_oldstore.json", "w"), ensure_ascii=False)
print(f"en: {ok}/{len(qs)} questions generated from the OLD STORE's own text", flush=True)
for q in qs[:3]:
    if len(q) > 10: print("  e.g.", q[:110], flush=True)
