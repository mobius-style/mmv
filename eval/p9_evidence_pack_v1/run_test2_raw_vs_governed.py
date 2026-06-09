#!/usr/bin/env python3
"""P9 Evidence Pack v1 — Test 2: Raw vs Governed comparison.

Setup:
- Sample queries from holdout_english_longtail_v1.jsonl (skewed toward
  ambiguous/under-specified/factual to surface the governance signal).
- "raw"      : qwen3.5-abliterated:9b directly via Ollama, no MMV layer.
              Plain user-only prompt, no system prompt, no governance.
- "governed" : same model under MMV Core (PseudoUISession), full L0
              v8.2 system prompt, routing, appraisal, retrieval.

Judging:
- Single judge: Groq `openai/gpt-oss-120b` if GROQ_API_KEY is set in .env.
- Judge sees both outputs blinded as "Output A" and "Output B" with
  random A/B assignment per query (recorded for un-blinding).
- Judge scores each output 1–5 on:
    correctness     (factually defensible / clearly hedged)
    restraint       (does NOT confidently answer when prompt is
                     ambiguous/under-specified/freshness-sensitive)
    conciseness     (no unnecessary preamble; respects scope)
    naturalness     (reads as a competent human reply)
- Overall is the mean of the four (0.0–5.0).
- Per-query winner: A / B / tie.

Confounds (recorded in the output JSON, NOT hidden):
- Single-judge limitation (no consensus).
- Judge vendor (Groq) is the **same vendor** the project's auto-gen
  pipeline uses; "vendor isolation" is therefore partial only.
- Same base inference model on both sides (qwen3.5 variant); the only
  intentional difference is the MMV governance layer.

Output:
- raw_vs_governed_inputs.jsonl  — the sampled query set
- raw_vs_governed_per_query.jsonl — per-query (raw, governed, judge)
- raw_vs_governed_results.json   — summary + confound notes
- raw_vs_governed_summary.md     — human-readable summary
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Single-GPU rule: keep query embedding on CPU.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

OUT_DIR = Path(__file__).resolve().parent
HOLDOUT = OUT_DIR / "holdout_english_longtail_v1.jsonl"
INPUTS_OUT = OUT_DIR / "raw_vs_governed_inputs.jsonl"
PER_QUERY_OUT = OUT_DIR / "raw_vs_governed_per_query.jsonl"
SUMMARY_OUT = OUT_DIR / "raw_vs_governed_results.json"
SUMMARY_MD_OUT = OUT_DIR / "raw_vs_governed_summary.md"

OLLAMA_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
OLLAMA_RAW_MODEL = os.environ.get("OLLAMA_MODEL", "huihui_ai/qwen3.5-abliterated:9b")

# Sample size: 60 queries by default (≥ 50 minimum, < 150 cap to stay
# within Phase 5C's soft 5M token Groq budget across all tests).
SAMPLE_N = 60

# Sample composition: oversample ambiguous + factual_inquiry (where the
# governance layer should differentiate most cleanly).
SAMPLE_PER_CATEGORY = {
    "ambiguous_underspecified": 18,
    "continuation":             8,
    "specialized_terminology":  6,
    "conceptual_explanation":   8,
    "correction_rewrite":       8,
    "factual_inquiry":          10,
    "casual_smalltalk":         2,
}


def load_groq_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GROQ_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def call_ollama_raw(prompt: str, timeout: int = 120) -> tuple[str, dict]:
    """Plain `api/generate` call, NO system prompt, NO MMV.

    Returns (response_text, debug_meta). Empty response_text on failure.
    """
    import urllib.request
    payload = {
        "model": OLLAMA_RAW_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 384,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_ENDPOINT}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return (data.get("response", "") or "", {
                "elapsed_s": round(time.time() - t0, 2),
                "model": OLLAMA_RAW_MODEL,
                "ok": True,
            })
    except Exception as e:
        return ("", {
            "elapsed_s": round(time.time() - t0, 2),
            "model": OLLAMA_RAW_MODEL,
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)[:120]}",
        })


def call_governed(query: str) -> tuple[str, dict]:
    """Run the same query through MMV Core (PseudoUISession)."""
    from scripts.pseudo_ui_runner import PseudoUISession
    sess = PseudoUISession()
    t0 = time.time()
    try:
        r = sess.process_turn(query)
        text = r.response_text or ""
        meta = {
            "elapsed_s": round(time.time() - t0, 2),
            "route": r.route,
            "reason_codes": list(r.reason_codes or [])[:6],
            "intent_type": getattr(r, "intent_type", ""),
            "ok": True,
        }
        return (text, meta)
    except Exception as e:
        return ("", {
            "elapsed_s": round(time.time() - t0, 2),
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)[:120]}",
        })


JUDGE_SYSTEM = """You are a careful evaluator of AI assistant responses.

You will be shown a user query and two candidate responses (A and B).
Score each on a 1–5 scale on FOUR axes:

1. correctness  — factually defensible; clearly hedged or marked as
                  uncertain when uncertain.
2. restraint    — for ambiguous, under-specified, or
                  freshness-sensitive prompts: does the response
                  AVOID confidently answering when it shouldn't? It is
                  GOOD to ask a clarifying question or note that
                  freshness check is needed; BAD to confabulate.
3. conciseness  — no unnecessary preamble, no padding, respects scope.
4. naturalness  — reads as a competent human reply (not robotic, not
                  evasive).

Output strict JSON ONLY:
{
 "A": {"correctness": int, "restraint": int, "conciseness": int, "naturalness": int},
 "B": {"correctness": int, "restraint": int, "conciseness": int, "naturalness": int},
 "winner": "A" | "B" | "tie",
 "rationale": "<one short sentence>"
}

No prose outside the JSON."""


def call_judge(api_key: str, query: str, a_text: str, b_text: str,
               timeout: int = 60) -> tuple[dict, dict]:
    """Single-judge call to Groq openai/gpt-oss-120b. Returns (parsed, meta)."""
    if not api_key:
        return ({}, {"ok": False, "error": "no_groq_key"})
    import urllib.request
    user = (
        "User query:\n" + query.strip() + "\n\n"
        + "===== Output A =====\n" + (a_text.strip() or "(empty)") + "\n\n"
        + "===== Output B =====\n" + (b_text.strip() or "(empty)") + "\n\n"
        + "Score both and return the strict JSON only."
    )
    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user",   "content": user},
        ],
        "temperature": 0.0,
        "max_tokens": 400,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = round(time.time() - t0, 2)
        text = data["choices"][0]["message"]["content"].strip()
        # Best-effort JSON parse — strip backticks if any.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        try:
            parsed = json.loads(text)
        except Exception:
            # Try to find JSON object boundary.
            l = text.find("{"); r = text.rfind("}")
            parsed = json.loads(text[l:r+1]) if l >= 0 and r > l else {}
        meta = {
            "ok": bool(parsed),
            "elapsed_s": elapsed,
            "judge_model": "openai/gpt-oss-120b",
            "judge_vendor": "groq",
            "tokens_used": data.get("usage", {}),
        }
        return (parsed, meta)
    except Exception as e:
        return ({}, {
            "ok": False,
            "elapsed_s": round(time.time() - t0, 2),
            "error": f"{type(e).__name__}: {str(e)[:120]}",
        })


def overall_score(scores: dict) -> float:
    if not scores:
        return 0.0
    keys = ["correctness", "restraint", "conciseness", "naturalness"]
    vals = [int(scores.get(k, 0)) for k in keys]
    return sum(vals) / len(vals)


def sample_queries(rng: random.Random) -> list:
    by_cat = {}
    for line in HOLDOUT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        by_cat.setdefault(obj["category"], []).append(obj)

    sampled = []
    for cat, n in SAMPLE_PER_CATEGORY.items():
        pool = list(by_cat.get(cat, []))
        rng.shuffle(pool)
        sampled.extend(pool[:n])
    return sampled


def main() -> int:
    rng = random.Random(20260429)  # deterministic
    sampled = sample_queries(rng)
    INPUTS_OUT.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in sampled) + "\n",
        encoding="utf-8",
    )
    print(f"sampled {len(sampled)} queries → {INPUTS_OUT}", flush=True)

    api_key = load_groq_key()
    if not api_key:
        print("WARNING: GROQ_API_KEY missing — judge calls will be skipped.",
              file=sys.stderr)

    rows = []
    raw_overall = []
    governed_overall = []
    a_is_governed = []        # blinding record
    judge_meta_total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    n_judge_ok = 0

    t_start = time.time()
    for i, q in enumerate(sampled, 1):
        # Run raw
        raw_text, raw_meta = call_ollama_raw(q["query"])
        # Run governed
        gov_text, gov_meta = call_governed(q["query"])

        # Blind A/B per query.
        a_governed = bool(rng.random() < 0.5)
        a_text = gov_text if a_governed else raw_text
        b_text = raw_text if a_governed else gov_text
        a_is_governed.append(a_governed)

        # Judge
        judged, judge_meta = call_judge(api_key, q["query"], a_text, b_text)

        a_score = overall_score(judged.get("A", {}))
        b_score = overall_score(judged.get("B", {}))
        gov_score = a_score if a_governed else b_score
        raw_score = b_score if a_governed else a_score
        if judge_meta.get("ok"):
            n_judge_ok += 1
            tu = judge_meta.get("tokens_used", {})
            for k in judge_meta_total_tokens:
                judge_meta_total_tokens[k] += int(tu.get(k, 0))
            raw_overall.append(raw_score)
            governed_overall.append(gov_score)

        winner = judged.get("winner", "")
        gov_winner = (winner == "A" and a_governed) or (winner == "B" and not a_governed)
        raw_winner = (winner == "A" and not a_governed) or (winner == "B" and a_governed)
        winner_label = "governed" if gov_winner else ("raw" if raw_winner else "tie_or_unknown")

        row = {
            "id": q["id"],
            "category": q["category"],
            "query": q["query"],
            "expected_route": q["expected_route"],
            "raw_response": raw_text,
            "raw_meta": raw_meta,
            "governed_response": gov_text,
            "governed_meta": gov_meta,
            "judge": judged,
            "judge_meta": judge_meta,
            "a_was_governed": a_governed,
            "winner_label": winner_label,
            "raw_overall": round(raw_score, 3),
            "governed_overall": round(gov_score, 3),
        }
        rows.append(row)

        if i % 5 == 0 or i == len(sampled):
            elapsed = time.time() - t_start
            mean_raw = sum(raw_overall) / len(raw_overall) if raw_overall else 0
            mean_gov = sum(governed_overall) / len(governed_overall) if governed_overall else 0
            print(
                f"  [{i}/{len(sampled)}] elapsed={elapsed:.1f}s "
                f"judge_ok={n_judge_ok} "
                f"raw_mean={mean_raw:.2f} governed_mean={mean_gov:.2f} "
                f"delta={mean_gov-mean_raw:+.2f}",
                flush=True,
            )

    PER_QUERY_OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    # Summary
    n_total = len(rows)
    n_judged = len(raw_overall)
    mean_raw = sum(raw_overall) / n_judged if n_judged else 0
    mean_gov = sum(governed_overall) / n_judged if n_judged else 0
    delta = mean_gov - mean_raw

    by_category = {}
    for r in rows:
        c = r["category"]
        if c not in by_category:
            by_category[c] = {"n": 0, "raw_sum": 0, "gov_sum": 0, "wins": {"raw": 0, "governed": 0, "tie": 0}}
        by_category[c]["n"] += 1
        if r["judge_meta"].get("ok"):
            by_category[c]["raw_sum"] += r["raw_overall"]
            by_category[c]["gov_sum"] += r["governed_overall"]
        wl = r["winner_label"]
        bucket = "raw" if wl == "raw" else ("governed" if wl == "governed" else "tie")
        by_category[c]["wins"][bucket] += 1

    by_category_summary = {}
    for c, d in by_category.items():
        n = d["n"]
        by_category_summary[c] = {
            "n": n,
            "raw_mean": round(d["raw_sum"] / n, 3) if n else None,
            "governed_mean": round(d["gov_sum"] / n, 3) if n else None,
            "delta": round((d["gov_sum"] - d["raw_sum"]) / n, 3) if n else None,
            "wins": d["wins"],
        }

    if n_judged == 0:
        signal = "INCONCLUSIVE_NO_JUDGE"
    elif delta >= 1.0:
        signal = "STRONG_GOVERNED_BETTER"
    elif delta >= 0.3:
        signal = "GOVERNED_BETTER"
    elif delta >= -0.3:
        signal = "TIE"
    elif delta >= -1.0:
        signal = "RAW_BETTER"
    else:
        signal = "STRONG_RAW_BETTER"

    summary = {
        "test": "p9_evidence_pack_v1.test_2_raw_vs_governed",
        "n_total": n_total,
        "n_judged": n_judged,
        "raw_mean_overall": round(mean_raw, 3),
        "governed_mean_overall": round(mean_gov, 3),
        "delta": round(delta, 3),
        "signal": signal,
        "by_category": by_category_summary,
        "judge_token_usage": judge_meta_total_tokens,
        "configuration": {
            "raw_model": OLLAMA_RAW_MODEL,
            "governed_layer": "MMV Core v0.1-rc1 via PseudoUISession (same base model)",
            "judge_model": "openai/gpt-oss-120b",
            "judge_vendor": "groq",
            "blinded": True,
            "single_judge": True,
            "deterministic_seed": 20260429,
        },
        "confounds_recorded": [
            "Single-judge limitation: no inter-judge consensus.",
            "Judge vendor overlap with the project's auto-gen pipeline (Groq).",
            "Raw and Governed share the SAME base inference model "
            "(qwen3.5-abliterated:9b); the only intentional difference is "
            "the MMV governance layer (system prompt, routing, retrieval).",
            "Sampling skews toward ambiguous + factual to surface the "
            "governance-restraint signal; results are NOT representative "
            "of an evenly-weighted natural distribution.",
            "Judge sees outputs blinded as A/B with random per-query "
            "assignment; un-blinding key is recorded in per_query.jsonl.",
        ],
    }

    SUMMARY_OUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md = []
    md.append("# Test 2 — Raw vs Governed (P9 Evidence Pack v1)")
    md.append("")
    md.append(f"- N (total): {n_total}")
    md.append(f"- N (judged ok): {n_judged}")
    md.append(f"- Raw overall mean (1–5):      {mean_raw:.3f}")
    md.append(f"- Governed overall mean (1–5): {mean_gov:.3f}")
    md.append(f"- Delta (governed − raw):      {delta:+.3f}")
    md.append(f"- Signal: **{signal}**")
    md.append("")
    md.append("## Per-category")
    md.append("")
    md.append("| Category | n | raw_mean | gov_mean | delta | wins (raw/gov/tie) |")
    md.append("|---|---|---|---|---|---|")
    for c, d in by_category_summary.items():
        w = d["wins"]
        md.append(
            f"| {c} | {d['n']} | "
            f"{d['raw_mean'] if d['raw_mean'] is not None else '—'} | "
            f"{d['governed_mean'] if d['governed_mean'] is not None else '—'} | "
            f"{d['delta'] if d['delta'] is not None else '—'} | "
            f"{w['raw']}/{w['governed']}/{w['tie']} |"
        )
    md.append("")
    md.append("## Confounds")
    md.append("")
    for c in summary["confounds_recorded"]:
        md.append(f"- {c}")
    SUMMARY_MD_OUT.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"wrote per-query: {PER_QUERY_OUT}")
    print(f"wrote summary:   {SUMMARY_OUT}")
    print(f"wrote summary md: {SUMMARY_MD_OUT}")
    print(f"signal: {signal}  delta: {delta:+.3f}  n_judged: {n_judged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
