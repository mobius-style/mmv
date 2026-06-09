#!/usr/bin/env python3
"""P9 Evidence Pack v1 — Test 2 Groq openai/gpt-oss-120b judge pass.

Background:
  Phase 5C originally intended to use Groq's hosted
  `openai/gpt-oss-120b` as judge, but every call returned HTTP 403
  via Cloudflare error 1010 (UA fingerprint block). The diagnostic
  in `docs/GROQ_403_DIAGNOSTIC_NOTE.md` proved the cause was the
  default Python `urllib` User-Agent. With an explicit User-Agent
  header set, the same key + same model returns HTTP 200 with a
  real completion.

This script applies the minimal User-Agent fix and runs the
originally-planned judge-only pass on the 60 captured raw/governed
pairs. **No raw or governed regeneration**; **no `src/` change**.

Methodology:
  - Read existing `raw_vs_governed_per_query.jsonl` (Phase 5C Test 2
    captured pairs).
  - For each pair, randomize A/B (deterministic seed 20260429) and
    ask the judge to score A and B independently on five 0–4 axes.
  - Length-bias guard verbatim in judge prompt.
  - Strip API key / Authorization / response headers from any saved
    artifact: only judge JSON content + token usage counts are
    persisted.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Single-GPU rule per Phase 5C HARD CONSTRAINT 6: harness has no
# embedding work; CPU-only env keeps anything embedding-related off
# the GPU.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

OUT_DIR = Path(__file__).resolve().parent
PER_QUERY_IN = OUT_DIR / "raw_vs_governed_per_query.jsonl"
PER_QUERY_OUT = OUT_DIR / "raw_vs_governed_groq120b_judge_results.jsonl"
SUMMARY_OUT = OUT_DIR / "raw_vs_governed_groq120b_judge_results.json"
SUMMARY_MD_OUT = OUT_DIR / "raw_vs_governed_groq120b_judge_summary.md"

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
JUDGE_MODEL = "openai/gpt-oss-120b"
GENERATOR_MODEL_NAME = "huihui_ai/qwen3.5-abliterated:9b"

# The minimal repair: an explicit User-Agent header. This is the only
# change relative to the original Phase 5C call sites.
USER_AGENT = "mmv-p9-evidence-pack/1.0"

REQUIRED_FIELDS = ("query", "category", "raw_response", "governed_response")


def load_groq_key() -> str:
    """Load GROQ_API_KEY without ever printing or logging it."""
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GROQ_API_KEY=") and "=" in line:
                v = line.split("=", 1)[1].strip()
                if v:
                    return v
    return ""


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


def call_judge(api_key: str, prompt: str, category: str,
               expected_route: str | None, text_a: str, text_b: str,
               *, timeout: int = 90) -> tuple[dict, dict]:
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
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user",   "content": user},
        ],
        "temperature": 0.0,
        "max_tokens": 600,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GROQ_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": USER_AGENT,   # ← the fix
            "Accept": "application/json",
        },
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = round(time.time() - t0, 2)
        # Drop response headers; keep only completion content + usage.
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message", {}) or {}).get("content", "").strip()
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
        # Strip any nested header-like fields out of usage.
        sanitized_usage = {
            k: int(usage.get(k, 0))
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            if k in usage
        }
        meta = {
            "ok": ok,
            "elapsed_s": elapsed,
            "judge_model": JUDGE_MODEL,
            "judge_provider": "groq",
            "tokens": sanitized_usage,
            "raw_excerpt": text[:200] if not ok else "",
        }
        return (parsed, meta)
    except urllib.error.HTTPError as e:
        # Capture status + a short body excerpt; never log headers.
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return ({}, {
            "ok": False,
            "elapsed_s": round(time.time() - t0, 2),
            "judge_model": JUDGE_MODEL,
            "judge_provider": "groq",
            "error_kind": "HTTPError",
            "status": e.code,
            "body_excerpt": body_text[:300],
        })
    except Exception as e:
        return ({}, {
            "ok": False,
            "elapsed_s": round(time.time() - t0, 2),
            "judge_model": JUDGE_MODEL,
            "judge_provider": "groq",
            "error_kind": type(e).__name__,
            "error_msg": str(e)[:200],
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
        print("valid pairs < 30; aborting per scope.", file=sys.stderr)
        return 2

    api_key = load_groq_key()
    if not api_key:
        print("GROQ_API_KEY missing — abort (no fallback per scope).",
              file=sys.stderr)
        return 3

    # Sanity ping with the User-Agent fix.
    p_parsed, p_meta = call_judge(
        api_key,
        prompt="What is 2+2?",
        category="conceptual_explanation",
        expected_route="answer",
        text_a="Four.",
        text_b="2+2 equals 4.",
        timeout=60,
    )
    if not p_meta.get("ok"):
        # Keep error short; never log key.
        print(f"judge ping FAILED: status={p_meta.get('status')} "
              f"kind={p_meta.get('error_kind')} body={p_meta.get('body_excerpt','')[:100]}",
              file=sys.stderr)
        return 4
    print(f"judge ping ok ({JUDGE_MODEL} via Groq, "
          f"tokens={p_meta.get('tokens', {})})", flush=True)

    rng = random.Random(20260429)
    rows = []
    raw_totals = []
    governed_totals = []
    n_ok = 0
    n_fail = 0
    token_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    has_expected_count = 0

    t_start = time.time()
    for i, p in enumerate(pairs, 1):
        a_governed = bool(rng.random() < 0.5)
        text_a = p["governed_response"] if a_governed else p["raw_response"]
        text_b = p["raw_response"]      if a_governed else p["governed_response"]
        expected = p.get("expected_route")
        if expected:
            has_expected_count += 1

        judged, meta = call_judge(
            api_key,
            prompt=p["query"],
            category=p["category"],
            expected_route=expected,
            text_a=text_a,
            text_b=text_b,
        )
        if meta.get("ok"):
            n_ok += 1
            for k in token_total:
                token_total[k] += int(meta.get("tokens", {}).get(k, 0))
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

        # Per-row dump — strip API-level secrets; only judge content + meta.
        rows.append({
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
        })

        if i % 5 == 0 or i == n_total:
            elapsed = time.time() - t_start
            mraw = sum(raw_totals) / len(raw_totals) if raw_totals else 0
            mgov = sum(governed_totals) / len(governed_totals) if governed_totals else 0
            print(
                f"  [{i}/{n_total}] elapsed={elapsed:.1f}s "
                f"ok={n_ok} fail={n_fail} "
                f"raw_mean={mraw:.2f} gov_mean={mgov:.2f} "
                f"delta={mgov-mraw:+.2f} "
                f"tokens={token_total['total_tokens']}",
                flush=True,
            )

    PER_QUERY_OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    # Aggregations
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

    axis_keys = ("route_accuracy", "answer_correctness", "restraint_quality",
                 "conciseness", "overall_usefulness")
    raw_axis_means = {}
    gov_axis_means = {}
    for k in axis_keys:
        rvals, gvals = [], []
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
        "test": "p9_evidence_pack_v1.test_2_groq120b_judge_pass",
        "n_total": n_total,
        "n_judged_ok": n_judged,
        "n_judge_fail": n_fail,
        "n_excluded_pre_run": len(excluded),
        "judge_model": JUDGE_MODEL,
        "judge_provider": "groq",
        "user_agent_used": USER_AGENT,
        "user_agent_repair_applied": True,
        "ab_blind_used": True,
        "deterministic_seed": 20260429,
        "raw_mean_total20": round(raw_mean, 2),
        "governed_mean_total20": round(gov_mean, 2),
        "delta_total20": round(delta, 2),
        "raw_axis_means": raw_axis_means,
        "governed_axis_means": gov_axis_means,
        "axis_deltas": {k: round((gov_axis_means.get(k) or 0) - (raw_axis_means.get(k) or 0), 2)
                         for k in axis_keys},
        "by_category": by_category_summary,
        "thesis_signal": thesis,
        "expected_behavior_present_count": has_expected_count,
        "scoring_method": "expected-route-aware (judge prompt includes expected_route per query)",
        "groq_token_usage": token_total,
        "configuration": {
            "raw_generator": GENERATOR_MODEL_NAME,
            "governed_layer": "MMV Core v0.1-rc1 via PseudoUISession (same base model as raw)",
            "judge_originally_intended": "Groq openai/gpt-oss-120b",
            "judge_used": "Groq openai/gpt-oss-120b (fix: explicit User-Agent header)",
            "user_agent_repair_reason": (
                "Phase 5C original calls used default Python urllib User-Agent, "
                "which Cloudflare 1010 was rejecting on the Groq edge. Fix: "
                "explicit User-Agent header. See GROQ_403_DIAGNOSTIC_NOTE.md."
            ),
        },
        "caveats": [
            "Post-hoc judge-only pass. Raw and governed responses were "
            "generated before the judge access repair; they were NOT "
            "regenerated. The original Phase 5C Test 2 generation "
            "conditions are unchanged.",
            "The User-Agent fix changes only the HTTP header on judge "
            "requests. It does not affect generated responses or any "
            "other code path.",
            "Single-judge limitation remains: no inter-judge consensus.",
            "Groq 120B judge is stronger than the local 20B fallback "
            "but is still not a multi-judge consensus.",
            "Length-bias guard explicitly included in the judge prompt.",
            "Same base model on both raw and governed sides; the "
            "intentional variable is the MMV governance layer.",
            "Sampling oversamples ambiguous + factual; not "
            "representative of an evenly-weighted natural distribution.",
            "NOT Phase 6 full evaluation. NOT deployment-wide "
            "validation. NOT real UI performance validation.",
        ],
    }

    SUMMARY_OUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md = []
    md.append("# Test 2 Groq 120B Judge Pass — summary")
    md.append("")
    md.append(f"- N total: {n_total}")
    md.append(f"- N judged ok: {n_judged}")
    md.append(f"- N judge fail: {n_fail}")
    md.append(f"- Judge: `{JUDGE_MODEL}` via Groq (User-Agent fix applied)")
    md.append(f"- Raw mean (0–20):      **{raw_mean:.2f}**")
    md.append(f"- Governed mean (0–20): **{gov_mean:.2f}**")
    md.append(f"- Δ (governed − raw):   **{delta:+.2f}**")
    md.append(f"- P9 thesis signal:     **{thesis}**")
    md.append(f"- Token usage (Groq):   prompt={token_total['prompt_tokens']}, "
              f"completion={token_total['completion_tokens']}, "
              f"total={token_total['total_tokens']}")
    md.append("")
    md.append("## Per-axis means (0–4)")
    md.append("")
    md.append("| Axis | raw | governed | Δ |")
    md.append("|---|---|---|---|")
    for k in axis_keys:
        rv = raw_axis_means.get(k); gv = gov_axis_means.get(k)
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
