#!/usr/bin/env python3
"""Forensics: what did the EN 'clean' pass actually do? Compare the raw chunk store
(21.9M, MiniLM era) with the published clean store (5.46M, ME5 index)."""
import gzip, json, re, sys, collections, hashlib, random, time
W = "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/Wiki/"
t0 = time.time()
def log(*a): print(f"[{time.time()-t0:6.0f}s]", *a, flush=True)

TITLE_RE = re.compile(r'^\{"title": "((?:[^"\\]|\\.)*)"')
CSS = re.compile(r'mw-parser-output|\.mw-|/\* start https|\{[^}]*:[^}]*;[^}]*\}')

# ---------- clean store: full parse ----------
clean_titles = collections.Counter()
clean_lens, clean_idx, clean_ids = [], collections.Counter(), set()
clean_texts_by_title = {}
dup_id = 0
n = 0
with gzip.open(W+"wiki_chunks_clean.jsonl.gz", "rt", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line); n += 1
        t = d["title"]; clean_titles[t] += 1
        clean_lens.append(len(d["text"])); clean_idx[str(d["chunk_index"])] += 1
        cid = d["chunk_id"]
        if cid in clean_ids: dup_id += 1
        else: clean_ids.add(cid)
        if n % 977 == 0 and len(clean_texts_by_title) < 4000:
            clean_texts_by_title.setdefault(t, d["text"])
log("CLEAN lines", n, "titles", len(clean_titles), "dup chunk_ids", dup_id)
cl = sorted(clean_lens)
log("CLEAN len p5/p50/p95/max", cl[len(cl)//20], cl[len(cl)//2], cl[len(cl)*19//20], cl[-1])
log("CLEAN chunks/title hist", collections.Counter(clean_titles.values()).most_common(8))
log("CLEAN chunk_index top", clean_idx.most_common(6))
css_clean = sum(1 for t in list(clean_texts_by_title.values()) if CSS.search(t))
log("CLEAN css-ish in sample", css_clean, "/", len(clean_texts_by_title))
ends = collections.Counter(t.strip()[-1] for t in clean_texts_by_title.values() if t.strip())
log("CLEAN last-char top", ends.most_common(8))
json.dump({"clean_n": n, "clean_titles": len(clean_titles), "dup_ids": dup_id},
          open("/home/happy/.codex/bench/wiki_forensics/stage1.json","w"))

# ---------- raw store: streaming, cheap ----------
raw_titles = collections.Counter()
raw_lens, raw_idx = [], collections.Counter()
raw_sample_by_title = {}
m = 0
with gzip.open(W+"wiki_chunks.jsonl.gz", "rt", encoding="utf-8") as f:
    for line in f:
        m += 1
        mt = TITLE_RE.match(line)
        if mt: raw_titles[mt.group(1)] += 1
        if m % 37 == 0:
            try: d = json.loads(line)
            except Exception: continue
            raw_lens.append(len(d["text"])); raw_idx[str(d["chunk_index"])] += 1
            if len(raw_sample_by_title) < 4000: raw_sample_by_title.setdefault(d["title"], d["text"])
        if m % 5_000_000 == 0: log("  raw", m)
log("RAW lines", m, "titles", len(raw_titles))
rl = sorted(raw_lens)
log("RAW len p5/p50/p95/max", rl[len(rl)//20], rl[len(rl)//2], rl[len(rl)*19//20], rl[-1])
log("RAW chunks/title hist", collections.Counter(raw_titles.values()).most_common(8))
css_raw = sum(1 for t in raw_sample_by_title.values() if CSS.search(t))
log("RAW css-ish in sample", css_raw, "/", len(raw_sample_by_title))

# ---------- set comparison ----------
ct, rt = set(clean_titles), set(raw_titles)
kept, dropped, added = ct & rt, rt - ct, ct - rt
log("TITLES raw", len(rt), "clean", len(ct), "kept", len(kept), "dropped", len(dropped), "clean-only", len(added))
rnd = random.Random(7)
log("DROPPED sample:", rnd.sample(sorted(dropped), min(25, len(dropped))))
log("CLEAN-ONLY sample:", rnd.sample(sorted(added), min(10, len(added))) if added else [])
# chunks-per-title for kept titles
k = rnd.sample(sorted(kept), min(200000, len(kept)))
ratio = [(clean_titles[t], raw_titles[t]) for t in k]
log("kept titles: mean clean chunks %.2f, mean raw chunks %.2f" % (
    sum(a for a,_ in ratio)/len(ratio), sum(b for _,b in ratio)/len(ratio)))
log("clean==1 chunk share %.3f ; raw==1 chunk share %.3f" % (
    sum(1 for a,_ in ratio if a==1)/len(ratio), sum(1 for _,b in ratio if b==1)/len(ratio)))
# text comparison for shared titles present in both samples
both = [t for t in clean_texts_by_title if t in raw_sample_by_title][:8]
for t in both[:4]:
    log("---- title:", t[:60])
    log("   RAW  :", raw_sample_by_title[t][:220].replace("\n"," "))
    log("   CLEAN:", clean_texts_by_title[t][:220].replace("\n"," "))
json.dump({"raw_n": m, "raw_titles": len(rt), "kept": len(kept), "dropped": len(dropped),
           "clean_only": len(added)}, open("/home/happy/.codex/bench/wiki_forensics/stage2.json","w"))
log("DONE")
