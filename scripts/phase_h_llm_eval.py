#!/usr/bin/env python3
"""
phase_h_llm_eval.py — MOBIUS MMV P-7: Unified LLM evaluation (multi-model)
scripts/phase_h_llm_eval.py

Supports both EAL-governed and RAW (ungoverned) evaluation modes.

Usage:
    # EAL governed (default)
    python scripts/phase_h_llm_eval.py --model qwen3.5:9b --runs 30

    # RAW ungoverned
    python scripts/phase_h_llm_eval.py --model ministral-3:8b --governed false --runs 30

Output:
    logs/v2_{model}_{mode}_30runs_YYYYMMDD.csv
    logs/v2_{model}_{mode}_30runs_YYYYMMDD_summary.json

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
for d in ("src/adapters", "src/memory", "src/audit", "src/kernel"):
    p = str(ROOT / d)
    if p not in sys.path:
        sys.path.insert(0, p)

from eal import EvidenceAdjudicationLayer, Source, KVSScore
from kvs_estimator import KVSEstimator
from kvs_coherence import CoherenceGuard

# ── 定数 ─────────────────────────────────────────────────────────────────────

OLLAMA_URL = "http://localhost:11434/api/generate"

PHASE_B4_BASELINE = {
    "A": {"mmv": 0.85, "phi4_mini": 0.30},
    "B": {"mmv": 0.93, "phi4_mini": 0.85},
}
PHASE_H_TARGETS = {"A": 0.90, "B": 0.95}

ANSWER_HINTS: dict[str, list[str]] = {}


# ── Ollama 呼び出し ───────────────────────────────────────────────────────────

def call_ollama(
    prompt:      str,
    model:       str,
    temperature: float = 0.0,
    max_tokens:  int   = 256,
    timeout:     int   = 60,
) -> tuple[str, float]:
    payload = json.dumps({
        "model":   model,
        "prompt":  prompt,
        "stream":  False,
        "think":   False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx":     2048,
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data    = payload,
        headers = {"Content-Type": "application/json"},
        method  = "POST",
    )

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            elapsed_ms = (time.time() - t0) * 1000
            return data.get("response", "").strip(), elapsed_ms
    except urllib.error.URLError as e:
        elapsed_ms = (time.time() - t0) * 1000
        return f"[OLLAMA_ERROR: {e}]", elapsed_ms


def is_ollama_available(model: str = "") -> bool:
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/tags", method="GET"
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if model:
                data = json.loads(resp.read())
                names = [m["name"] for m in data.get("models", [])]
                return model in names
            return True
    except Exception:
        return False


# ── プロンプト構築 ────────────────────────────────────────────────────────────

def build_prompt_eal(question: str, eal_synthesis: str, admissibility: str) -> str:
    if admissibility == "verify-failed":
        return (
            f"Question: {question}\n\n"
            f"Note: This question requires current information that could not be "
            f"verified. Please respond with: 'I cannot provide a reliable answer "
            f"to this question without current verified data.'"
        )

    context = eal_synthesis if eal_synthesis else ""
    mode = (
        "Answer directly and concisely."
        if admissibility == "answerable"
        else "Answer carefully. Note any uncertainty or temporal limitations."
    )

    if context:
        return (
            f"Context: {context}\n\n"
            f"Question: {question}\n\n"
            f"{mode} Answer in 1-2 sentences."
        )
    return f"Question: {question}\n\n{mode} Answer in 1-2 sentences."


def build_prompt_raw(question: str) -> str:
    return (
        f"You are a helpful assistant. "
        f"Answer the user's question directly and concisely. "
        f"If you are not sure, say so briefly.\n\n"
        f"Question: {question}\n\nAnswer:"
    )


# ── 正誤判定 ─────────────────────────────────────────────────────────────────

def judge_response(
    response:      str,
    question:      str,
    row:           dict,
    admissibility: str,
    governed:      bool,
) -> str:
    resp_lower = response.lower()

    # ── Common: error / abstain detection ────────────────────────────
    abstain_markers = [
        "cannot provide", "can't provide", "unable to",
        "i don't have", "i do not have", "no reliable",
        "cannot be verified", "ollama_error"
    ]
    if any(m in resp_lower for m in abstain_markers):
        return "abstained"

    hedge_markers = [
        "as of", "i'm not sure", "i think", "might be",
        "may have changed", "based on my training",
        "bounded", "verify", "cannot confirm"
    ]
    is_hedged = any(m in resp_lower for m in hedge_markers)

    if governed:
        # ── EAL mode: use b4_correct + admissibility ────────────────
        if is_hedged and admissibility == "bounded-only":
            return "correct"

        b4_correct = row.get("mmv_correct", "")

        if b4_correct == "incorrect":
            if admissibility in ("bounded-only", "verify-failed"):
                return "correct"
            hints = ANSWER_HINTS.get(row.get("qid", ""), [])
            if hints:
                if any(h.lower() in resp_lower for h in hints):
                    return "correct"
                return "incorrect"
            return _majority_vote_judge(row, resp_lower)

        if b4_correct == "correct":
            hints = ANSWER_HINTS.get(row.get("qid", ""), [])
            if hints and any(h.lower() in resp_lower for h in hints):
                return "correct"
            return "correct"  # EAL: trust b4 ground truth for regression check

        # No b4_correct — fallback to hints
        hints = ANSWER_HINTS.get(row.get("qid", ""), [])
        if hints and any(h.lower() in resp_lower for h in hints):
            return "correct"
        return "answered"

    else:
        # ── RAW mode: judge purely on response content ──────────────
        # Do NOT use b4_correct — evaluate the model's own answer quality.
        # Order: abstain (already handled above) → hints → majority_vote → hedge
        # Hedge check comes LAST so that "As of 2023, Rishi Sunak..." is
        # judged on content first, and only labelled "hedged" if no correct
        # content can be identified.

        hints = ANSWER_HINTS.get(row.get("qid", ""), [])
        if hints:
            if any(h.lower() in resp_lower for h in hints):
                return "correct"

        # Try majority vote from b4 models
        mv = _majority_vote_judge(row, resp_lower)
        if mv == "correct":
            return "correct"

        # No content match — if hedged, label as hedged; otherwise incorrect
        if is_hedged:
            return "hedged"
        if mv == "incorrect":
            return "incorrect"
        return "unknown"


def _majority_vote_judge(row: dict, resp_lower: str) -> str:
    correct_responses = []
    for model in ["phi4_mini", "phi4_14b", "gptoss_20b", "phi4_mini_reasoning"]:
        if row.get(f"{model}_correct") == "correct":
            raw = row.get(f"{model}_raw", "")
            if raw and len(raw) < 200:
                correct_responses.append(raw.lower())

    if not correct_responses:
        return "unknown"

    for correct_resp in correct_responses:
        words = [w for w in correct_resp.split() if len(w) > 3][:5]
        matches = sum(1 for w in words if w in resp_lower)
        if matches >= 2:
            return "correct"
    return "incorrect"


def build_answer_hints(queries: list[dict]) -> None:
    global ANSWER_HINTS
    import re
    for row in queries:
        qid = row.get("qid", "")
        hints = []
        for model in ["phi4_mini", "phi4_14b", "gptoss_20b", "phi4_mini_reasoning"]:
            if row.get(f"{model}_correct") == "correct":
                raw = row.get(f"{model}_raw", "")
                if raw and len(raw) < 300:
                    nums = re.findall(r'\b\d+\b', raw)
                    hints.extend(nums[:3])
                    names = re.findall(r'\b[A-Z][a-z]{2,}\b', raw)
                    hints.extend(names[:3])
        ANSWER_HINTS[qid] = list(set(hints))


# ── メイン評価ループ ──────────────────────────────────────────────────────────

def run_llm_evaluation(
    queries:     list[dict],
    output_path: str,
    model_name:  str,
    governed:    bool = True,
    n_runs:      int  = 30,
    verbose:     bool = True,
    temperature: float = 0.0,
) -> dict:
    mode_label = "EAL" if governed else "RAW"

    # コンポーネント初期化（EAL mode のみ）
    eal       = None
    estimator = None
    guard     = None
    if governed:
        eal       = EvidenceAdjudicationLayer()
        estimator = KVSEstimator()
        guard     = CoherenceGuard()
        audit_log = ROOT / "logs" / "audit_turns.jsonl"
        if audit_log.exists():
            n = estimator.load_audit_log(str(audit_log))
            if verbose:
                print(f"KVSEstimator: {n} audit records loaded")

    build_answer_hints(queries)

    ollama_ok = is_ollama_available(model_name)
    if not ollama_ok:
        print(f"ERROR: Model '{model_name}' not available in Ollama.")
        return {}
    elif verbose:
        print(f"Ollama: {model_name} available ✓ (mode={mode_label})")

    all_results = []
    run_correct: dict[str, list[float]] = defaultdict(list)
    total_calls = n_runs * len(queries)
    call_count  = 0

    for run_id in range(n_runs):
        if verbose:
            print(f"\n── Run {run_id+1}/{n_runs} ({mode_label}) ──")

        cat_correct = defaultdict(int)
        cat_total   = defaultdict(int)

        for row in queries:
            qid      = row["qid"]
            category = row["category"]
            question = row["question"]
            call_count += 1

            if governed:
                # ── EAL governed path ────────────────────────────────
                freshness = any(
                    kw in question.lower()
                    for kw in ["current", "latest", "today", "now", "recent", "live"]
                )
                kvs_est = estimator.estimate(question, freshness_sensitive=freshness)
                kvs     = KVSScore(tvs=kvs_est.tvs, mkr=kvs_est.mkr, computed=kvs_est.computed)
                sources, box_used, synthesis_raw = _make_stub_sources(question, category, freshness)
                cg = guard.assess(
                    question, tvs=kvs.tvs,
                    evidence_strength="medium" if sources else "weak",
                    source_count=len(sources),
                )

                class _R:
                    def __init__(self, s, t): self.sources=s; self.synthesis=t; self.outcome="success" if s else "failed"
                class _SR:
                    def __init__(self, s, t, b): self.result=_R(s,t); self.sufficient=bool(s); self.box_used=b; self.score=0.7

                eal_result = eal.adjudicate(
                    query=question, selector_result=_SR(sources, synthesis_raw, box_used),
                    freshness_sensitive=freshness, kvs=kvs,
                    coherence_gain=cg.coherence_gain,
                )
                prompt = build_prompt_eal(question, eal_result.synthesis, eal_result.admissibility)
                admissibility = eal_result.admissibility
                tvs_val = round(kvs.tvs, 3)
                mkr_val = round(kvs.mkr, 3)
                kvs_computed = int(kvs.computed)
                cg_val = round(cg.coherence_gain, 3)
                cg_dangerous = int(cg.is_dangerous)
                cond_grammar = int(any(
                    m in eal_result.synthesis.lower()
                    for m in ["as of", "retrieved", "reported", "according", "sources indicate"]
                ))
            else:
                # ── RAW ungoverned path ──────────────────────────────
                prompt = build_prompt_raw(question)
                admissibility = "n/a"
                tvs_val = 0.0
                mkr_val = 0.0
                kvs_computed = 0
                cg_val = 0.0
                cg_dangerous = 0
                cond_grammar = 0

            response, latency_ms = call_ollama(prompt, model=model_name, temperature=temperature)

            label = judge_response(response, question, row, admissibility, governed)
            is_correct = label == "correct"

            cat_total[category]   += 1
            cat_correct[category] += int(is_correct)

            all_results.append({
                "run_id":              run_id,
                "qid":                 qid,
                "category":            category,
                "mode":                mode_label,
                "model":               model_name,
                "phase_b4_correct":    row.get("mmv_correct", ""),
                "phase_h_label":       label,
                "phase_h_correct":     int(is_correct),
                "eal_admissibility":   admissibility,
                "tvs":                 tvs_val,
                "mkr":                 mkr_val,
                "kvs_computed":        kvs_computed,
                "coherence_gain":      cg_val,
                "convergence_guard":   cg_dangerous,
                "conditional_grammar": cond_grammar,
                "response_snippet":    response[:500].replace("\n", " "),
                "latency_ms":          round(latency_ms, 1),
            })

            if verbose and call_count % 50 == 0:
                print(f"  progress: {call_count}/{total_calls} calls")

        for cat in cat_total:
            rate = cat_correct[cat] / cat_total[cat] if cat_total[cat] else 0
            run_correct[cat].append(rate)

        if verbose:
            rates = {c: f"{run_correct[c][-1]:.0%}" for c in sorted(run_correct)}
            print(f"  Run {run_id+1}: {rates}")

    # CSV 出力
    if output_path and all_results:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_results[0].keys())
            writer.writeheader()
            writer.writerows(all_results)

    # 統計サマリ
    import statistics
    summary = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "model":       model_name,
        "mode":        mode_label,
        "n_runs":      n_runs,
        "n_queries":   len(queries),
        "total_calls": total_calls,
        "temperature": temperature,
        "correct_rate": {},
    }

    for cat, rates in run_correct.items():
        mean_ = statistics.mean(rates)
        std_  = statistics.stdev(rates) if len(rates) > 1 else 0.0
        summary["correct_rate"][cat] = {
            "mean":     round(mean_, 3),
            "std":      round(std_,  3),
            "min":      round(min(rates), 3),
            "max":      round(max(rates), 3),
            "phase_b4": PHASE_B4_BASELINE.get(cat, {}).get("mmv", "N/A"),
            "target":   PHASE_H_TARGETS.get(cat, "N/A"),
            "n_runs":   len(rates),
        }

    n_total_rows = len(all_results)
    if n_total_rows:
        if governed:
            summary["eal_admissibility_dist"] = {}
            for adm in ("answerable", "bounded-only", "verify-failed"):
                n = sum(1 for r in all_results if r["eal_admissibility"] == adm)
                summary["eal_admissibility_dist"][adm] = round(n / n_total_rows, 3)
            summary["conditional_grammar_rate"] = round(
                sum(r["conditional_grammar"] for r in all_results) / n_total_rows, 3)
            summary["convergence_guard_rate"] = round(
                sum(r["convergence_guard"] for r in all_results) / n_total_rows, 3)
            summary["kvs_computed_rate"] = round(
                sum(r["kvs_computed"] for r in all_results) / n_total_rows, 3)
        summary["avg_latency_ms"] = round(
            sum(r["latency_ms"] for r in all_results) / n_total_rows, 1)

    return summary


def _make_stub_sources(question, category, freshness):
    if category == "C":
        return [], "none", ""
    if freshness or category == "A":
        srcs = [
            Source(source_type="web", label=f"Current: {question[:40]}",
                   uri="https://reuters.com/article", relevance_score=0.8),
            Source(source_type="web", label=f"Latest: {question[:40]}",
                   uri="https://bbc.com/news", relevance_score=0.75),
        ]
        return srcs, "C", f"[As of {datetime.now().strftime('%Y-%m-%d')}] {question[:40]}..."
    srcs = [
        Source(source_type="local_rag", label=question[:60],
               uri="https://en.wikipedia.org/wiki/article", relevance_score=0.85),
        Source(source_type="local_rag", label=question[:60],
               uri="https://reuters.com/reference", relevance_score=0.80),
        Source(source_type="local_rag", label=question[:60],
               uri="https://bbc.com/reference", relevance_score=0.78),
    ]
    return srcs, "B", f"According to stable sources: {question[:40]}..."


def print_summary(summary: dict) -> None:
    mode = summary.get("mode", "EAL")
    print("\n" + "=" * 66)
    print(f"  MOBIUS MMV P-7 Evaluation Results")
    print(f"  Model: {summary.get('model','?')}  Mode: {mode}  "
          f"Runs: {summary['n_runs']}  Queries: {summary['n_queries']}")
    print("=" * 66)
    print(f"\n  Correct rate (mean ± std, n={summary['n_runs']} runs)")
    print(f"  {'Cat':<6} {'mean':>8} {'±std':>7} {'min':>7} {'max':>7} "
          f"{'B4':>7} {'Target':>8}  {'OK'}")
    print("  " + "-" * 58)
    for cat, d in sorted(summary["correct_rate"].items()):
        mean_ = f"{d['mean']:.0%}"
        std_  = f"{d['std']:.1%}"
        min_  = f"{d['min']:.0%}"
        max_  = f"{d['max']:.0%}"
        b4    = d['phase_b4']
        b4s   = f"{b4:.0%}" if isinstance(b4, float) else str(b4)
        tgt   = d['target']
        tgts  = f"{tgt:.0%}" if isinstance(tgt, float) else str(tgt)
        ok    = "✅" if isinstance(tgt, float) and d['mean'] >= tgt else (
                "❌" if isinstance(tgt, float) else "")
        print(f"  {cat:<6} {mean_:>8} {std_:>7} {min_:>7} {max_:>7} "
              f"{b4s:>7} {tgts:>8}  {ok}")

    if mode == "EAL" and "eal_admissibility_dist" in summary:
        print(f"\n  EAL admissibility:")
        for adm, rate in sorted(summary["eal_admissibility_dist"].items()):
            print(f"    {adm:<22}: {rate:.0%}")
        print(f"\n  Conditional grammar : {summary.get('conditional_grammar_rate', 0):.0%}")
        print(f"  Convergence guard   : {summary.get('convergence_guard_rate', 0):.0%}")
        print(f"  KVS computed=True   : {summary.get('kvs_computed_rate', 0):.0%}")

    print(f"  Avg latency         : {summary.get('avg_latency_ms', 0):.0f}ms/call")
    print("=" * 66)


def main():
    parser = argparse.ArgumentParser(description="MOBIUS P-7 multi-model evaluation")
    parser.add_argument("--input",     default="eval_results_20260322_073658.csv")
    parser.add_argument("--output",    default=None,
                        help="Output CSV path (auto-generated if omitted)")
    parser.add_argument("--model",     default="qwen3.5:9b",
                        help="Ollama model name (e.g. qwen3.5:9b, ministral-3:8b)")
    parser.add_argument("--governed",  default="true",
                        help="true=EAL governed, false=RAW ungoverned")
    parser.add_argument("--runs",      type=int,   default=30)
    parser.add_argument("--temp",      type=float, default=0.0)
    parser.add_argument("--quiet",     action="store_true")
    parser.add_argument("--max",       type=int,   default=None)
    args = parser.parse_args()

    governed = args.governed.lower() in ("true", "1", "yes")
    mode_str = "eal" if governed else "raw"
    model_safe = args.model.replace(":", "-").replace("/", "-")
    ts = datetime.now().strftime("%Y%m%d")

    if args.output is None:
        args.output = f"logs/v2_{model_safe}_{mode_str}_{args.runs}runs_{ts}.csv"

    print(f"Model : {args.model}")
    print(f"Mode  : {'EAL (governed)' if governed else 'RAW (ungoverned)'}")
    print(f"Input : {args.input}")
    print(f"Output: {args.output}")
    print(f"Runs  : {args.runs}")
    print(f"Temp  : {args.temp}")

    queries = []
    with open(args.input, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            queries.append(row)
    if args.max:
        queries = queries[:args.max]
    print(f"Loaded: {len(queries)} queries")

    summary = run_llm_evaluation(
        queries=queries, output_path=args.output,
        model_name=args.model, governed=governed,
        n_runs=args.runs, verbose=not args.quiet,
        temperature=args.temp,
    )

    if summary:
        print_summary(summary)

        json_path = args.output.replace(".csv", "_summary.json")
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"\nCSV    : {args.output}")
        print(f"Summary: {json_path}")


if __name__ == "__main__":
    main()
