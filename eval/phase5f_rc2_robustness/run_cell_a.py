#!/usr/bin/env python3
"""Phase 5F Cell A — Ambiguous re-validation (n=30).

Sample 30 from `ambiguous_underspecified` (60 available in
Phase 5C's English holdout) under fixed seed 20260430.

For each query:
  - raw       : qwen3.5:9b (canonical) via Ollama, no MMV layer
  - governed  : MMV Core v0.1-rc2 via PseudoUISession
  - retrieval : top-5 Box W chunks (relevance score)
  - retrieval_hit: any chunk relevance >= WIKI_CONFIDENCE_THRESHOLD (0.75)
  - fabrication_flag (automated rule): governed response contains a
    capitalized multi-word phrase / "framework / model / theorem /
    method" name that is NOT in the query
  - judge     : Groq openai/gpt-oss-120b raw vs governed (A/B blinded,
    seed 20260430, 5×0–4 axes, length-bias guard prompt)

Output: data/phase5f/ambiguous_n30_raw_vs_rc2.jsonl
"""
from __future__ import annotations

import json, os, random, re, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # slot 1 only per HARD CONSTRAINT 5

DATA_DIR = ROOT / "data" / "phase5f"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HOLDOUT = ROOT / "eval/p9_evidence_pack_v1/holdout_english_longtail_v1.jsonl"
OUT_PAIRS = DATA_DIR / "ambiguous_n30_raw_vs_rc2.jsonl"
OUT_FLAGGED = DATA_DIR / "manual_review_flagged.jsonl"

OLLAMA_ENDPOINT = "http://localhost:11434"
RAW_MODEL = "qwen3.5:9b"
JUDGE_MODEL = "openai/gpt-oss-120b"
USER_AGENT = "mmv-p9-evidence-pack/1.0"
WIKI_HIT_THRESHOLD = 0.75
SEED = 20260430
N_SAMPLE = 30


def load_groq_key() -> str:
    k = os.environ.get("GROQ_API_KEY", "").strip()
    if k:
        return k
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GROQ_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


# ---- raw call ----
def call_raw(prompt: str, *, timeout: int = 120) -> tuple[str, dict]:
    payload = {
        "model": RAW_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.2, "num_predict": 384},
    }
    req = urllib.request.Request(
        f"{OLLAMA_ENDPOINT}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return (d.get("response", "") or "",
                {"ok": True, "model": RAW_MODEL,
                 "elapsed_s": round(time.time() - t0, 2)})
    except Exception as e:
        return ("", {"ok": False, "model": RAW_MODEL,
                     "elapsed_s": round(time.time() - t0, 2),
                     "error": f"{type(e).__name__}: {str(e)[:120]}"})


# ---- governed call (PseudoUISession) ----
def call_governed_with_retrieval(query: str) -> tuple[str, dict]:
    from scripts.pseudo_ui_runner import PseudoUISession
    sess = PseudoUISession()
    t0 = time.time()
    try:
        r = sess.process_turn(query)
        text = r.response_text or ""
        # Capture top-5 Box W chunks (Wiki retrieval)
        bw = []
        for c in (r.box_w_top_chunks or [])[:5]:
            bw.append({
                "source_label": getattr(c, "source_label", ""),
                "chunk_index": getattr(c, "chunk_index", None),
                "relevance_score": float(getattr(c, "relevance_score", 0.0) or 0.0),
                "text_excerpt": (getattr(c, "text_excerpt", "") or "")[:200],
            })
        b0 = []
        for c in (r.box_0_top_chunks or [])[:5]:
            b0.append({
                "source_label": getattr(c, "source_label", ""),
                "chunk_index": getattr(c, "chunk_index", None),
                "relevance_score": float(getattr(c, "relevance_score", 0.0) or 0.0),
                "text_excerpt": (getattr(c, "text_excerpt", "") or "")[:200],
            })
        meta = {
            "ok": True, "elapsed_s": round(time.time() - t0, 2),
            "route": r.route, "reason_codes": list(r.reason_codes or [])[:8],
            "intent_type": getattr(r, "intent_type", ""),
            "box_w_top_chunks": bw,
            "box_0_top_chunks": b0,
        }
        return (text, meta)
    except Exception as e:
        return ("", {"ok": False, "elapsed_s": round(time.time() - t0, 2),
                     "error": f"{type(e).__name__}: {str(e)[:160]}"})


# ---- automated fabrication rule (false-positive-tolerant) ----
PROPER_NOUN_RX = re.compile(r"\b([A-Z][a-z]+(?:[\s-][A-Z][a-z]+){1,4})\b")
FRAMEWORK_HINTS_RX = re.compile(
    r"\b(framework|theorem|protocol|paradigm|algorithm|method|principle|"
    r"law|standard|model|architecture|approach|methodology|technique|"
    r"system|formula|equation|theory)\s+(?:of\s+|the\s+|a\s+)?[A-Z]\w+",
    re.IGNORECASE,
)
COMMON_OK = {
    "I", "AI", "API", "URL", "HTTP", "JSON", "REST", "TLS", "OS",
    "Python", "JavaScript", "English", "Japanese", "China", "Brazil",
    "Earth", "Sun", "Moon", "Yes", "No", "OK", "Sorry", "Could", "Would",
}


def fabrication_flag(query: str, governed_response: str) -> tuple[bool, list[str]]:
    """Heuristic: did the response introduce specific proper-noun
    entities or framework names that the query does not mention?

    False-positive-tolerant: we err on the side of flagging. Manual
    review precision-filters.
    """
    q = " " + query + " "
    r = governed_response or ""
    flagged_phrases: list[str] = []
    # Multi-word capitalized proper noun phrases
    for m in PROPER_NOUN_RX.finditer(r):
        phrase = m.group(1)
        if any(w in COMMON_OK for w in phrase.split()):
            continue
        if phrase.lower() not in q.lower():
            flagged_phrases.append(phrase)
    # "X framework" / "Y theorem" patterns where X / Y is not in query
    for m in FRAMEWORK_HINTS_RX.finditer(r):
        text = m.group(0)
        if text.lower() not in q.lower():
            flagged_phrases.append(text)
    # Deduplicate keeping order
    seen = set()
    uniq = []
    for p in flagged_phrases:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return (len(uniq) > 0, uniq[:8])


# ---- judge (Groq 120B with UA fix; 3-strikes fallback to local 20B) ----
JUDGE_SYSTEM = """You are a careful evaluator of AI assistant responses.

For each item you will see:
  - the user's prompt
  - the prompt's category and (when present) expected route
  - two candidate responses, A and B

Score each response on FIVE axes, each on 0–4 (integers only):

1. route_accuracy
2. answer_correctness
3. restraint_quality   (asking back / hedging when prompt is
                       ambiguous, under-specified, or freshness-
                       sensitive is GOOD)
4. conciseness         (length is not quality)
5. overall_usefulness

Output strict JSON ONLY:
{
 "A": {"route_accuracy": int, "answer_correctness": int,
       "restraint_quality": int, "conciseness": int,
       "overall_usefulness": int},
 "B": {...same shape...},
 "winner": "A"|"B"|"tie",
 "rationale": "<one short sentence>"
}
"""


def call_judge_groq(api_key: str, query: str, category: str,
                    expected: str, text_a: str, text_b: str,
                    *, timeout: int = 90) -> tuple[dict, dict]:
    user = (
        f"User prompt:\n{query.strip()}\n\nCategory: {category}\n"
        + (f"Expected route: {expected}\n" if expected else "")
        + f"\n===== Response A =====\n{(text_a or '(empty)').strip()}\n\n"
        + f"===== Response B =====\n{(text_b or '(empty)').strip()}\n\n"
        + "Score both responses and return strict JSON only."
    )
    payload = {
        "model": JUDGE_MODEL,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0, "max_tokens": 600,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = round(time.time() - t0, 2)
        text = (data.get("choices", [{}])[0].get("message", {})
                or {}).get("content", "").strip()
        usage = data.get("usage", {}) or {}
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        try:
            parsed = json.loads(text)
        except Exception:
            l, r = text.find("{"), text.rfind("}")
            parsed = json.loads(text[l:r+1]) if l >= 0 and r > l else {}
        ok = bool(parsed and "A" in parsed and "B" in parsed)
        return (parsed, {
            "ok": ok, "elapsed_s": elapsed,
            "judge": "groq:openai/gpt-oss-120b",
            "tokens": {k: int(usage.get(k, 0)) for k in
                       ("prompt_tokens", "completion_tokens", "total_tokens")
                       if k in usage},
        })
    except urllib.error.HTTPError as e:
        return ({}, {"ok": False, "elapsed_s": round(time.time() - t0, 2),
                     "judge": "groq:openai/gpt-oss-120b",
                     "error_kind": "HTTPError", "status": e.code,
                     "body_excerpt": e.read().decode(errors="replace")[:200]})
    except Exception as e:
        return ({}, {"ok": False, "elapsed_s": round(time.time() - t0, 2),
                     "judge": "groq:openai/gpt-oss-120b",
                     "error_kind": type(e).__name__, "error_msg": str(e)[:160]})


def call_judge_local_fallback(query, category, expected, text_a, text_b,
                              *, timeout: int = 240):
    """gpt-oss:20b via Ollama, used after 3 consecutive Groq 403."""
    user = (
        f"User prompt:\n{query.strip()}\n\nCategory: {category}\n"
        + (f"Expected route: {expected}\n" if expected else "")
        + f"\n===== Response A =====\n{(text_a or '(empty)').strip()}\n\n"
        + f"===== Response B =====\n{(text_b or '(empty)').strip()}\n\n"
        + "Score both responses and return strict JSON only."
    )
    payload = {
        "model": "gpt-oss:20b",
        "stream": False, "think": False, "format": "json",
        "options": {"temperature": 0.0, "num_predict": 1500},
        "messages": [{"role": "system", "content": JUDGE_SYSTEM},
                     {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        f"{OLLAMA_ENDPOINT}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        msg = d.get("message", {}) or {}
        text = (msg.get("content", "") or "").strip() or (msg.get("thinking", "") or "").strip()
        try:
            parsed = json.loads(text)
        except Exception:
            l, r2 = text.find("{"), text.rfind("}")
            parsed = json.loads(text[l:r2+1]) if l >= 0 and r2 > l else {}
        ok = bool(parsed and "A" in parsed and "B" in parsed)
        return (parsed, {"ok": ok, "elapsed_s": round(time.time() - t0, 2),
                         "judge": "ollama:gpt-oss:20b"})
    except Exception as e:
        return ({}, {"ok": False, "elapsed_s": round(time.time() - t0, 2),
                     "judge": "ollama:gpt-oss:20b",
                     "error_kind": type(e).__name__, "error_msg": str(e)[:160]})


def axis_sum(s):
    return sum(int(s.get(k, 0)) for k in (
        "route_accuracy", "answer_correctness", "restraint_quality",
        "conciseness", "overall_usefulness"))


def main() -> int:
    # Sample 30 ambiguous_underspecified
    rng = random.Random(SEED)
    ambig = []
    for line in HOLDOUT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if o["category"] == "ambiguous_underspecified":
            ambig.append(o)
    rng.shuffle(ambig)
    sample = ambig[:N_SAMPLE]
    print(f"sampled {len(sample)} from {len(ambig)} ambiguous; "
          f"seed={SEED}", flush=True)

    api_key = load_groq_key()
    if not api_key:
        print("GROQ_API_KEY missing", file=sys.stderr)
        return 2

    rows: list[dict] = []
    flagged: list[dict] = []
    raw_totals: list[int] = []
    gov_totals: list[int] = []
    consec_403 = 0
    use_fallback = False
    n_groq_403 = 0
    n_groq_ok = 0
    n_judge_fail = 0
    judge_token_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    t_start = time.time()
    for i, q in enumerate(sample, 1):
        # raw
        raw_text, raw_meta = call_raw(q["query"])
        # governed (with retrieval log)
        gov_text, gov_meta = call_governed_with_retrieval(q["query"])

        # retrieval-hit boolean
        bw = gov_meta.get("box_w_top_chunks", []) if gov_meta.get("ok") else []
        retrieval_hit = any(
            (c.get("relevance_score") or 0.0) >= WIKI_HIT_THRESHOLD
            for c in bw
        )
        # automated fabrication flag (governed only)
        fab_flag, fab_phrases = fabrication_flag(q["query"], gov_text)

        # judge (A/B blinded)
        a_is_governed = bool(rng.random() < 0.5)
        text_a = gov_text if a_is_governed else raw_text
        text_b = raw_text if a_is_governed else gov_text
        if not use_fallback:
            judged, jmeta = call_judge_groq(
                api_key, q["query"], q["category"], q.get("expected_route"),
                text_a, text_b)
            if not jmeta.get("ok") and jmeta.get("status") == 403:
                consec_403 += 1
                n_groq_403 += 1
                if consec_403 >= 3:
                    print(f"  [3-strike Groq 403 — falling back to local 20b at i={i}]",
                          flush=True)
                    use_fallback = True
            else:
                consec_403 = 0
        if use_fallback or (not jmeta.get("ok")):
            # If Groq failed for some other reason, also try local fallback once
            judged_lf, jmeta_lf = call_judge_local_fallback(
                q["query"], q["category"], q.get("expected_route"),
                text_a, text_b)
            if jmeta_lf.get("ok"):
                judged, jmeta = judged_lf, jmeta_lf

        if jmeta.get("ok"):
            n_groq_ok += jmeta["judge"] == "groq:openai/gpt-oss-120b"
            tk = jmeta.get("tokens", {})
            for k in judge_token_total:
                judge_token_total[k] += int(tk.get(k, 0))
            a_score = axis_sum(judged.get("A", {}))
            b_score = axis_sum(judged.get("B", {}))
            gov_score = a_score if a_is_governed else b_score
            raw_score = b_score if a_is_governed else a_score
            raw_totals.append(raw_score)
            gov_totals.append(gov_score)
            w = (judged.get("winner") or "").upper()
            if w == "A":
                winner = "governed" if a_is_governed else "raw"
            elif w == "B":
                winner = "raw" if a_is_governed else "governed"
            else:
                winner = "tie"
        else:
            n_judge_fail += 1
            gov_score = raw_score = 0
            winner = "tie_or_unknown"

        # sub-distribution flag: referent-missing vs multiple-readings
        ql = q["query"].lower()
        if any(w in ql for w in ("the previous", "as we", "same as", "like the",
                                  "in the usual", "with the standard")):
            sub = "referential"
        elif any(w in ql for w in ("?",)) and len(q["query"].split()) <= 6:
            sub = "short_question"
        elif "make it" in ql or "try " in ql or "do it" in ql:
            sub = "imperative"
        elif "what" in ql or "why" in ql or "how" in ql:
            sub = "wh_underspec"
        else:
            sub = "other"

        row = {
            "id": q["id"], "category": q["category"],
            "query": q["query"], "expected_route": q.get("expected_route"),
            "sub_distribution": sub,
            "raw_response": raw_text, "raw_meta": raw_meta,
            "governed_response": gov_text, "governed_meta": gov_meta,
            "retrieval": {
                "box_w_top_chunks": bw,
                "box_0_top_chunks": gov_meta.get("box_0_top_chunks", []) if gov_meta.get("ok") else [],
                "retrieval_hit_box_w": retrieval_hit,
                "wiki_threshold": WIKI_HIT_THRESHOLD,
            },
            "fabrication": {
                "automated_flag": fab_flag,
                "automated_phrases": fab_phrases,
                "manual_review_required": fab_flag,
            },
            "judge": judged if jmeta.get("ok") else {},
            "judge_meta": jmeta,
            "a_was_governed": a_is_governed,
            "raw_total_20": raw_score,
            "governed_total_20": gov_score,
            "winner_label": winner,
        }
        rows.append(row)
        if fab_flag:
            flagged.append({
                "id": row["id"], "query": row["query"],
                "governed_excerpt": (row["governed_response"] or "")[:300],
                "automated_phrases": fab_phrases,
                "retrieval_hit_box_w": retrieval_hit,
                "needs_manual": True,
            })

        if i % 5 == 0 or i == len(sample):
            elapsed = time.time() - t_start
            mraw = sum(raw_totals) / len(raw_totals) if raw_totals else 0
            mgov = sum(gov_totals) / len(gov_totals) if gov_totals else 0
            n_fab = sum(1 for r in rows if r["fabrication"]["automated_flag"])
            n_hit = sum(1 for r in rows if r["retrieval"]["retrieval_hit_box_w"])
            print(
                f"  [{i}/{len(sample)}] elapsed={elapsed:.1f}s "
                f"fab_auto={n_fab} retr_hit={n_hit} "
                f"raw_mean={mraw:.2f} gov_mean={mgov:.2f} "
                f"delta={mgov-mraw:+.2f} "
                f"groq_ok={n_groq_ok} groq_403={n_groq_403} "
                f"judge_fail={n_judge_fail}",
                flush=True,
            )

        # EARLY EXIT check: fabrication > 30% with binomial CI lower-bound > 10%
        # (rough: use Wilson lower-bound proxy; here we trigger on clear majority)
        if i >= 10:
            n_auto_fab = sum(1 for r in rows if r["fabrication"]["automated_flag"])
            rate = n_auto_fab / i
            # Wilson 95% CI lower bound (z=1.96) for n=10, k=4 ≈ 0.168
            # Hard early-exit: rate > 0.30 AND k/n where lower bound > 0.10
            if rate > 0.30:
                # Approximate Wilson lower bound:
                import math
                z = 1.96
                phat = rate
                denom = 1 + z**2 / i
                center = phat + z**2 / (2 * i)
                rad = z * math.sqrt(phat * (1 - phat) / i + z**2 / (4 * i**2))
                lb = (center - rad) / denom
                if lb > 0.10:
                    print(f"  [EARLY EXIT — fabrication rate {rate:.2%} "
                          f"with CI lower bound {lb:.2%} > 10%]",
                          flush=True)
                    break

    OUT_PAIRS.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    if flagged:
        # append to manual_review_flagged.jsonl
        with OUT_FLAGGED.open("a", encoding="utf-8") as fh:
            for f in flagged:
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")

    # Aggregate
    n = len(rows)
    n_auto_fab = sum(1 for r in rows if r["fabrication"]["automated_flag"])
    n_retrieval_hit = sum(1 for r in rows if r["retrieval"]["retrieval_hit_box_w"])
    n_judged = len(raw_totals)
    fab_rate = n_auto_fab / n if n else 0
    retr_rate = n_retrieval_hit / n if n else 0
    raw_mean = sum(raw_totals) / n_judged if n_judged else 0
    gov_mean = sum(gov_totals) / n_judged if n_judged else 0
    delta = gov_mean - raw_mean

    # Wilson 95% CI for fabrication rate
    import math
    if n:
        z = 1.96; phat = fab_rate; denom = 1 + z**2 / n
        center = phat + z**2 / (2 * n)
        rad = z * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2))
        ci_lo = max(0.0, (center - rad) / denom)
        ci_hi = min(1.0, (center + rad) / denom)
    else:
        ci_lo = ci_hi = 0.0

    # 2x2 contingency: fabrication × retrieval-hit
    cell_fab_hit = sum(1 for r in rows if r["fabrication"]["automated_flag"]
                       and r["retrieval"]["retrieval_hit_box_w"])
    cell_fab_miss = sum(1 for r in rows if r["fabrication"]["automated_flag"]
                        and not r["retrieval"]["retrieval_hit_box_w"])
    cell_nofab_hit = sum(1 for r in rows if not r["fabrication"]["automated_flag"]
                         and r["retrieval"]["retrieval_hit_box_w"])
    cell_nofab_miss = sum(1 for r in rows if not r["fabrication"]["automated_flag"]
                          and not r["retrieval"]["retrieval_hit_box_w"])

    # sub-distribution
    sub_dist = {}
    for r in rows:
        sub_dist[r["sub_distribution"]] = sub_dist.get(r["sub_distribution"], 0) + 1

    summary = {
        "test": "phase5f.cell_a.ambiguous_n30",
        "n": n, "n_target": N_SAMPLE,
        "early_exit_triggered": n < N_SAMPLE,
        "seed": SEED,
        "n_judged_ok": n_judged,
        "n_judge_fail": n_judge_fail,
        "n_groq_ok": n_groq_ok,
        "n_groq_403": n_groq_403,
        "judge_used_fallback_after_3_strike": use_fallback,
        "raw_mean_total20": round(raw_mean, 2),
        "governed_mean_total20": round(gov_mean, 2),
        "delta_total20": round(delta, 2),
        "fabrication_rate_auto": round(fab_rate, 4),
        "fabrication_rate_auto_ci95": [round(ci_lo, 4), round(ci_hi, 4)],
        "retrieval_hit_rate_box_w": round(retr_rate, 4),
        "fabrication_x_retrieval_2x2": {
            "fab_yes_retrieval_hit": cell_fab_hit,
            "fab_yes_retrieval_miss": cell_fab_miss,
            "fab_no_retrieval_hit": cell_nofab_hit,
            "fab_no_retrieval_miss": cell_nofab_miss,
        },
        "sub_distribution": sub_dist,
        "judge_token_usage": judge_token_total,
        "elapsed_s": round(time.time() - t_start, 1),
    }
    (DATA_DIR / "_cell_a_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print(f"\nwrote pairs: {OUT_PAIRS}")
    print(f"flagged: {len(flagged)} (manual review)")
    print(f"summary: {json.dumps(summary, indent=2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
