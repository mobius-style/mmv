#!/usr/bin/env python3
"""A/B the old fixed 1536-char chunker vs the new B+ sentence/token chunker on identical articles."""
import sys, os, statistics, importlib.util
sys.path.insert(0, "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import libzim
from transformers import AutoTokenizer
spec = importlib.util.spec_from_file_location("bplus", "/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/build_wiki_index_me5_bplus.py")
bp = importlib.util.module_from_spec(spec); spec.loader.exec_module(bp)
tok = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")

OLD_CHARS, OLD_OVER = 1536, 256
def old_chunk(t):
    if not t or len(t) < 80: return []
    if len(t) <= OLD_CHARS: return [t]
    out, s = [], 0
    while s < len(t):
        c = t[s:s+OLD_CHARS].strip()
        if c: out.append(c)
        s += OLD_CHARS - OLD_OVER
    return out

def stats(chunks, label):
    if not chunks: return f"{label}: none"
    n = [len(x) for x in tok(["passage: "+c for c in chunks], add_special_tokens=True)["input_ids"]]
    n.sort(); ch = sorted(len(c) for c in chunks)
    over = sum(1 for x in n if x > 512)
    return (f"{label:9s} chunks={len(chunks):6d}  chars p50={ch[len(ch)//2]:5d} p95={ch[len(ch)*19//20]:5d} max={ch[-1]:5d}"
            f"  tok p50={n[len(n)//2]:4d} p95={n[len(n)*19//20]:4d} max={n[-1]:5d}  >512: {100*over/len(n):5.2f}%")

ZIM = {"zh":"/home/happy/デスクトップ/mobius_ai/kiwix/wikipedia_zh_all_mini_2026-05.zim",
       "ja":"/home/happy/デスクトップ/mobius_ai/kiwix/wikipedia_ja_all_mini_2026-06.zim",
       "en":"/home/happy/デスクトップ/mobius_ai/kiwix/wikipedia_en_all_mini_2026-03.zim"}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
for lang, path in ZIM.items():
    if not os.path.exists(path): print(lang, "ZIM missing, skipped"); continue
    ar = libzim.Archive(path); texts = []
    step = max(1, ar.entry_count // (N*3))
    eid = 0
    while len(texts) < N and eid < ar.entry_count:
        try:
            e = ar._get_entry_by_id(eid)
            if not e.is_redirect:
                it = e.get_item()
                if "html" in str(it.mimetype).lower():
                    t = bp.strip_html(bytes(it.content).decode("utf-8", "ignore"))
                    if len(t) >= 80: texts.append(t)
        except Exception: pass
        eid += step
    old = [c for t in texts for c in old_chunk(t)]
    new = [c for t in texts for c in bp.chunk_text(t, tok)]
    print(f"\n=== {lang}  articles={len(texts)}  (mean article {statistics.mean(len(t) for t in texts):.0f} chars)")
    print("  " + stats(old, "OLD 1536"))
    print("  " + stats(new, "B+"))
    print(f"  chunks/article  old={len(old)/len(texts):.2f}  new={len(new)/len(texts):.2f}")
    ex = max(new, key=len)
    print(f"  longest B+ chunk ends: …{ex[-70:]!r}")
    print(f"  sample B+ chunk: {new[len(new)//2][:150]!r}")
