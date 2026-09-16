#!/usr/bin/env python3
"""
build_wiki_index_me5_bplus.py — Phase C Box B: Wikipedia ZIM → FAISS IndexIVFPQ
v11 (B+): 文境界 + ME5 512トークン窓に収まるチャンク化。
  2026-09-14 実測: 1536字固定スライスは ja の 11.9% / zh の 20.6% が 512 超で
  埋め込み時に無言で切り捨てられていた（超過分の平均 22-25% が失われる）。
  B+ は文境界で区切り 480 トークン以内に収める（超過率ほぼ 0）。
  chunk_id を内容ハッシュ化し、マージ時に完全重複を排除する。
  v11.1: 抽出器を差し替え（render-faithful）。ZIM footer（公開 ja の 96.1% / zh の 89.9%
  のチャンクに混入していた英語の CC ライセンス文）、<head>/<h1> のタイトル重複、
  インライン tag→空白で語が割れる欠陥、HTML 実体未展開、CJK 文中への空白挿入を除去。
  各チャンク先頭にタイトルを 1 行付す（自己記述的な引用単位にするため）。
  実測(2026-09-14, QA 検索 A/B, 6,000 記事の妨害プール): MRR ja 79.1->79.0 / zh 81.8->83.0 /
  en 91.7->92.5、トークン総量 -13〜16%。

変更点（v9からの改善）:
  - 21.9Mチャンクを4Partに分割して逐次保存
  - 途中で落ちても完了済みPartはスキップして再開
  - 全Part完了後にmerge_from()で統合
  - Part単位・全体の進捗ゲージ（tqdm）を表示

Author: Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, os, re, sys, time
import multiprocessing as mp
from html import unescape
from datetime import datetime, timezone
from pathlib import Path

def check_deps():
    missing = []
    for pkg in ["libzim","sentence_transformers","faiss","numpy","torch","psutil","tqdm"]:
        try: __import__(pkg)
        except ImportError: missing.append(pkg)
    if missing:
        print(f"ERROR: missing: {missing}")
        sys.exit(1)

check_deps()

import numpy as np
import faiss
import torch
import psutil
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
import libzim

# ── 定数 ─────────────────────────────────────────────────────────────────────
MODEL_NAME     = "intfloat/multilingual-e5-large"  # ME5-large, 1024-dim
DIM            = 1024
PASSAGE_PREFIX = "passage: "   # E5 requires this prefix on indexed passages
CHUNK_CHARS    = 1536
OVERLAP_CHARS  = 256
NLIST          = 4096
M_PQ           = 64            # (legacy PQ setting, kept for the manifest diff)
NBITS          = 8
INDEX_KIND     = "IVF,SQ4"     # measured 2026-09-14 on 150k ME5 vectors, recall@10 vs exact at nprobe 64:
                               # IVF,PQ64 47.0% (the shipped type) | OPQ256,PQ256 84.6% | IVF,SQ8 96.2% (1,024 B/vec)
SQ_BYTES       = 512      # QT_4bit: 4 bits x 1024 dims
DEFAULT_BATCH  = 512
RAM_RESERVE_GB = 10.0
N_PARTS        = 4

# Per-language Wikipedia URL base, set from --lang in __main__ (fork-inherited by workers)
WIKI_URL_BASE  = "https://en.wikipedia.org/wiki/"

def calc_buffer_size() -> int:
    available_gb    = psutil.virtual_memory().available / 1e9
    usable_gb       = max(0, available_gb - RAM_RESERVE_GB) * 0.40
    bytes_per_chunk = 3200  # 実測値ベース
    calc_buf        = int(usable_gb * 1e9 / bytes_per_chunk)
    return max(2_000_000, min(calc_buf, 8_000_000))

# ── HTML除去・チャンク ────────────────────────────────────────────────────────
_TAG_RE   = re.compile(r"<[^>]+>")
_SPC_RE   = re.compile(r"\s+")
# Remove <script>/<style> blocks INCLUDING their text content (MediaWiki inlines
# TemplateStyles CSS in <style> tags; tag-only stripping leaks the CSS as text).
_BLOCK_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_CSSCMT_RE= re.compile(r"/\*.*?\*/", re.S)               # leftover CSS comments
_CSSRULE_RE= re.compile(r"[.#@][-\w][^{}<>]{0,200}\{[^{}]*\}")  # leftover CSS rules as text

def strip_html(html: str) -> str:
    html = _BLOCK_RE.sub(" ", html)
    html = _TAG_RE.sub(" ", html)
    html = _CSSCMT_RE.sub(" ", html)
    html = _CSSRULE_RE.sub(" ", html)
    return _SPC_RE.sub(" ", html).strip()

_CONTENT   = re.compile(r'<div[^>]+id="mw-content-text"', re.I)
_HTDIG     = re.compile(r'<!--\s*htdig_noindex\s*-->.*?<!--\s*/htdig_noindex\s*-->', re.S | re.I)
_ZIMFOOT   = re.compile(r'<div[^>]*class="[^"]*zim-footer[^"]*".*?</div>', re.S | re.I)
_SCRIPT    = re.compile(r'<(script|style)\b[^>]*>.*?</\1>', re.I | re.S)
_COMMENT   = re.compile(r'<!--.*?-->', re.S)
_BLOCK     = re.compile(r'</?(?:p|div|section|h[1-6]|li|ul|ol|dl|dd|dt|tr|table|tbody|thead|br|hr|blockquote|figure|figcaption|caption|aside|nav|header|footer|main)\b[^>]*>', re.I)
_CELL      = re.compile(r'</(?:td|th)\s*>', re.I)
_ROW       = re.compile(r'<tr\b[^>]*>(.*?)</tr\s*>', re.I | re.S)
_CELLSPLIT = re.compile(r'<t[dh]\b[^>]*>(.*?)</t[dh]\s*>', re.I | re.S)

def _linearize_row(m: "re.Match") -> str:
    cells = [_TAG.sub('', re.sub(r'<br\s*/?>', ' ', c, flags=re.I)).strip() for c in _CELLSPLIT.findall(m.group(1))]
    cells = [unescape(_SPACES.sub(' ', c)).strip() for c in cells if c and c.strip()]
    if not cells: return '\n'
    if len(cells) == 2: return '\n' + cells[0] + ': ' + cells[1] + '\n'
    return '\n' + ' | '.join(cells) + '\n'
_TAG       = re.compile(r'<[^>]+>')
_CSSCMT    = re.compile(r'/\*.*?\*/', re.S)
_CSSRULE   = re.compile(r'[.#@][-\w][^{}<>]{0,200}\{[^{}]*\}')
_FOOTTXT   = re.compile(r'This article is issued from Wikipedia[^\n]*', re.I)
_EDITLINKS = re.compile(r'\[\s*(?:edit|編集|编辑|編輯)\s*\]', re.I)
# Navigation strips only. Keyword lists were removed after review (2026-09-15): '編集' also means
# film editing and '解説' commentary, so the old rule deleted ~22k real ja infobox rows, and
# '^Project' matched article prose. These patterns match the MediaWiki navbar/navbox rendering only.
_NAVBOX    = re.compile(r'<(?:div|table)[^>]*class="[^"]*(?:navbox|navbar|vertical-navbox|metadata|ambox|sistersitebox|noprint)[^"]*"[^>]*>.*?</(?:div|table)\s*>', re.I | re.S)
_NAVLINE   = re.compile(r'^(?:■?\s*(?:v\s*[·・.]?\s*t\s*[·・.]?\s*e|[查査]\s*[论論]\s*[编編]|檢\s*視\s*論\s*編|表示\s*編集\s*履歴)\s*)$', re.I)
_SYMBOLONLY= re.compile(r'^[\W_]{1,12}$')
_CJK       = r'　-〿぀-ヿ㐀-䶿一-鿿豈-﫿＀-￯'
_CJKSPACE  = re.compile(r'(?<=[' + _CJK + r'])[ \t]+(?=[' + _CJK + r'])')
_SPACES    = re.compile(r'[ \t ]+')
_NEWLINES  = re.compile(r'\s*\n\s*')

def extract_text(html: str) -> str:
    m = _CONTENT.search(html)
    if m:
        html = html[m.start():]
    else:                                   # fall back to <body>
        b = html.lower().find('<body')
        if b >= 0: html = html[b:]
    html = _HTDIG.sub('\n', html)
    html = _NAVBOX.sub('\n', html)   # navbars/navboxes as markup, not as keywords
    html = _ZIMFOOT.sub('\n', html)
    html = _SCRIPT.sub(' ', html)
    html = _COMMENT.sub(' ', html)
    html = _ROW.sub(_linearize_row, html)   # table rows -> 'key: value' lines
    html = _CELL.sub(' 　| ', html)     # stray cells outside <tr>
    html = _BLOCK.sub('\n', html)
    html = _TAG.sub('', html)               # inline tags: no space injected
    text = unescape(html)
    text = _CSSCMT.sub(' ', text)
    text = _CSSRULE.sub(' ', text)
    text = _FOOTTXT.sub(' ', text)
    text = _EDITLINKS.sub(' ', text)
    text = text.replace('　| \n', '\n').replace('　|', ' |')
    text = _SPACES.sub(' ', text)
    text = _NEWLINES.sub('\n', text)
    # (the CJK space-collapsing rule was removed after review: it deleted real spaces inside titles
    #  such as 'ロイヤル ストレート フラッシュ'; inline tags no longer inject spaces, so it is unneeded)
    lines, seen_first = [], None
    for ln in (l.strip(' |') for l in text.split('\n')):
        if not ln: continue
        if _NAVLINE.match(ln) or _SYMBOLONLY.match(ln): continue
        if seen_first is None: seen_first = ln
        elif ln == seen_first: continue     # drop repeated title lines
        lines.append(ln)
    return '\n'.join(lines).strip()


_SENT_END = ("。","．",".","!","?","！","？")
def split_prose_facts(text: str) -> tuple[str, str]:
    """Measured 2026-09-14: mixing infobox rows into prose chunks costs prose retrieval
    (en MRR 93.3 vs 95.9); dropping them loses facts. So: prose chunks and a separate
    facts chunk stream per article ('split' variant: ja 81.2 / zh 84.3 / en 95.8 MRR)."""
    prose, facts = [], []
    for ln in text.split("\n"):
        (prose if (len(ln) >= 60 or ln.rstrip().endswith(_SENT_END)) else facts).append(ln)
    return "\n".join(prose), "\n".join(facts)

TOKEN_BUDGET   = 256           # swept 160/256/360/480 on a QA benchmark (2026-09-14): 256 = best cost/quality
MIN_CHUNK_CHARS = 25           # floor on cleaned text; the old 80 was calibrated on
MIN_ARTICLE_CHARS = 25         # boilerplate-padded text (see docs/WIKI_INDEX_V11.md)
_TOK = None

def _tok():
    """Fast tokenizer, created lazily inside each worker process (post-fork)."""
    global _TOK
    if _TOK is None:
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from transformers import AutoTokenizer
        _TOK = AutoTokenizer.from_pretrained(MODEL_NAME)
    return _TOK

# Sentence end: CJK enders, or Latin .!? followed by whitespace.
_ABBREV = ("u.s", "u.k", "e.g", "i.e", "etc", "vs", "approx", "no", "nos", "st", "mt", "ft", "jr", "sr",
           "dr", "mr", "mrs", "ms", "prof", "rev", "gen", "col", "capt", "lt", "sgt", "inc", "ltd",
           "co", "corp", "dept", "univ", "est", "fig", "figs", "vol", "vols", "pp", "ed", "eds",
           "al", "ca", "cf", "ave", "blvd", "rd", "ph.d", "m.a", "b.a", "d.c", "a.m", "p.m")
_END_RE = re.compile(r"[。．！？]|(?:[.!?](?=\s))")

def _is_real_end(text: str, end: int) -> bool:
    """Reject '.' that closes a known abbreviation or a single initial ('P. P. Henry')."""
    if text[end-1] in "。．！？!?": return True
    head = text[max(0, end-12):end-1]
    tail = re.split(r"[\s(\[\"'—-]", head)[-1].lower()
    if tail in _ABBREV: return False
    if len(tail) <= 1: return False            # initials: 'P.' 'A.'
    nxt = text[end:end+2].lstrip()
    return not (nxt[:1].islower() and text[end-1] == ".")

def split_sentences(text: str) -> list[str]:
    out, start = [], 0
    for m in _END_RE.finditer(text):
        if not _is_real_end(text, m.end()): continue
        piece = text[start:m.end()].strip()
        if piece: out.append(piece)
        start = m.end()
    tail = text[start:].strip()
    if tail: out.append(tail)
    return out

def _hard_split(sentence: str, tok, budget: int = TOKEN_BUDGET) -> list[str]:
    """A single sentence longer than the budget: cut on token boundaries."""
    enc = tok(sentence, add_special_tokens=False, return_offsets_mapping=True)
    offs = enc["offset_mapping"]
    out = []
    for i in range(0, len(offs), budget):
        win = offs[i:i + budget]
        piece = sentence[win[0][0]:win[-1][1]].strip()
        if piece: out.append(piece)
    return out

def chunk_lines(text: str, tok=None, reserve: int = 0) -> list[str]:
    """For the facts stream: each line is an atomic unit (an infobox row), packed to the budget.
    Never cuts inside a line, so 'colour index (B-V): 0.705' cannot be severed from its key."""
    tok = tok or _tok()
    lines = [l for l in (x.strip() for x in text.split("\n")) if len(l) >= 2]
    if not lines: return []
    budget = max(64, TOKEN_BUDGET - reserve)
    lens = [len(x) for x in tok(lines, add_special_tokens=False)["input_ids"]]
    out, buf, blen = [], [], 0
    for ln, L in zip(lines, lens):
        if L > budget:
            if buf: out.append("\n".join(buf)); buf, blen = [], 0
            out.extend(_hard_split(ln, tok, budget)); continue
        if buf and blen + L > budget:
            out.append("\n".join(buf)); buf, blen = [], 0
        buf.append(ln); blen += L
    if buf: out.append("\n".join(buf))
    return [c for c in out if len(c) >= MIN_CHUNK_CHARS]

def chunk_text(text: str, tok=None, reserve: int = 0) -> list[str]:
    """B+: pack whole sentences up to TOKEN_BUDGET - reserve ME5 tokens. No overlap.
    `reserve` = tokens the caller will prepend (title line) so the final chunk stays < 512."""
    if not text or len(text) < MIN_ARTICLE_CHARS: return []
    tok = tok or _tok()
    budget = max(64, TOKEN_BUDGET - reserve)
    sents = split_sentences(text)
    if not sents: return []
    lens = [len(x) for x in tok(sents, add_special_tokens=False)["input_ids"]]
    chunks, buf, blen = [], [], 0
    for s, L in zip(sents, lens):
        if L > budget:
            if buf: chunks.append(" ".join(buf)); buf, blen = [], 0
            chunks.extend(_hard_split(s, tok, budget))
            continue
        if buf and blen + L > budget:
            chunks.append(" ".join(buf)); buf, blen = [], 0
        buf.append(s); blen += L
    if buf: chunks.append(" ".join(buf))
    return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS]

# ── CPUワーカー ───────────────────────────────────────────────────────────────
def _worker_write_to_tmpfile(args: tuple) -> tuple[str, int, int]:
    zim_path, start, end, w_max, worker_id, tmp_dir = args
    tmp_path = os.path.join(tmp_dir, f"worker_{worker_id:03d}.jsonl.gz")
    try:
        archive = libzim.Archive(zim_path)
    except Exception as e:
        print(f"  [worker {worker_id}] open failed: {e}", flush=True)
        return tmp_path, 0, 0
    tok = _tok()
    article_count = chunk_count = 0
    with gzip.open(tmp_path, "wt", encoding="utf-8") as f:
        for entry_id in range(start, end):
            if w_max and article_count >= w_max: break
            try:
                entry = archive._get_entry_by_id(entry_id)
                if entry.is_redirect: continue
                item = entry.get_item()
                if "html" not in str(item.mimetype).lower(): continue
                raw  = bytes(item.content).decode("utf-8", errors="ignore")
                text = extract_text(raw)
                if len(text) < MIN_ARTICLE_CHARS: continue
                url = f"{WIKI_URL_BASE}{entry.path.replace(' ','_')}"
                title = entry.title
                reserve = len(tok(title, add_special_tokens=False)["input_ids"]) + 4
                prose, facts = split_prose_facts(text)
                pieces = chunk_text(prose, tok, reserve) + chunk_lines(facts, tok, reserve)
                if not pieces: continue
                for ci, chunk in enumerate(pieces):
                    chunk = f"{title}\n{chunk}"
                    f.write(json.dumps({
                        "title": title, "url": url,
                        "text": chunk, "chunk_index": ci,
                        "license": "CC BY-SA 4.0",
                    }, ensure_ascii=False) + "\n")
                    chunk_count += 1
                article_count += 1
            except Exception:
                continue
    print(f"  [worker {worker_id}] done: {article_count:,} articles {chunk_count:,} chunks", flush=True)
    return tmp_path, article_count, chunk_count

# ── Stage 1: ZIM → chunks.jsonl.gz ──────────────────────────────────────────
def stage1_zim_to_chunks(zim_path, chunks_path, manifest_path, max_articles, n_workers):
    print(f"[Stage 1] ZIM → chunks.jsonl.gz  workers={n_workers}")
    archive     = libzim.Archive(zim_path)
    entry_count = archive.entry_count
    art_count   = archive.article_count
    print(f"  entry_count={entry_count:,}  article_count={art_count:,}")
    del archive

    tmp_dir    = str(chunks_path.parent / "tmp_workers")
    os.makedirs(tmp_dir, exist_ok=True)
    chunk_size = entry_count // n_workers
    ranges = []
    for i in range(n_workers):
        s     = i * chunk_size
        e     = entry_count if i == n_workers-1 else (i+1)*chunk_size
        w_max = (max_articles // n_workers) if max_articles else 0
        ranges.append((zim_path, s, e, w_max, i, tmp_dir))

    print(f"  Launching {n_workers} workers...")
    t0 = time.time()
    with mp.Pool(processes=n_workers) as pool:
        results = pool.map(_worker_write_to_tmpfile, ranges)

    total_art = sum(r[1] for r in results)
    total_chk = sum(r[2] for r in results)
    print(f"  Workers done: {total_art:,} articles {total_chk:,} chunks ({time.time()-t0:.0f}s)")

    print(f"  Merging {n_workers} tmp files (content-hash ids, exact dedup)...")
    chunk_count = 0
    seen_hashes = set()
    dropped_dupes = 0
    with gzip.open(chunks_path, "wt", encoding="utf-8") as f_out:
        for tmp_path, _, _ in results:
            if not os.path.exists(tmp_path): continue
            with gzip.open(tmp_path, "rt", encoding="utf-8") as f_in:
                for line in f_in:
                    try:
                        meta = json.loads(line)
                        h = hashlib.sha1(meta["text"].encode("utf-8")).hexdigest()[:20]
                        if h in seen_hashes:
                            dropped_dupes += 1
                            continue
                        seen_hashes.add(h)
                        meta["chunk_id"] = h
                        f_out.write(json.dumps(meta, ensure_ascii=False) + "\n")
                        chunk_count += 1
                    except Exception:
                        continue
            os.remove(tmp_path)
    try: os.rmdir(tmp_dir)
    except: pass
    print(f"  Merge done: {chunk_count:,} chunks ({dropped_dupes:,} exact duplicates dropped)")
    del seen_hashes

    manifest_path.write_text(json.dumps({
        "stage1_done": True, "chunk_count": chunk_count,
        "zim_source": Path(zim_path).name, "n_workers": n_workers,
        "extractor": "render_faithful_v3 (zim-footer, head/h1 title, HTML entities, inline-tag spacing; navbox by markup; no CJK-space rule)",
        "title_prefix": True, "prose_facts_split": True,
        "chunker": "bplus_sentence_token_budget", "token_budget": TOKEN_BUDGET,
        "min_chunk_chars": MIN_CHUNK_CHARS, "min_article_chars": MIN_ARTICLE_CHARS, "overlap": 0,
        "dedup": "exact sha1-20 over chunk text", "dropped_duplicates": dropped_dupes,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    return chunk_count

# ── FAISS Training（保存・再利用）────────────────────────────────────────────
def load_or_train_index(chunks_path, trained_path, chunk_count, batch_size, model, pool):
    nlist     = min(NLIST, chunk_count // 10)
    quantizer = faiss.IndexFlatIP(DIM)
    index     = faiss.IndexIVFScalarQuantizer(quantizer, DIM, nlist, faiss.ScalarQuantizer.QT_4bit, faiss.METRIC_INNER_PRODUCT)

    CLIP = (0.001, 0.999)   # residual-quantile range (see reindex_sq4.py for the measurement)
    if trained_path.exists():
        print(f"\n  [FAISS Training] 保存済みを読み込み: {trained_path.name}")
        index = faiss.read_index(str(trained_path))
        return index, nlist

    train_size = min(chunk_count, nlist * 64)
    print(f"\n  [FAISS Training] {train_size:,} samples...")
    # Uniform stride across the whole corpus. The file is in ZIM (≈alphabetical) order, so
    # taking the first N lines would train the IVF centroids on titles starting with "A".
    stride = max(1, chunk_count // train_size)
    train_texts = []
    with gzip.open(chunks_path, "rt", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if len(train_texts) >= train_size: break
            if i % stride: continue
            try: train_texts.append(json.loads(line)["text"])
            except: continue
    train_texts = [PASSAGE_PREFIX + t for t in train_texts]
    if pool:
        train_emb = model.encode(train_texts, batch_size=batch_size,
                                 show_progress_bar=True, convert_to_numpy=True, pool=pool)
    else:
        train_emb = model.encode(train_texts, batch_size=batch_size,
                                 show_progress_bar=True, convert_to_numpy=True)

    train_emb = np.array(train_emb, dtype=np.float32)
    faiss.normalize_L2(train_emb)
    index.train(train_emb)
    if getattr(index, "by_residual", False):
        _, assign = index.quantizer.search(train_emb, 1)
        cent = faiss.rev_swig_ptr(faiss.downcast_index(index.quantizer).get_xb(), nlist * DIM).reshape(nlist, DIM)
        resid = train_emb - cent[assign[:, 0]]
        lo = np.quantile(resid, CLIP[0], axis=0).astype("float32")
        hi = np.quantile(resid, CLIP[1], axis=0).astype("float32")
        faiss.copy_array_to_vector(np.concatenate([lo, hi - lo]).astype("float32"), index.sq.trained)
        print(f"  quantiser range refit on residuals, clipped to {CLIP}", flush=True)
        del resid
    del train_texts, train_emb

    faiss.write_index(index, str(trained_path))
    print(f"  Training saved: {trained_path.name}")
    return index, nlist

# ── Stage 2: チェックポイント方式パイプライン ─────────────────────────────────
def stage2_checkpoint_pipeline(chunks_path, out_dir, manifest_path,
                                chunk_count, batch_size, model):
    gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
    buf_size  = calc_buffer_size()
    ram_gb    = buf_size * 3200 / 1e9

    print(f"\n[Stage 2] チェックポイント方式パイプライン")
    print(f"  RAM available:  {psutil.virtual_memory().available/1e9:.1f}GB")
    print(f"  Buffer size:    {buf_size:,} chunks ({ram_gb:.1f}GB)")
    print(f"  GPU:            {gpu_count}")
    print(f"  Total chunks:   {chunk_count:,}")
    print(f"  Parts:          {N_PARTS}")

    pool = None
    if gpu_count >= 2:
        pool = model.start_multi_process_pool(target_devices=["cuda:0","cuda:1"])
        print(f"  Multi-GPU pool: cuda:0 + cuda:1")

    trained_path = out_dir / "wiki_index_trained.faiss"
    base_index, nlist = load_or_train_index(
        chunks_path, trained_path, chunk_count, batch_size, model, pool)

    # Part範囲を計算
    part_size = chunk_count // N_PARTS
    parts = []
    for i in range(N_PARTS):
        s = i * part_size
        e = chunk_count if i == N_PARTS-1 else (i+1)*part_size
        parts.append((s, e))

    t_total   = time.time()
    completed = []

    # 全体進捗バー
    total_bar = tqdm(total=chunk_count, desc="[Total]",
                     unit="chunks", position=0,
                     bar_format="{desc}: {percentage:3.0f}%|{bar:20}| "
                                "{n_fmt}/{total_fmt} {rate_fmt} ETA {remaining}")

    for part_idx, (p_start, p_end) in enumerate(parts):
        part_num  = part_idx + 1
        part_path = out_dir / f"faiss_part{part_num}.faiss"

        if part_path.exists():
            part_size_actual = p_end - p_start
            print(f"\n  [Part {part_num}/{N_PARTS}] スキップ（完了済み）: {part_path.name}")
            total_bar.update(part_size_actual)
            completed.append(part_path)
            continue

        print(f"\n  [Part {part_num}/{N_PARTS}] {p_start:,} 〜 {p_end:,} ({p_end-p_start:,} chunks)")

        # 訓練済みインデックスを読み込み（このPartのベース）
        part_index = faiss.read_index(str(trained_path))

        part_bar = tqdm(total=p_end-p_start,
                        desc=f"[Part {part_num}/{N_PARTS}]",
                        unit="chunks", position=1, leave=False,
                        bar_format="{desc}: {percentage:3.0f}%|{bar:20}| "
                                   "{n_fmt}/{total_fmt} {rate_fmt} ETA {remaining}")

        def flush(texts):
            if not texts: return
            texts = [PASSAGE_PREFIX + t for t in texts]
            if pool:
                emb = model.encode(texts, batch_size=batch_size,
                                   show_progress_bar=False,
                                   convert_to_numpy=True, pool=pool)
            else:
                emb = model.encode(texts, batch_size=batch_size,
                                   show_progress_bar=False, convert_to_numpy=True)
            emb = np.array(emb, dtype=np.float32)
            faiss.normalize_L2(emb)
            part_index.add(emb)
            emb_f.write(emb.astype(np.float16).tobytes())   # keep vectors: re-index any type without re-embedding
            del emb
            del texts

        buf_texts  = []
        global_idx = 0
        t_part     = time.time()
        emb_f = open(out_dir / f"emb_part{part_num}.f16", "wb")   # truncated: a part always restarts from scratch

        with gzip.open(chunks_path, "rt", encoding="utf-8") as f:
            for line in f:
                if global_idx < p_start:
                    global_idx += 1
                    continue
                if global_idx >= p_end:
                    break
                try:
                    buf_texts.append(json.loads(line)["text"])
                except Exception as exc:          # never skip silently: that shifts every later vector
                    raise SystemExit(f"stage2: unparsable line at global_idx={global_idx}: {exc}")
                global_idx += 1

                if len(buf_texts) >= buf_size:
                    n = len(buf_texts)
                    flush(buf_texts)
                    buf_texts = []
                    part_bar.update(n)
                    total_bar.update(n)
                    ram_now = psutil.virtual_memory().available / 1e9
                    tqdm.write(f"  [Part {part_num}] {part_index.ntotal:,} vectors "
                               f"RAM={ram_now:.1f}GB")

        if buf_texts:
            n = len(buf_texts)
            flush(buf_texts)
            part_bar.update(n)
            total_bar.update(n)

        part_bar.close()

        # Part保存
        emb_f.close()
        faiss.write_index(part_index, str(part_path))
        elapsed = time.time() - t_part
        print(f"\n  [Part {part_num}] 保存完了: {part_path.name} "
              f"({part_index.ntotal:,} vectors, {elapsed:.0f}s)")
        completed.append(part_path)
        del part_index

    total_bar.close()

    if pool:
        model.stop_multi_process_pool(pool)

    # Stage 3: マージ
    print(f"\n[Stage 3] {N_PARTS}パートをマージ...")
    final_path = out_dir / "wiki_index_ivfpq_me5.faiss"
    merged = faiss.read_index(str(completed[0]))
    for p in completed[1:]:
        idx = faiss.read_index(str(p))
        merged.merge_from(idx, merged.ntotal)
        del idx
        print(f"  merged: {p.name} → total {merged.ntotal:,}")

    faiss.write_index(merged, str(final_path))
    index_gb  = final_path.stat().st_size / 1e9
    memory_gb = round(chunk_count * SQ_BYTES / 1e9, 3)
    print(f"  wiki_index_ivfpq.faiss: {index_gb:.2f}GB (~{memory_gb:.2f}GB in memory)")

    # 後片付け
    for p in completed:
        p.unlink()
    CLIP = (0.001, 0.999)   # residual-quantile range (see reindex_sq4.py for the measurement)
    if trained_path.exists():
        trained_path.unlink()
    print(f"  チェックポイントファイル削除完了")

    # manifest更新
    manifest = json.loads(manifest_path.read_text())
    manifest.update({
        "stage2_done": True, "model": MODEL_NAME,
        "passage_prefix": PASSAGE_PREFIX, "metric": "INNER_PRODUCT",
        "wiki_url_base": WIKI_URL_BASE,
        "dim": DIM, "index_type": "IndexIVFScalarQuantizer", "quantizer": "QT_4bit", "index_kind": INDEX_KIND, "range_fit": "residual quantiles 0.001-0.999",
        "nlist": nlist, "bytes_per_vector": SQ_BYTES, "recommended_nprobe": 128,
        "embeddings_fp16": "emb_part{1..N}.f16 — raw float16, 1024 dims, row-major, index-aligned (re-index without re-embedding)",
        "buffer_size_chunks": buf_size,
        "index_size_gb": round(index_gb, 3),
        "chunks_size_gb": round(chunks_path.stat().st_size / 1e9, 3),
        "index_memory_gb": memory_gb,
        "gpu_count": gpu_count, "batch_size_used": batch_size,
        "n_parts": N_PARTS,
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    total_elapsed = time.time() - t_total
    print(f"\n=== Build complete ===")
    print(f"  Total vectors: {merged.ntotal:,}")
    print(f"  Index:         {index_gb:.2f}GB")
    print(f"  Memory:        ~{memory_gb:.2f}GB")
    print(f"  Total time:    {total_elapsed/3600:.1f}h")

# ── メイン ────────────────────────────────────────────────────────────────────
def build(zim_path, out_dir, batch_size, max_articles, skip_stage1, n_workers):
    out           = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chunks_path   = out / "wiki_chunks.jsonl.gz"
    manifest_path = out / "wiki_manifest.json"

    if skip_stage1 and chunks_path.exists() and manifest_path.exists():
        print(f"[Stage 1] Skipped (--skip-stage1)")
        chunk_count = json.loads(manifest_path.read_text())["chunk_count"]
        print(f"  chunk_count: {chunk_count:,}")
    else:
        chunk_count = stage1_zim_to_chunks(
            zim_path, chunks_path, manifest_path, max_articles, n_workers)

    print()
    print("[Loading embedding model...]")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  device={device}  GPUs={torch.cuda.device_count()}")
    # fp16: 2.9x faster on this GPU, same-text cosine vs fp32 > 0.9999 (measured 2026-09-14)
    model = SentenceTransformer(MODEL_NAME, device=device, model_kwargs={"torch_dtype": torch.float16})
    if device == "cuda":
        model = model.half()   # fp16 inference for throughput; vectors are PQ-quantized anyway
        print("  fp16 enabled (model.half())")

    for bs in [batch_size, batch_size//2, 256, 128, 64]:
        try:
            model.encode(["test"] * bs, batch_size=bs, show_progress_bar=False)
            if torch.cuda.is_available(): torch.cuda.empty_cache()
            print(f"  batch_size={bs} OK")
            batch_size = bs
            break
        except RuntimeError:
            if torch.cuda.is_available(): torch.cuda.empty_cache()

    stage2_checkpoint_pipeline(
        chunks_path, out, manifest_path, chunk_count, batch_size, model)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="MOBIUS Phase C — Wikipedia Index Builder v10")
    ap.add_argument("--zim",          required=True)
    ap.add_argument("--out",          default="data/box_b/")
    ap.add_argument("--batch-size",   type=int, default=DEFAULT_BATCH)
    ap.add_argument("--max-articles", type=int, default=0)
    ap.add_argument("--skip-stage1",  action="store_true")
    ap.add_argument("--workers",      type=int, default=max(1, mp.cpu_count()-2))
    ap.add_argument("--lang",         default="en",
                    help="Wikipedia language code for URL base (e.g. ja, zh, en)")
    args = ap.parse_args()

    WIKI_URL_BASE = f"https://{args.lang}.wikipedia.org/wiki/"

    max_str   = 'ALL' if not args.max_articles else f'{args.max_articles:,}'
    ram_total = psutil.virtual_memory().total / 1e9
    ram_avail = psutil.virtual_memory().available / 1e9
    buf_size  = calc_buffer_size()

    print("================================================================")
    print(" MOBIUS Phase C — Box B: Wikipedia Index Builder v10")
    print("================================================================")
    print(f" ZIM:         {args.zim}")
    print(f" Out:         {args.out}")
    print(f" Batch:       {args.batch_size}")
    print(f" Max:         {max_str}")
    print(f" Workers:     {args.workers} / {mp.cpu_count()} cores")
    print(f" RAM:         {ram_avail:.1f}GB avail / {ram_total:.1f}GB total")
    print(f" Buffer:      {buf_size:,} chunks ({buf_size*3200/1e9:.1f}GB)")
    print(f" Skip Stage1: {args.skip_stage1}")
    print(f" Parts:       {N_PARTS}（チェックポイント方式）")
    print()

    build(args.zim, args.out, args.batch_size,
          args.max_articles, args.skip_stage1, args.workers)
