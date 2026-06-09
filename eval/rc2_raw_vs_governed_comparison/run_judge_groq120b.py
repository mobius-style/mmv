#!/usr/bin/env python3
"""Judge Raw vs RC2 Governed using Groq openai/gpt-oss-120b.

Reuses the User-Agent fix established by the prior judge-repair pass
to avoid Cloudflare 1010. Same 5-axis 0–4 rubric, same A/B blinding,
same length-bias guard. Where RC1 judge data is available from the
prior Groq 120B pass, the row carries that for three-way comparison.

Output:
  results.jsonl   per-pair raw / rc2 / rc1 + judge JSON + un-blinding
  summary.json    aggregate + cross-rc1 comparison
  summary.md      human-readable
"""
import json, os, random, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

OUT_DIR = Path(__file__).resolve().parent
PAIRS_IN = OUT_DIR / "raw_vs_rc2_governed_pairs.jsonl"
PER_QUERY_OUT = OUT_DIR / "results.jsonl"
SUMMARY_OUT = OUT_DIR / "summary.json"
SUMMARY_MD_OUT = OUT_DIR / "summary.md"

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
JUDGE_MODEL = "openai/gpt-oss-120b"
USER_AGENT = "mmv-p9-evidence-pack/1.0"

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


def load_groq_key() -> str:
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
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = round(time.time() - t0, 2)
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
        sanitized_usage = {
            k: int(usage.get(k, 0))
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            if k in usage
        }
        return (parsed, {
            "ok": ok, "elapsed_s": elapsed,
            "judge_model": JUDGE_MODEL, "judge_provider": "groq",
            "tokens": sanitized_usage,
            "raw_excerpt": text[:200] if not ok else "",
        })
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return ({}, {
            "ok": False, "elapsed_s": round(time.time() - t0, 2),
            "judge_model": JUDGE_MODEL, "judge_provider": "groq",
            "error_kind": "HTTPError", "status": e.code,
            "body_excerpt": body_text[:300],
        })
    except Exception as e:
        return ({}, {
            "ok": False, "elapsed_s": round(time.time() - t0, 2),
            "judge_model": JUDGE_MODEL, "judge_provider": "groq",
            "error_kind": type(e).__name__, "error_msg": str(e)[:200],
        })


def axis_sum(scores: dict) -> int:
    if not scores:
        return 0
    return sum(int(scores.get(k, 0)) for k in (
        "route_accuracy", "answer_correctness", "restraint_quality",
        "conciseness", "overall_usefulness",
    ))


def main() -> int:
    if not PAIRS_IN.exists():
        print(f"missing input: {PAIRS_IN}", file=sys.stderr)
        return 1

    pairs = []
    for line in PAIRS_IN.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        pairs.append(json.loads(line))
    print(f"valid pairs: {len(pairs)}", flush=True)

    api_key = load_groq_key()
    if not api_key:
        print("GROQ_API_KEY missing — abort.", file=sys.stderr)
        return 2

    p_parsed, p_meta = call_judge(
        api_key, "What is 2+2?", "conceptual_explanation", "answer",
        "Four.", "2+2 equals 4.", timeout=60,
    )
    if not p_meta.get("ok"):
        print(f"judge ping FAILED: {p_meta}", file=sys.stderr)
        return 3
    print(f"judge ping ok ({JUDGE_MODEL} via Groq, "
          f"tokens={p_meta.get('tokens', {})})", flush=True)

    rng = random.Random(20260429)
    rows = []
    raw_totals, rc2_totals = [], []
    n_ok = n_fail = 0
    token_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    t0 = time.time()
    for i, p in enumerate(pairs, 1):
        a_is_rc2 = bool(rng.random() < 0.5)
        text_a = p["rc2_governed_response"] if a_is_rc2 else p["raw_response"]
        text_b = p["raw_response"]            if a_is_rc2 else p["rc2_governed_response"]
        judged, meta = call_judge(
            api_key, p["query"], p["category"], p.get("expected_route"),
            text_a, text_b,
        )
        if meta.get("ok"):
            n_ok += 1
            for k in token_total:
                token_total[k] += int(meta.get("tokens", {}).get(k, 0))
            a_score = axis_sum(judged.get("A", {}))
            b_score = axis_sum(judged.get("B", {}))
        else:
            n_fail += 1
            a_score = b_score = 0

        rc2_score = a_score if a_is_rc2 else b_score
        raw_score = b_score if a_is_rc2 else a_score
        if meta.get("ok"):
            raw_totals.append(raw_score)
            rc2_totals.append(rc2_score)

        winner_label = "tie_or_unknown"
        if meta.get("ok"):
            w = (judged.get("winner") or "").upper()
            if w == "A":
                winner_label = "rc2_governed" if a_is_rc2 else "raw"
            elif w == "B":
                winner_label = "raw" if a_is_rc2 else "rc2_governed"
            else:
                winner_label = "tie"

        rows.append({
            "id": p["id"], "category": p["category"], "query": p["query"],
            "expected_route": p.get("expected_route"),
            "raw_response_excerpt": p["raw_response"][:240] + ("…" if len(p["raw_response"]) > 240 else ""),
            "rc1_governed_response_excerpt": (p.get("rc1_governed_response", "") or "")[:240],
            "rc2_governed_response_excerpt": p["rc2_governed_response"][:240] + ("…" if len(p["rc2_governed_response"]) > 240 else ""),
            "rc1_governed_meta": p.get("rc1_governed_meta", {}),
            "rc2_governed_meta": p.get("rc2_governed_meta", {}),
            "a_was_rc2": a_is_rc2,
            "judge": judged, "judge_meta": meta,
            "raw_total_20": raw_score,
            "rc2_total_20": rc2_score,
            "rc1_raw_total_20_from_rc1_run": p.get("rc1_raw_total_20"),
            "rc1_governed_total_20_from_rc1_run": p.get("rc1_governed_total_20"),
            "winner_label_raw_vs_rc2": winner_label,
        })

        if i % 5 == 0 or i == len(pairs):
            elapsed = time.time() - t0
            mraw = sum(raw_totals) / len(raw_totals) if raw_totals else 0
            mrc2 = sum(rc2_totals) / len(rc2_totals) if rc2_totals else 0
            print(f"  [{i}/{len(pairs)}] elapsed={elapsed:.1f}s "
                  f"ok={n_ok} fail={n_fail} "
                  f"raw_mean={mraw:.2f} rc2_mean={mrc2:.2f} "
                  f"delta={mrc2-mraw:+.2f} tokens={token_total['total_tokens']}",
                  flush=True)

    PER_QUERY_OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    n_judged = len(raw_totals)
    raw_mean = sum(raw_totals) / n_judged if n_judged else 0
    rc2_mean = sum(rc2_totals) / n_judged if n_judged else 0
    delta_rc2_vs_raw = rc2_mean - raw_mean

    by_cat = {}
    for r in rows:
        c = r["category"]
        if c not in by_cat:
            by_cat[c] = {"n": 0, "raw_sum": 0, "rc2_sum": 0,
                          "rc1_raw_sum": 0, "rc1_rc1_sum": 0,
                          "n_rc1_known": 0,
                          "wins": {"raw": 0, "rc2_governed": 0, "tie": 0, "tie_or_unknown": 0}}
        by_cat[c]["n"] += 1
        if r["judge_meta"].get("ok"):
            by_cat[c]["raw_sum"] += r["raw_total_20"]
            by_cat[c]["rc2_sum"] += r["rc2_total_20"]
        # RC1 cross-data, when present.
        if r.get("rc1_governed_total_20_from_rc1_run") is not None:
            by_cat[c]["rc1_raw_sum"] += int(r.get("rc1_raw_total_20_from_rc1_run") or 0)
            by_cat[c]["rc1_rc1_sum"] += int(r.get("rc1_governed_total_20_from_rc1_run") or 0)
            by_cat[c]["n_rc1_known"] += 1
        wl = r["winner_label_raw_vs_rc2"]
        bucket = wl if wl in by_cat[c]["wins"] else "tie_or_unknown"
        by_cat[c]["wins"][bucket] += 1

    by_cat_summary = {}
    for c, d in by_cat.items():
        n = d["n"]; nr = d["n_rc1_known"]
        by_cat_summary[c] = {
            "n": n,
            "raw_mean": round(d["raw_sum"] / n, 2) if n else None,
            "rc2_mean": round(d["rc2_sum"] / n, 2) if n else None,
            "delta_rc2_vs_raw": round((d["rc2_sum"] - d["raw_sum"]) / n, 2) if n else None,
            "rc1_raw_mean_from_rc1_run": round(d["rc1_raw_sum"] / nr, 2) if nr else None,
            "rc1_governed_mean_from_rc1_run": round(d["rc1_rc1_sum"] / nr, 2) if nr else None,
            "rc1_delta_from_rc1_run": round((d["rc1_rc1_sum"] - d["rc1_raw_sum"]) / nr, 2) if nr else None,
            "delta_rc2_vs_rc1": (round(((d["rc2_sum"] - d["raw_sum"]) / n) - ((d["rc1_rc1_sum"] - d["rc1_raw_sum"]) / nr), 2) if (n and nr) else None),
            "wins": d["wins"],
        }

    axis_keys = ("route_accuracy", "answer_correctness", "restraint_quality",
                 "conciseness", "overall_usefulness")
    raw_axis_means, rc2_axis_means = {}, {}
    for k in axis_keys:
        rvals, c2vals = [], []
        for r in rows:
            if not r["judge_meta"].get("ok") or not r["judge"]:
                continue
            jd = r["judge"]; ar = r["a_was_rc2"]
            try:
                a_v = int(jd.get("A", {}).get(k, 0))
                b_v = int(jd.get("B", {}).get(k, 0))
            except Exception:
                continue
            c2vals.append(a_v if ar else b_v)
            rvals.append(b_v if ar else a_v)
        raw_axis_means[k] = round(sum(rvals) / len(rvals), 2) if rvals else None
        rc2_axis_means[k] = round(sum(c2vals) / len(c2vals), 2) if c2vals else None

    if n_judged == 0:
        thesis = "INCONCLUSIVE_NO_JUDGE"
    elif delta_rc2_vs_raw >= 2.0:
        thesis = "STRONGLY_SUPPORTS"
    elif delta_rc2_vs_raw >= 1.0:
        thesis = "SUPPORTS"
    elif delta_rc2_vs_raw >= 0.3:
        thesis = "WEAKLY_SUPPORTS"
    elif delta_rc2_vs_raw > -0.3:
        thesis = "INCONCLUSIVE"
    elif delta_rc2_vs_raw > -1.0:
        thesis = "WEAKLY_WEAKENS"
    else:
        thesis = "WEAKENS"

    summary = {
        "test": "p9_rc2_raw_vs_governed",
        "n_total": len(rows),
        "n_judged_ok": n_judged,
        "n_judge_fail": n_fail,
        "judge_model": JUDGE_MODEL,
        "judge_provider": "groq",
        "user_agent_used": USER_AGENT,
        "ab_blind_used": True,
        "deterministic_seed": 20260429,
        "raw_mean_total20": round(raw_mean, 2),
        "rc2_mean_total20": round(rc2_mean, 2),
        "delta_rc2_vs_raw_total20": round(delta_rc2_vs_raw, 2),
        "raw_axis_means": raw_axis_means,
        "rc2_axis_means": rc2_axis_means,
        "axis_deltas": {k: round((rc2_axis_means.get(k) or 0) - (raw_axis_means.get(k) or 0), 2)
                         for k in axis_keys},
        "by_category": by_cat_summary,
        "thesis_signal_rc2_vs_raw": thesis,
        "groq_token_usage": token_total,
        "configuration": {
            "raw_generator": "huihui_ai/qwen3.5-abliterated:9b",
            "governed_layer_rc2": "MMV Core v0.1-rc2 candidate (route-calibration patch) via PseudoUISession",
            "governed_layer_rc1_for_compare": "MMV Core v0.1-rc1 (frozen) — saved Phase 5C run",
            "judge": "Groq openai/gpt-oss-120b (User-Agent fix)",
        },
        "caveats": [
            "Post-calibration repair check. The same query set was previously "
            "used to diagnose rc1 weaknesses; this is NOT an independent "
            "validation.",
            "Raw responses were reused from Phase 5C Test 2 verbatim. RC2 "
            "governed responses were regenerated by the rc2 runtime.",
            "Single judge (Groq openai/gpt-oss-120b). No multi-judge consensus.",
            "Judge model family (openai/gpt-oss) overlaps with the prior "
            "local-20B fallback; cross-judge agreement here is between "
            "siblings, not a fully independent panel.",
            "Length-bias guard explicitly included in the judge prompt.",
            "Pseudo-UI only; not real-UI performance validation.",
            "NOT Phase 6 full evaluation. NOT deployment-wide validation.",
        ],
    }

    SUMMARY_OUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md = []
    md.append("# RC2 vs Raw — Groq 120B judge summary")
    md.append("")
    md.append(f"- N total: {len(rows)}")
    md.append(f"- N judged ok: {n_judged}")
    md.append(f"- Judge: `{JUDGE_MODEL}` via Groq (User-Agent fix)")
    md.append("")
    md.append(f"- Raw mean (0–20):           **{raw_mean:.2f}**")
    md.append(f"- RC2 governed mean (0–20):  **{rc2_mean:.2f}**")
    md.append(f"- Δ (rc2 − raw):             **{delta_rc2_vs_raw:+.2f}**")
    md.append(f"- Thesis signal (rc2 vs raw): **{thesis}**")
    md.append(f"- Token usage (Groq): {token_total['total_tokens']}")
    md.append("")
    md.append("## Per-axis means (0–4)")
    md.append("| axis | raw | rc2 | Δ |")
    md.append("|---|---|---|---|")
    for k in axis_keys:
        rv = raw_axis_means.get(k); gv = rc2_axis_means.get(k)
        if rv is None or gv is None:
            md.append(f"| {k} | — | — | — |")
        else:
            md.append(f"| {k} | {rv} | {gv} | {gv-rv:+.2f} |")
    md.append("")
    md.append("## Per-category (mean total 0–20)")
    md.append("")
    md.append("| category | n | raw | rc2 | Δ rc2−raw | RC1 Δ (from rc1 judge run) | Δ rc2 vs rc1 | wins (raw / rc2 / tie) |")
    md.append("|---|---|---|---|---|---|---|---|")
    for c, d in by_cat_summary.items():
        w = d["wins"]
        ties = w.get("tie", 0) + w.get("tie_or_unknown", 0)
        md.append(
            f"| {c} | {d['n']} | "
            f"{d['raw_mean'] if d['raw_mean'] is not None else '—'} | "
            f"{d['rc2_mean'] if d['rc2_mean'] is not None else '—'} | "
            f"{d['delta_rc2_vs_raw'] if d['delta_rc2_vs_raw'] is not None else '—'} | "
            f"{d['rc1_delta_from_rc1_run'] if d['rc1_delta_from_rc1_run'] is not None else '—'} | "
            f"{d['delta_rc2_vs_rc1'] if d['delta_rc2_vs_rc1'] is not None else '—'} | "
            f"{w.get('raw',0)}/{w.get('rc2_governed',0)}/{ties} |"
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
    print(f"thesis: {thesis}  delta rc2−raw: {delta_rc2_vs_raw:+.2f}  n_judged: {n_judged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
