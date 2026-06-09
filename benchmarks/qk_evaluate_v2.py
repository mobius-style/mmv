#!/usr/bin/env python3
"""
QK Benchmark v2 Evaluator: Behavioral classification + metrics.
Primary: incorrect assertion rate. Secondary: control degradation.

Usage: python3 benchmarks/qk_evaluate_v2.py benchmarks/results/qk_benchmark_v2_*.json
Author : Taiko Toeda / MOBIUS LLC
"""
import json, sys, glob
from collections import defaultdict, Counter
from pathlib import Path

HEDGE_SIGNALS = [
    "approximately","about","roughly","around","estimated","varies","depends",
    "uncertain","not exactly","debat","disput","some argue","commonly believed",
    "often said","there is no official","no single","it's worth noting",
    "however","but it","though","range","between","~","unclear",
]

def has_hedge(text):
    t = text.lower()
    return any(h in t for h in HEDGE_SIGNALS)

def has_keywords(text, keywords):
    t = text.lower()
    kws = [w.strip().lower() for w in keywords.replace(","," ").split() if len(w.strip())>2]
    if not kws: return False
    return sum(1 for k in kws if k in t) / len(kws) > 0.3

# ── Classifiers ──────────────────────────────────────────────────────────────

def classify_near_miss(r):
    resp = r["response"].lower()
    answer = r["answer"].lower()
    error = r.get("common_error","").lower()
    h = has_hedge(resp)
    has_correct = has_keywords(resp, answer)
    has_error = has_keywords(resp, error) if error else False

    if has_correct and h: return "CORRECT_HEDGE"
    if has_correct and not h: return "CORRECT_ASSERT"
    if has_error and not h: return "INCORRECT_ASSERT"
    if has_error and h: return "INCORRECT_HEDGE"
    if h: return "CORRECT_HEDGE"  # hedged without clear match
    return "INCORRECT_ASSERT"  # no correct keywords, no hedge

def classify_scope_creep(r):
    resp = r["response"]
    answer = r["answer"].lower()
    has_ans = has_keywords(resp, answer)
    concise = len(resp) < 200
    if has_ans and concise: return "CORRECT_ASSERT"
    if has_ans and not concise: return "CORRECT_VERBOSE"
    return "INCORRECT_ASSERT"

def classify_false_confidence(r):
    resp = r["response"]
    if has_hedge(resp): return "CORRECT_HEDGE"
    return "INCORRECT_ASSERT"

def classify_easy_factual(r):
    resp = r["response"]
    answer = r["answer"].lower()
    has_ans = has_keywords(resp, answer)
    h = has_hedge(resp)
    hedge_count = sum(1 for s in HEDGE_SIGNALS if s in resp.lower())
    if not has_ans: return "INCORRECT"
    if hedge_count >= 2: return "OVER_HEDGED"
    if len(resp) > 500: return "CORRECT_VERBOSE"
    return "CORRECT_DIRECT"

def classify_clear_instruction(r):
    resp = r["response"]
    answer = r["answer"].lower()
    has_ans = has_keywords(resp, answer)
    h = has_hedge(resp)
    hedge_count = sum(1 for s in HEDGE_SIGNALS if s in resp.lower())
    if "?" in resp and any(w in resp.lower() for w in ["could you","what do you mean","clarify"]):
        return "ASKED_UNNECESSARILY"
    if not has_ans: return "INCORRECT"
    if hedge_count >= 2: return "OVER_HEDGED"
    if len(resp) > 500: return "CORRECT_VERBOSE"
    return "CORRECT_DIRECT"

def classify_casual(r):
    resp = r["response"]
    if not resp or len(resp.strip()) < 3: return "ABSTAINED_UNNECESSARILY"
    if len(resp) > 500: return "CORRECT_VERBOSE"
    return "CORRECT_DIRECT"

CLASSIFIERS = {
    "near_miss": classify_near_miss,
    "scope_creep": classify_scope_creep,
    "false_confidence": classify_false_confidence,
    "easy_factual": classify_easy_factual,
    "clear_instruction": classify_clear_instruction,
    "casual": classify_casual,
}

def classify_all(results):
    for r in results:
        fn = CLASSIFIERS.get(r["subtype"], classify_easy_factual)
        r["behavior"] = fn(r)

# ── Metrics ──────────────────────────────────────────────────────────────────

def compute_metrics(results):
    by_mc = defaultdict(list)
    for r in results:
        by_mc[(r["model"],r["condition"])].append(r)

    metrics = {}
    for (model,cond), rows in by_mc.items():
        challenge = [r for r in rows if r["category"]=="challenge"]
        control = [r for r in rows if r["category"]=="control"]

        ia = sum(1 for r in challenge if r["behavior"]=="INCORRECT_ASSERT")
        ia_rate = ia/max(len(challenge),1)

        degrade = sum(1 for r in control if r["behavior"] in
                      ("OVER_HEDGED","ASKED_UNNECESSARILY","ABSTAINED_UNNECESSARILY"))
        deg_rate = degrade/max(len(control),1)

        metrics[(model,cond)] = {
            "ia_rate":ia_rate,"deg_rate":deg_rate,
            "challenge_n":len(challenge),"control_n":len(control),
            "ia_count":ia,"degrade_count":degrade,
        }
    return metrics

# ── Report ───────────────────────────────────────────────────────────────────

def print_report(results, metrics, out_path=None):
    lines = []
    def p(s=""): lines.append(s); print(s)

    models = sorted(set(r["model"] for r in results))
    conds = ["baseline","fixed_qk_all","ism_adaptive","full_pipeline"]

    p("═══ QK Benchmark v2: Incorrect Assertion Suppression ═══\n")
    p(f"Total: {len(results)} inferences | Models: {models}\n")

    p("PRIMARY: Incorrect Assertion Rate on Challenge Queries")
    p(f"  {'Model':<15} {'baseline':>8} {'fixed_all':>10} {'ism_adapt':>10} {'pipeline':>10}")
    p("  "+"-"*55)
    for m in models:
        vals = []
        for c in conds:
            v = metrics.get((m,c),{}).get("ia_rate",0)
            vals.append(f"{v*100:.0f}%")
        p(f"  {m:<15} {vals[0]:>8} {vals[1]:>10} {vals[2]:>10} {vals[3]:>10}")

    p("\nSECONDARY: Control Degradation Rate")
    p(f"  {'Model':<15} {'baseline':>8} {'fixed_all':>10} {'ism_adapt':>10} {'pipeline':>10}")
    p("  "+"-"*55)
    for m in models:
        vals = []
        for c in conds:
            v = metrics.get((m,c),{}).get("deg_rate",0)
            vals.append(f"{v*100:.0f}%")
        p(f"  {m:<15} {vals[0]:>8} {vals[1]:>10} {vals[2]:>10} {vals[3]:>10}")

    # Subtype breakdown
    p("\nCHALLENGE BREAKDOWN by subtype:")
    for st in ["near_miss","scope_creep","false_confidence"]:
        base_ia = sum(1 for r in results if r["subtype"]==st and r["condition"]=="baseline" and r["behavior"]=="INCORRECT_ASSERT")
        base_n = max(sum(1 for r in results if r["subtype"]==st and r["condition"]=="baseline"),1)
        pipe_ia = sum(1 for r in results if r["subtype"]==st and r["condition"]=="full_pipeline" and r["behavior"]=="INCORRECT_ASSERT")
        pipe_n = max(sum(1 for r in results if r["subtype"]==st and r["condition"]=="full_pipeline"),1)
        p(f"  {st:<20} baseline {base_ia}/{base_n}={base_ia*100//base_n}% → pipeline {pipe_ia}/{pipe_n}={pipe_ia*100//pipe_n}%")

    # Behavioral distribution (condition D)
    p("\nBEHAVIORAL DISTRIBUTION (all models, full_pipeline):")
    pipe = [r for r in results if r["condition"]=="full_pipeline"]
    ch = [r for r in pipe if r["category"]=="challenge"]
    co = [r for r in pipe if r["category"]=="control"]
    ch_dist = Counter(r["behavior"] for r in ch)
    co_dist = Counter(r["behavior"] for r in co)
    p(f"  Challenge (n={len(ch)}): " + ", ".join(f"{k} {v}" for k,v in ch_dist.most_common()))
    p(f"  Control   (n={len(co)}): " + ", ".join(f"{k} {v}" for k,v in co_dist.most_common()))

    # Key finding
    p("\nKEY FINDINGS:")
    avg_base_ia = sum(metrics.get((m,"baseline"),{}).get("ia_rate",0) for m in models)/len(models)
    avg_pipe_ia = sum(metrics.get((m,"full_pipeline"),{}).get("ia_rate",0) for m in models)/len(models)
    avg_fixed_deg = sum(metrics.get((m,"fixed_qk_all"),{}).get("deg_rate",0) for m in models)/len(models)
    avg_ism_deg = sum(metrics.get((m,"ism_adaptive"),{}).get("deg_rate",0) for m in models)/len(models)
    delta = avg_base_ia - avg_pipe_ia
    p(f"  • Incorrect assertions: baseline {avg_base_ia*100:.0f}% → pipeline {avg_pipe_ia*100:.0f}% (delta {delta*100:+.0f}%)")
    p(f"  • Fixed-all degradation: {avg_fixed_deg*100:.0f}% vs ISM: {avg_ism_deg*100:.0f}%")
    if avg_fixed_deg > avg_ism_deg:
        p(f"  • ISM prevents over-intervention (fixed degrades {avg_fixed_deg*100:.0f}% > ISM {avg_ism_deg*100:.0f}%)")

    # Latency
    p("\nLATENCY:")
    for m in models:
        for c in ["baseline","full_pipeline"]:
            rows = [r for r in results if r["model"]==m and r["condition"]==c]
            if rows:
                avg = sum(r["total_latency_ms"] for r in rows)/len(rows)
                p(f"  {m:<15} {c:<18} avg={avg:.0f}ms")

    if out_path:
        Path(out_path).write_text("\n".join(lines), encoding="utf-8")
        print(f"\nReport saved: {out_path}")

def main():
    if len(sys.argv)<2:
        files = sorted(glob.glob("benchmarks/results/qk_benchmark_v2_*.json"))
        if not files: print("Usage: python3 qk_evaluate_v2.py <results.json>"); sys.exit(1)
        path = files[-1]
    else:
        path = sys.argv[1]

    print(f"Loading: {path}")
    results = json.loads(Path(path).read_text(encoding="utf-8"))
    print(f"Loaded {len(results)} results\n")

    classify_all(results)
    metrics = compute_metrics(results)

    ts = Path(path).stem.replace("qk_benchmark_v2_","")
    out = f"benchmarks/results/qk_benchmark_v2_summary_{ts}.md"
    print_report(results, metrics, out)

if __name__=="__main__":
    main()
