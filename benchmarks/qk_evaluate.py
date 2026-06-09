#!/usr/bin/env python3
"""
QK Benchmark Evaluator — rule-based scoring on 5 axes.

Usage: python3 benchmarks/qk_evaluate.py benchmarks/results/qk_benchmark_*.json

Author : Taiko Toeda / MOBIUS LLC
"""
import json, sys, glob
from collections import defaultdict
from pathlib import Path


def score_factual(r):
    resp = r["response"].lower()
    gt = r["ground_truth"].lower()
    kws = [w.strip() for w in gt.replace(",", " ").replace("(", " ").replace(")", " ").split() if len(w.strip()) > 2]
    matches = sum(1 for kw in kws if kw in resp)
    ratio = matches / max(len(kws), 1)
    first = resp.split(".")[0] if "." in resp else resp[:200]
    key3 = [w for w in kws if len(w) > 3][:3]
    direct = sum(1 for t in key3 if t in first)
    hedges = ["uncertain", "approximately", "roughly", "about", "i'm not sure", "may ", "might", "possibly"]
    has_hedge = any(h in resp for h in hedges)
    fabs = ["as of my", "i believe", "reportedly", "i think"]
    has_fab = any(f in resp for f in fabs)
    length = len(resp)
    return {
        "accuracy": 5 if ratio > 0.6 else (4 if ratio > 0.4 else (3 if ratio > 0.2 else (2 if ratio > 0 else 1))),
        "directness": min(5, 3 + direct),
        "uncertainty": 4 if has_hedge else 3,
        "hallucination": 2 if has_fab else 4,
        "conciseness": 5 if length < 300 else (4 if length < 600 else (3 if length < 1000 else 2)),
    }


def score_underspec(r):
    resp = r["response"].lower()
    asks = ["what do you mean", "could you clarify", "which", "can you specify",
            "what specific", "more context", "please provide", "could you tell me", "?"]
    asked = sum(1 for a in asks if a in resp)
    committed = any(w in resp for w in ["the answer is", "you should", "i recommend", "definitely"])
    return {
        "accuracy": min(5, 2 + asked) if not committed else 1,
        "directness": 4 if asked >= 2 else (3 if asked >= 1 else 2),
        "uncertainty": 5 if not committed else 1,
        "hallucination": 5 if not committed else 2,
        "conciseness": 4 if len(resp) < 500 else 3,
    }


def score_opinion(r):
    resp = r["response"].lower()
    persp = ["on the other hand", "however", "alternatively", "some people",
             "it depends", "pros and cons", "advantages", "disadvantages", "tradeoff"]
    p = sum(1 for x in persp if x in resp)
    cert = ["definitely", "absolutely", "the best is", "you must", "always"]
    c = sum(1 for x in cert if x in resp)
    return {
        "accuracy": min(5, 2 + p),
        "directness": 4 if len(resp) > 50 else 3,
        "uncertainty": min(5, 3 + p) if c == 0 else 2,
        "hallucination": 4 if c == 0 else 2,
        "conciseness": 4 if len(resp) < 800 else 3,
    }


def score_casual(r):
    length = len(r["response"])
    return {
        "accuracy": 4 if length > 5 else 2,
        "directness": 4 if length < 500 else 3,
        "uncertainty": 3,
        "hallucination": 3,
        "conciseness": 5 if length < 200 else (4 if length < 400 else 3),
    }


SCORERS = {"factual": score_factual, "epistemic": score_factual,
           "underspec": score_underspec, "opinion": score_opinion, "casual": score_casual}
AXES = ["accuracy", "directness", "uncertainty", "hallucination", "conciseness"]


def evaluate(results):
    for r in results:
        cat = r["category"]
        scorer = SCORERS.get(cat, score_casual)
        r["scores"] = scorer(r)
        r["mean_score"] = sum(r["scores"].values()) / 5


def aggregate(results):
    # Per condition
    by_cond = defaultdict(list)
    for r in results:
        by_cond[r["condition"]].append(r)

    # Per model x condition
    by_mc = defaultdict(list)
    for r in results:
        by_mc[(r["model"], r["condition"])].append(r)

    # Per category x condition
    by_cc = defaultdict(list)
    for r in results:
        by_cc[(r["category"], r["condition"])].append(r)

    return by_cond, by_mc, by_cc


def mean_axes(rows):
    if not rows:
        return {a: 0 for a in AXES}
    return {a: sum(r["scores"][a] for r in rows) / len(rows) for a in AXES}


def mean_score(rows):
    return sum(r["mean_score"] for r in rows) / max(len(rows), 1)


def print_report(results, out_path=None):
    by_cond, by_mc, by_cc = aggregate(results)
    lines = []

    def p(s=""):
        lines.append(s)
        print(s)

    p("# QK Effectiveness Benchmark Report\n")
    p(f"Total inferences: {len(results)}")
    p(f"Models: {sorted(set(r['model'] for r in results))}")
    p(f"Conditions: {sorted(set(r['condition'] for r in results))}")
    p(f"Categories: {sorted(set(r['category'] for r in results))}\n")

    # Table 1: Per condition
    p("## 1. Mean Score by Condition\n")
    p(f"{'Condition':<20} {'accuracy':>8} {'direct':>8} {'uncert':>8} {'halluc':>8} {'concise':>8} {'MEAN':>8}")
    p("-" * 76)
    for cond in ["baseline", "fixed_qk", "ism_adaptive", "full_pipeline"]:
        rows = by_cond.get(cond, [])
        ma = mean_axes(rows)
        ms = mean_score(rows)
        p(f"{cond:<20} {ma['accuracy']:>8.2f} {ma['directness']:>8.2f} {ma['uncertainty']:>8.2f} {ma['hallucination']:>8.2f} {ma['conciseness']:>8.2f} {ms:>8.2f}")

    # Table 2: Per model x condition
    p("\n## 2. Mean Score by Model x Condition\n")
    p(f"{'Model':<15} {'Condition':<20} {'MEAN':>6} {'accuracy':>8} {'direct':>8} {'halluc':>8}")
    p("-" * 75)
    for model in sorted(set(r["model"] for r in results)):
        for cond in ["baseline", "fixed_qk", "ism_adaptive", "full_pipeline"]:
            rows = by_mc.get((model, cond), [])
            if not rows:
                continue
            ma = mean_axes(rows)
            ms = mean_score(rows)
            p(f"{model:<15} {cond:<20} {ms:>6.2f} {ma['accuracy']:>8.2f} {ma['directness']:>8.2f} {ma['hallucination']:>8.2f}")

    # Table 3: Per category x condition
    p("\n## 3. Mean Score by Category x Condition\n")
    p(f"{'Category':<12} {'Condition':<20} {'MEAN':>6} {'n':>4}")
    p("-" * 46)
    for cat in ["factual", "epistemic", "underspec", "opinion", "casual"]:
        for cond in ["baseline", "ism_adaptive", "full_pipeline"]:
            rows = by_cc.get((cat, cond), [])
            if not rows:
                continue
            ms = mean_score(rows)
            p(f"{cat:<12} {cond:<20} {ms:>6.2f} {len(rows):>4}")

    # Delta: full_pipeline vs baseline
    p("\n## 4. Improvement: full_pipeline vs baseline\n")
    for model in sorted(set(r["model"] for r in results)):
        base = by_mc.get((model, "baseline"), [])
        pipe = by_mc.get((model, "full_pipeline"), [])
        if base and pipe:
            delta = mean_score(pipe) - mean_score(base)
            p(f"  {model:<15} delta={delta:+.2f} (baseline={mean_score(base):.2f} → pipeline={mean_score(pipe):.2f})")

    # Latency
    p("\n## 5. Latency Summary\n")
    for model in sorted(set(r["model"] for r in results)):
        for cond in ["baseline", "full_pipeline"]:
            rows = by_mc.get((model, cond), [])
            if not rows:
                continue
            avg_lat = sum(r["total_latency_ms"] for r in rows) / len(rows)
            p(f"  {model:<15} {cond:<20} avg={avg_lat:.0f}ms")

    if out_path:
        Path(out_path).write_text("\n".join(lines), encoding="utf-8")
        print(f"\nReport saved: {out_path}")


def main():
    if len(sys.argv) < 2:
        files = sorted(glob.glob("benchmarks/results/qk_benchmark_*.json"))
        if not files:
            print("Usage: python3 benchmarks/qk_evaluate.py <results.json>")
            sys.exit(1)
        path = files[-1]
    else:
        path = sys.argv[1]

    print(f"Loading: {path}")
    results = json.loads(Path(path).read_text(encoding="utf-8"))
    print(f"Loaded {len(results)} results\n")

    evaluate(results)

    ts = Path(path).stem.replace("qk_benchmark_", "")
    out = f"benchmarks/results/qk_benchmark_summary_{ts}.md"
    print_report(results, out)


if __name__ == "__main__":
    main()
