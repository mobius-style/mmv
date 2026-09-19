#!/usr/bin/env python3
"""Control for the benchmark bias a reviewer flagged: the question set was generated from text
produced by the NEW extractor. Generate a second set from the OLD extractor's text for the same
articles, so the old artifact is scored on questions drawn from what IT could see."""
import sys, os, json, importlib.util, urllib.request, concurrent.futures as cf
sys.path.insert(0, "/home/happy/.codex/bench/wiki_forensics")
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
import libzim
spec = importlib.util.spec_from_file_location("bp","/home/happy/デスクトップ/mobius_ai/MOBIUS_MMV/build_wiki_index_me5_bplus.py")
bp = importlib.util.module_from_spec(spec); spec.loader.exec_module(bp)
# the OLD extractor: tag-only stripping, as shipped in build_wiki_index_me5.py
import re
_TAG=re.compile(r"<[^>]+>"); _SPC=re.compile(r"\s+")
_BLOCK=re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I|re.S)
_CSSCMT=re.compile(r"/\*.*?\*/", re.S); _CSSRULE=re.compile(r"[.#@][-\w][^{}<>]{0,200}\{[^{}]*\}")
def old_strip(h):
    h=_BLOCK.sub(" ",h); h=_TAG.sub(" ",h); h=_CSSCMT.sub(" ",h); h=_CSSRULE.sub(" ",h)
    return _SPC.sub(" ",h).strip()
lang = sys.argv[1]
LANGNAME={"ja":"Japanese","zh":"Chinese"}[lang]
ZIM={"ja":"wikipedia_ja_all_mini_2026-06.zim","zh":"wikipedia_zh_all_mini_2026-05.zim"}[lang]
ar = libzim.Archive("/home/happy/デスクトップ/mobius_ai/kiwix/"+ZIM)
saved = json.load(open(f"questions_{lang}.json"))
PROMPT=("Passage:\n{p}\n\nWrite ONE specific question in {L} that this passage answers. "
        "Do not quote the subject's name verbatim — refer to it descriptively. Output only the question.")
def ask(p):
    body=json.dumps({"messages":[{"role":"user","content":PROMPT.format(p=p,L=LANGNAME)}],
                     "max_tokens":80,"temperature":0.3}).encode()
    r=urllib.request.Request("http://127.0.0.1:8106/v1/chat/completions",data=body,headers={"Content-Type":"application/json"})
    try: return (json.load(urllib.request.urlopen(r,timeout=180))["choices"][0]["message"].get("content") or "").strip().split("\n")[0]
    except Exception: return ""
prose=[]
for eid in saved["eids"]:
    e=ar._get_entry_by_id(eid); raw=bytes(e.get_item().content).decode("utf-8","ignore")
    t=old_strip(raw)
    prose.append(t[:1200])
with cf.ThreadPoolExecutor(max_workers=4) as ex: qs=list(ex.map(ask, prose))
json.dump({"eids":saved["eids"],"titles":saved["titles"],"questions":qs},
          open(f"questions_{lang}_oldextract.json","w"), ensure_ascii=False)
print(f"{lang}: {sum(1 for q in qs if len(q)>10)}/{len(qs)} questions from the OLD extractor's text")
print("  e.g.", next(q for q in qs if len(q)>10)[:90])
