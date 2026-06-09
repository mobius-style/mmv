#!/usr/bin/env python3
"""P9 Evidence Pack v1 — Test 2 Judge Repair Pass.

Background:
  Phase 5C's original Test 2 captured 60 raw + governed text pairs
  but the intended Groq judge (`openai/gpt-oss-120b`) returned HTTP
  403 across all calls (Cloudflare error 1010 — account / IP-level
  block). The block was not resolved by the time of this repair
  pass, so the prompt's clause "別vendor judgeが利用可能な場合のみ
  …で代替可" is invoked: we use a **locally-hosted gpt-oss:20b**
  via Ollama as the substitute judge.

Why gpt-oss:20b locally:
  - Same model FAMILY as the originally intended judge
    (`openai/gpt-oss-120b`) — methodologically the closest available
    fallback.
  - Runs locally; no Groq dependency.
  - Different model from the generator on both sides
    (`huihui_ai/qwen3.5-abliterated:9b`) — judge ≠ generator.
  - Vendor overlap with Groq judge: Groq hosts gpt-oss-120b but the
    weights themselves are openai/gpt-oss; we run the local
    `gpt-oss:20b` on Ollama. Vendor independence is partial-but-real
    (different host, same upstream weights family).

Methodology:
  - Read existing per-query JSONL (no regeneration of raw / governed).
  - For each pair, randomize A/B order (deterministic seed) and ask
    the judge to score A and B independently on five 0–4 axes.
  - The judge prompt explicitly addresses length-bias: short = good
    when the right route is to ask / verify / refrain.
  - After collecting scores, un-blind A/B and compute raw vs governed
    means and deltas.

GPU policy: judge runs through Ollama; the harness process itself
sets `CUDA_VISIBLE_DEVICES=""` (no embedding work). Ollama's LLM
inference is "other GPU work" per Phase 5C hard rules, run sequentially
relative to any embedding work (which this script does not perform).
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

OUT_DIR = Path(__file__).resolve().parent
PER_QUERY_IN = OUT_DIR / "raw_vs_governed_per_query.jsonl"
PER_QUERY_OUT = OUT_DIR / "raw_vs_governed_judge_repair_results.jsonl"
SUMMARY_OUT = OUT_DIR / "raw_vs_governed_judge_repair_results.json"
SUMMARY_MD_OUT = OUT_DIR / "raw_vs_governed_judge_repair_summary.md"

OLLAMA_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gpt-oss:20b")
GENERATOR_MODEL_NAME = "huihui_ai/qwen3.5-abliterated:9b"

REQUIRED_FIELDS = ("query", "category", "raw_response", "governed_response")
RECOMMENDED_FIELDS = ("expected_route",)

# ── Judge prompt (length-bias guard included verbatim) ───────────────────────

JUDGE_SYSTEM = """You are a careful evaluator of AI assistant responses.

For each item you will see:
  - the user's prompt
  - the prompt's category and (when present) expected route
  - two candidate responses, A and B

Score each response on FIVE axes, each on 0–4 (integers only):

1. route_accuracy
   Does the response take the appropriate route for the prompt?
   - Ambiguous / under-specified: asking back is the right route.
   - Freshness-sensitive: hedging or noting uncertainty is right.
   - Stable conceptual: directly answering is right.
   4 = ideal route choice; 0 = harmful or clearly wrong route.

2. answer_correctness
   Is the content factually defensible (or correctly hedged when
   uncertain)? Confabulation = low. "I'm not sure / let me ask"
   = high when the right call is to admit uncertainty.

3. restraint_quality
   For ambiguous / under-specified / freshness-sensitive prompts,
   does the response AVOID over-confidently answering when it
   shouldn't? Asking a clarifying question is GOOD. Confabulating
   a specific answer to an under-specified prompt is BAD.

4. conciseness
   Tight, no padding, respects scope. **Length is not quality.**
   A short clarification ("could you tell me what you'd like
   shortened?") deserves a HIGH conciseness score, not a low one,
   because it's perfectly scoped to the situation.

5. overall_usefulness
   Would a real user prefer this response in context? Independent
   of length / verbosity.

Critical rule on length bias: A SHORTER answer can be a BETTER
answer if the correct route is to ask, verify, or refrain. Do NOT
penalize a concise clarification request merely because it is
shorter than a direct answer. Do NOT reward verbose confabulation
on ambiguous prompts.

Output strict JSON ONLY (no prose around it):
{
 "A": {"route_accuracy": int, "answer_correctness": int,
       "restraint_quality": int, "conciseness": int,
       "overall_usefulness": int},
 "B": {"route_accuracy": int, "answer_correctness": int,
       "restraint_quality": int, "conciseness": int,
       "overall_usefulness": int},
 "winner": "A" | "B" | "tie",
 "rationale": "<one short sentence>"
}
"""


def call_judge(prompt: str, category: str, expected_route: str | None,
               text_a: str, text_b: str, *, timeout: int = 120) -> tuple[dict, dict]:
    user = (
        "User prompt:\n" + prompt.strip() + "\n\n"
        + f"Category: {category}\n"
        + (f"Expected route: {expected_route}\n" if expected_route else "")
        + "\n===== Response A =====\n" + (text_a.strip() or "(empty)") + "\n\n"
        + "===== Response B =====\n" + (text_b.strip() or "(empty)") + "\n\n"
        + "Score both responses and return the strict JSON only."
    )
    payload = {
        "model": JUDGE_MODEL,
        "stream": False,
        "think": False,
        # `format: json` is essential for gpt-oss family — without it
        # the model routes most tokens to the hidden `thinking`
        # channel and `content` comes back empty. Even with
        # format:json, some prompts still spend tokens in `thinking`,
        # so we (a) raise num_predict and (b) fall back to parsing
        # `thinking` if `content` is empty.
        "format": "json",
        "options": {"temperature": 0.0, "num_predict": 1500},
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user",   "content": user},
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_ENDPOINT}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = round(time.time() - t0, 2)
        msg = data.get("message", {}) or {}
        content_text = (msg.get("content", "") or "").strip()
        thinking_text = (msg.get("thinking", "") or "").strip()

        def _try_parse(t: str) -> dict:
            t = t.strip()
            if not t:
                return {}
            if t.startswith("```"):
                t = t.strip("`")
                if t.lower().startswith("json"):
                    t = t[4:].lstrip()
            try:
                return json.loads(t)
            except Exception:
                l = t.find("{"); r = t.rfind("}")
                if l >= 0 and r > l:
                    try:
                        return json.loads(t[l:r+1])
                    except Exception:
                        return {}
                return {}

        # Primary: `content`. Fallback: `thinking` (gpt-oss sometimes
        # routes the JSON there; accept it but record the fallback).
        parsed = _try_parse(content_text)
        used_fallback = False
        if not (parsed and "A" in parsed and "B" in parsed):
            alt = _try_parse(thinking_text)
            if alt and "A" in alt and "B" in alt:
                parsed = alt
                used_fallback = True

        ok = bool(parsed and "A" in parsed and "B" in parsed)
        meta = {
            "ok": ok,
            "elapsed_s": elapsed,
            "judge_model": JUDGE_MODEL,
            "judge_provider": "ollama_local",
            "thinking_fallback_used": used_fallback,
            "content_empty": not bool(content_text),
            "raw_excerpt": (content_text or thinking_text)[:200] if not ok else "",
        }
        return (parsed, meta)
    except Exception as e:
        return ({}, {
            "ok": False,
            "elapsed_s": round(time.time() - t0, 2),
            "judge_model": JUDGE_MODEL,
            "judge_provider": "ollama_local",
            "error": f"{type(e).__name__}: {str(e)[:160]}",
        })


def axis_sum(scores: dict) -> int:
    if not scores:
        return 0
    keys = ("route_accuracy", "answer_correctness", "restraint_quality",
            "conciseness", "overall_usefulness")
    return sum(int(scores.get(k, 0)) for k in keys)


def main() -> int:
    if not PER_QUERY_IN.exists():
        print(f"missing input: {PER_QUERY_IN}", file=sys.stderr)
        return 1

    pairs = []
    excluded = []
    for i, line in enumerate(PER_QUERY_IN.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        missing = [f for f in REQUIRED_FIELDS if not str(obj.get(f, "")).strip()]
        if missing:
            excluded.append({"id": obj.get("id", f"row_{i}"),
                              "missing_fields": missing})
            continue
        pairs.append(obj)

    n_total = len(pairs)
    print(f"valid pairs: {n_total}; excluded: {len(excluded)}", flush=True)
    if n_total < 30:
        print(f"valid pairs ({n_total}) < 30 minimum; aborting per scope.",
              file=sys.stderr)
        return 2

    # Sanity-ping the judge endpoint before starting.
    test_parsed, test_meta = call_judge(
        prompt="What is 2+2?",
        category="conceptual_explanation",
        expected_route="answer",
        text_a="Four.",
        text_b="2+2 equals 4.",
        timeout=60,
    )
    if not test_meta.get("ok"):
        print(f"judge ping FAILED: {test_meta}", file=sys.stderr)
        print("aborting per Phase 5C no-repair rule "
              "(do not investigate auth / endpoint).", file=sys.stderr)
        return 3
    print(f"judge ping ok ({JUDGE_MODEL} via Ollama)", flush=True)

    rng = random.Random(20260429)
    rows = []
    raw_totals = []
    governed_totals = []
    n_ok = 0
    n_fail = 0
    judge_meta_total_seconds = 0.0
    has_expected_count = 0

    t_start = time.time()
    for i, p in enumerate(pairs, 1):
        # Blind A/B per query.
        a_governed = bool(rng.random() < 0.5)
        text_a = p["governed_response"] if a_governed else p["raw_response"]
        text_b = p["raw_response"]      if a_governed else p["governed_response"]
        expected = p.get("expected_route")
        if expected:
            has_expected_count += 1

        judged, meta = call_judge(
            prompt=p["query"],
            category=p["category"],
            expected_route=expected,
            text_a=text_a,
            text_b=text_b,
        )
        judge_meta_total_seconds += meta.get("elapsed_s", 0)
        if meta.get("ok"):
            n_ok += 1
            a_score = axis_sum(judged.get("A", {}))
            b_score = axis_sum(judged.get("B", {}))
        else:
            n_fail += 1
            a_score = 0
            b_score = 0

        gov_score = a_score if a_governed else b_score
        raw_score = b_score if a_governed else a_score
        if meta.get("ok"):
            raw_totals.append(raw_score)
            governed_totals.append(gov_score)

        winner_label = "tie_or_unknown"
        if meta.get("ok"):
            w = (judged.get("winner") or "").upper()
            if w == "A":
                winner_label = "governed" if a_governed else "raw"
            elif w == "B":
                winner_label = "raw" if a_governed else "governed"
            else:
                winner_label = "tie"

        row = {
            "id": p["id"],
            "category": p["category"],
            "query": p["query"],
            "expected_route": expected,
            "raw_response_excerpt": (p["raw_response"][:240] + "…") if len(p["raw_response"]) > 240 else p["raw_response"],
            "governed_response_excerpt": (p["governed_response"][:240] + "…") if len(p["governed_response"]) > 240 else p["governed_response"],
            "a_was_governed": a_governed,
            "judge": judged,
            "judge_meta": meta,
            "raw_total_20": raw_score,
            "governed_total_20": gov_score,
            "winner_label": winner_label,
        }
        rows.append(row)

        if i % 5 == 0 or i == n_total:
            elapsed = time.time() - t_start
            mraw = sum(raw_totals) / len(raw_totals) if raw_totals else 0
            mgov = sum(governed_totals) / len(governed_totals) if governed_totals else 0
            print(
                f"  [{i}/{n_total}] elapsed={elapsed:.1f}s "
                f"ok={n_ok} fail={n_fail} "
                f"raw_mean={mraw:.2f} gov_mean={mgov:.2f} "
                f"delta={mgov-mraw:+.2f}",
                flush=True,
            )

    PER_QUERY_OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    # Aggregations.
    n_judged = len(raw_totals)
    raw_mean = sum(raw_totals) / n_judged if n_judged else 0
    gov_mean = sum(governed_totals) / n_judged if n_judged else 0
    delta = gov_mean - raw_mean

    by_category = {}
    for r in rows:
        c = r["category"]
        if c not in by_category:
            by_category[c] = {"n": 0, "raw_sum": 0, "gov_sum": 0,
                              "wins": {"raw": 0, "governed": 0, "tie": 0, "tie_or_unknown": 0}}
        by_category[c]["n"] += 1
        if r["judge_meta"].get("ok"):
            by_category[c]["raw_sum"] += r["raw_total_20"]
            by_category[c]["gov_sum"] += r["governed_total_20"]
        wl = r["winner_label"]
        bucket = wl if wl in by_category[c]["wins"] else "tie_or_unknown"
        by_category[c]["wins"][bucket] += 1

    by_category_summary = {}
    for c, d in by_category.items():
        n = d["n"]
        by_category_summary[c] = {
            "n": n,
            "raw_mean": round(d["raw_sum"] / n, 2) if n else None,
            "governed_mean": round(d["gov_sum"] / n, 2) if n else None,
            "delta": round((d["gov_sum"] - d["raw_sum"]) / n, 2) if n else None,
            "wins": d["wins"],
        }

    # Per-axis means (overall) — only ok rows.
    axis_keys = ("route_accuracy", "answer_correctness", "restraint_quality",
                 "conciseness", "overall_usefulness")
    raw_axis_means = {}
    gov_axis_means = {}
    for k in axis_keys:
        rvals = []
        gvals = []
        for r in rows:
            if not r["judge_meta"].get("ok") or not r["judge"]:
                continue
            jd = r["judge"]
            ag = r["a_was_governed"]
            try:
                a_v = int(jd.get("A", {}).get(k, 0))
                b_v = int(jd.get("B", {}).get(k, 0))
            except Exception:
                continue
            gvals.append(a_v if ag else b_v)
            rvals.append(b_v if ag else a_v)
        raw_axis_means[k] = round(sum(rvals) / len(rvals), 2) if rvals else None
        gov_axis_means[k] = round(sum(gvals) / len(gvals), 2) if gvals else None

    # P9 thesis support determination.
    if n_judged == 0:
        thesis = "INCONCLUSIVE_NO_JUDGE"
    elif delta >= 2.0:
        thesis = "STRONGLY_SUPPORTS"
    elif delta >= 1.0:
        thesis = "SUPPORTS"
    elif delta >= 0.3:
        thesis = "WEAKLY_SUPPORTS"
    elif delta > -0.3:
        thesis = "INCONCLUSIVE"
    elif delta > -1.0:
        thesis = "WEAKLY_WEAKENS"
    else:
        thesis = "WEAKENS"

    summary = {
        "test": "p9_evidence_pack_v1.test_2_judge_repair_pass",
        "n_total": n_total,
        "n_judged_ok": n_judged,
        "n_judge_fail": n_fail,
        "n_excluded_pre_run": len(excluded),
        "excluded_reasons": excluded,
        "valid_pairs_count": n_total,
        "judge_model": JUDGE_MODEL,
        "judge_provider": "ollama_local",
        "judge_ping_ok": True,
        "ab_blind_used": True,
        "deterministic_seed": 20260429,

        "raw_mean_total20": round(raw_mean, 2),
        "governed_mean_total20": round(gov_mean, 2),
        "delta_total20": round(delta, 2),
        "raw_axis_means": raw_axis_means,
        "governed_axis_means": gov_axis_means,
        "axis_deltas": {k: round((gov_axis_means.get(k) or 0) - (raw_axis_means.get(k) or 0), 2) for k in axis_keys},

        "by_category": by_category_summary,
        "thesis_signal": thesis,

        "expected_behavior_present_count": has_expected_count,
        "expected_behavior_present_ratio": round(has_expected_count / n_total, 3) if n_total else None,
        "scoring_method": (
            "expected-route-aware (judge prompt includes expected_route per query)"
            if has_expected_count == n_total else
            "preference-aware (judge sees expected_route when available, "
            "otherwise scores on rubric only)"
        ),

        "judge_total_elapsed_s": round(judge_meta_total_seconds, 1),
        "groq_token_usage": 0,
        "ollama_judge_local_only": True,

        "configuration": {
            "raw_generator": GENERATOR_MODEL_NAME,
            "governed_layer": "MMV Core v0.1-rc1 via PseudoUISession (same base model as raw)",
            "judge_originally_intended": "Groq openai/gpt-oss-120b",
            "judge_substitute": f"Ollama local {JUDGE_MODEL}",
            "substitution_reason": (
                "Groq endpoint returned HTTP 403 (Cloudflare 1010) "
                "across all calls during Phase 5C; not investigated "
                "per the no-repair rule. Phase 5C amendment §2 permits "
                "a substitute judge."
            ),
        },

        "caveats": [
            "Post-hoc judge-only pass. Raw and governed responses were "
            "captured during the original Phase 5C Test 2 run and are "
            "not regenerated here.",
            "The judge generation conditions in the original Phase 5C "
            "Test 2 are not changed by this pass.",
            "Single-judge limitation: no inter-judge consensus.",
            "Vendor / model-family overlap: the judge "
            f"({JUDGE_MODEL}) is the openai/gpt-oss family; the "
            "originally intended Groq judge was openai/gpt-oss-120b. "
            "The locally-hosted judge runs on different infrastructure "
            "(Ollama, no Groq dependency) but shares the upstream "
            "weights family.",
            "Length-bias guard explicitly included in the judge "
            "prompt, but residual length bias cannot be fully ruled "
            "out without a multi-judge sweep.",
            "Same base model ("
            f"{GENERATOR_MODEL_NAME}) on both raw and governed sides; "
            "the intentional variable is the MMV governance layer.",
            "Sampling oversamples ambiguous + factual; not "
            "representative of an evenly-weighted natural distribution.",
            "This is NOT Phase 6 full evaluation. NOT deployment-wide "
            "validation. NOT real UI performance validation.",
        ],
    }

    SUMMARY_OUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Markdown summary.
    md = []
    md.append("# Test 2 Judge Repair Pass — summary")
    md.append("")
    md.append(f"- N total: {n_total}")
    md.append(f"- N judged ok: {n_judged}")
    md.append(f"- N judge fail: {n_fail}")
    md.append(f"- Judge: `{JUDGE_MODEL}` via Ollama (local)")
    md.append(f"- Originally intended: Groq `openai/gpt-oss-120b` "
              "(unavailable: HTTP 403)")
    md.append(f"- Raw mean (0–20):      **{raw_mean:.2f}**")
    md.append(f"- Governed mean (0–20): **{gov_mean:.2f}**")
    md.append(f"- Δ (governed − raw):   **{delta:+.2f}**")
    md.append(f"- P9 thesis signal:     **{thesis}**")
    md.append("")
    md.append("## Per-axis means (0–4)")
    md.append("")
    md.append("| Axis | raw | governed | Δ |")
    md.append("|---|---|---|---|")
    for k in axis_keys:
        rv = raw_axis_means.get(k)
        gv = gov_axis_means.get(k)
        if rv is None or gv is None:
            md.append(f"| {k} | — | — | — |")
        else:
            md.append(f"| {k} | {rv} | {gv} | {gv-rv:+.2f} |")
    md.append("")
    md.append("## Per-category (mean total 0–20)")
    md.append("")
    md.append("| category | n | raw | governed | Δ | wins (raw/gov/tie) |")
    md.append("|---|---|---|---|---|---|")
    for c, d in by_category_summary.items():
        w = d["wins"]
        ties = w.get("tie", 0) + w.get("tie_or_unknown", 0)
        md.append(
            f"| {c} | {d['n']} | "
            f"{d['raw_mean'] if d['raw_mean'] is not None else '—'} | "
            f"{d['governed_mean'] if d['governed_mean'] is not None else '—'} | "
            f"{d['delta'] if d['delta'] is not None else '—'} | "
            f"{w.get('raw',0)}/{w.get('governed',0)}/{ties} |"
        )
    md.append("")
    md.append("## Caveats")
    md.append("")
    for c in summary["caveats"]:
        md.append(f"- {c}")
    SUMMARY_MD_OUT.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"\nwrote per-query: {PER_QUERY_OUT}")
    print(f"wrote summary:   {SUMMARY_OUT}")
    print(f"wrote summary md: {SUMMARY_MD_OUT}")
    print(f"thesis signal: {thesis}  delta: {delta:+.2f}  n_judged: {n_judged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
