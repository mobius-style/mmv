#!/usr/bin/env python3
"""
Run qwen3 (RL reasoning) benchmark — Phase B.
  qwen3:4b / qwen3:8b with think:false.
  480 inferences (60 queries × 4 conditions × 2 models).
  2-worker parallel execution.

Purpose: Test whether RL-trained thinking models show QK interference
that SFT thinking models (qwen3.5) do not.

CRITICAL: think:false on all calls — matching all previous benchmarks.
We test whether RL reasoning patterns persist DESPITE think:false.

Author : Taiko Toeda / MOBIUS LLC
"""
import json, time, sys, threading, requests, subprocess, copy
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from benchmarks.qk_benchmark_v2 import (
    QUERIES, CONDITIONS, build_no_qk, build_fixed_qk,
    build_ism_qk, build_pass2,
)

MODELS = [
    {"name": "qwen3-4b", "model_id": "qwen3:4b",
     "options": {"num_ctx": 4096, "num_predict": 512}},
    {"name": "qwen3-8b", "model_id": "qwen3:8b",
     "options": {"num_ctx": 4096, "num_predict": 512}},
]

ENDPOINTS = ["http://localhost:11434", "http://localhost:11435"]

_print_lock = threading.Lock()

def _log(msg):
    with _print_lock:
        print(msg, flush=True)


def call_ollama(prompt, model, endpoint="http://localhost:11434",
                max_tokens=512, timeout=180, model_options=None):
    """Call Ollama WITH think:false — suppress RL thinking output."""
    t0 = time.time()
    opts = {"temperature": 0.2, "num_predict": max_tokens}
    if model_options:
        opts.update(model_options)
    try:
        r = requests.post(f"{endpoint}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "think": False, "options": opts},
            timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return {"text": data.get("response", ""),
                "latency_ms": int((time.time() - t0) * 1000),
                "error": None}
    except Exception as e:
        return {"text": "", "latency_ms": int((time.time() - t0) * 1000),
                "error": str(e)}


def run_query_batch(endpoint, model_name, model_id, query_condition_pairs,
                    total, model_options=None):
    """Run a batch of (query, condition, index) tuples on one endpoint."""
    results = []
    for q, cond, idx in query_condition_pairs:
        prompt = {
            "baseline": build_no_qk,
            "fixed_qk_all": build_fixed_qk,
            "ism_adaptive": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
            "full_pipeline": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
        }[cond](q["q"])

        r1 = call_ollama(prompt, model_id, endpoint,
                         model_options=model_options)
        p1, p1l = r1["text"], r1["latency_ms"]
        p2, p2l = "", 0

        if cond == "full_pipeline" and not r1["error"]:
            p2p = build_pass2(p1, q["q"])
            r2 = call_ollama(p2p, model_id, endpoint, max_tokens=256,
                             model_options=model_options)
            p2, p2l = r2["text"], r2["latency_ms"]

        final = p2 if p2 else p1
        status = "ERR" if r1.get("error") else "OK"
        _log(f"  [{model_name}:{idx}/{total}] {cond}/{q['id']} "
             f"({p1l + p2l}ms) {status}")

        results.append({
            "query_id": q["id"], "query": q["q"], "category": q["category"],
            "subtype": q["subtype"], "intent": q["intent"],
            "answer": q["answer"], "common_error": q.get("common_error", ""),
            "trap": q.get("trap", ""),
            "model": model_name, "condition": cond,
            "response": final, "pass1_text": p1, "pass2_text": p2,
            "pass1_latency_ms": p1l, "pass2_latency_ms": p2l,
            "total_latency_ms": p1l + p2l, "error": r1.get("error"),
        })
    return results


def run_model_parallel(model_name, model_id, model_options=None):
    """Run all conditions for one model using 2 workers."""
    all_pairs = [(q, cond) for cond in CONDITIONS for q in QUERIES]
    total = len(all_pairs)

    even_pairs = [(q, c, i + 1) for i, (q, c) in enumerate(all_pairs) if i % 2 == 0]
    odd_pairs = [(q, c, i + 1) for i, (q, c) in enumerate(all_pairs) if i % 2 == 1]

    with ThreadPoolExecutor(max_workers=2) as ex:
        f0 = ex.submit(run_query_batch, ENDPOINTS[0], model_name, model_id,
                        even_pairs, total, model_options)
        f1 = ex.submit(run_query_batch, ENDPOINTS[1], model_name, model_id,
                        odd_pairs, total, model_options)
        results = f0.result() + f1.result()

    return results


def run_model_sequential(model_name, model_id, model_options=None):
    """Fallback: run sequentially on port 11434 only."""
    all_pairs = [(q, cond) for cond in CONDITIONS for q in QUERIES]
    total = len(all_pairs)
    indexed = [(q, c, i + 1) for i, (q, c) in enumerate(all_pairs)]
    return run_query_batch(ENDPOINTS[0], model_name, model_id,
                           indexed, total, model_options)


def print_comparison(new_results, out_path):
    """Compare qwen3 (RL) with qwen3.5 (SFT) and DeepSeek R1."""
    merged_path = Path("benchmarks/results/qk_benchmark_v2_merged.json")
    if not merged_path.exists():
        print("\n  [WARN] No merged.json found for comparison")
        return

    with open(merged_path) as f:
        merged = json.load(f)

    from benchmarks.qk_evaluate_v2 import classify_all, compute_metrics

    classify_all(new_results)
    new_metrics = compute_metrics(new_results)

    # Get comparison models from merged data
    compare_models = {
        "qwen3.5-4b", "qwen3.5-9b",
        "deepseek-r1-7b", "deepseek-r1-8b",
    }
    compare_data = [r for r in merged if r["model"] in compare_models]
    classify_all(compare_data)
    compare_metrics = compute_metrics(compare_data)

    # Merge metrics
    all_metrics = {**compare_metrics, **new_metrics}

    conds = ["baseline", "fixed_qk_all", "ism_adaptive", "full_pipeline"]

    print("\n" + "=" * 90)
    print("PHASE B: qwen3 (RL) vs qwen3.5 (SFT) vs DeepSeek R1 (RL)")
    print("All models: think:false")
    print("=" * 90)

    # Family comparison table
    groups = [
        ("~4B Dense", [
            ("qwen3.5-4b", "SFT"),
            ("qwen3-4b", "RL"),
        ]),
        ("~8B Dense", [
            ("qwen3.5-9b", "SFT"),
            ("qwen3-8b", "RL"),
            ("deepseek-r1-7b", "RL"),
            ("deepseek-r1-8b", "RL"),
        ]),
    ]

    print(f"\n{'Model':<18} {'Train':>5} {'Condition':<16} {'IA%':>5} {'Ctrl Deg':>9} {'Notes':>10}")
    print("-" * 68)

    for group_name, models in groups:
        print(f"\n  --- {group_name} ---")
        for model_name, training in models:
            for c in conds:
                m = all_metrics.get((model_name, c))
                if m is None:
                    continue
                ia_pct = m["ia_rate"] * 100
                deg_pct = m["deg_rate"] * 100
                note = ""
                if c == "ism_adaptive":
                    base_m = all_metrics.get((model_name, "baseline"))
                    if base_m:
                        delta = (m["ia_rate"] - base_m["ia_rate"]) * 100
                        note = f"({delta:+.0f}%)"
                print(f"  {model_name:<16} {training:>5} {c:<16} {ia_pct:>4.0f}% {deg_pct:>8.0f}% {note:>10}")
        print()

    # Summary
    print("=" * 90)
    print("HYPOTHESIS TEST: Does RL training cause QK interference?")
    print("=" * 90)
    for group_name, models in groups:
        print(f"\n  {group_name}:")
        for model_name, training in models:
            base = all_metrics.get((model_name, "baseline"), {}).get("ia_rate", 0)
            ism = all_metrics.get((model_name, "ism_adaptive"), {}).get("ia_rate", 0)
            delta = (ism - base) * 100
            direction = "IMPROVES" if delta < -2 else ("WORSENS" if delta > 2 else "NEUTRAL")
            print(f"    {model_name:<16} {training}: baseline {base*100:.0f}% → ISM {ism*100:.0f}% "
                  f"(delta {delta:+.0f}%) → {direction}")


def main():
    t0 = time.time()
    all_results = []

    for model in MODELS:
        name = model["name"]
        model_id = model["model_id"]
        opts = model.get("options", {})

        print(f"\n=== {name} (2-worker parallel, think:false) ===")
        print(f"  options: {opts}")
        for ep in ENDPOINTS:
            print(f"  Warming {name} on {ep}...")
            call_ollama("warmup", model_id, ep, max_tokens=1,
                        model_options=opts)
        time.sleep(5)

        try:
            results = run_model_parallel(name, model_id, opts)
            err_count = sum(1 for r in results if r["error"])
            if "8b" in model_id and err_count > len(results) * 0.3:
                raise RuntimeError(f"Too many errors ({err_count}), likely OOM")
        except Exception as e:
            if "8b" not in model_id:
                raise
            print(f"\n  *** 8B 2-worker failed: {e}")
            print(f"  *** Falling back to single-worker sequential on 11434 ***")
            subprocess.run(["pkill", "-f", "ollama serve"],
                           capture_output=True)
            time.sleep(3)
            subprocess.run(["systemctl", "--user", "start", "ollama"],
                           capture_output=True)
            time.sleep(5)
            print(f"  Warming {name} on single worker...")
            call_ollama("warmup", model_id, ENDPOINTS[0],
                        max_tokens=1, model_options=opts)
            time.sleep(5)
            results = run_model_sequential(name, model_id, opts)

        all_results.extend(results)

        ok = sum(1 for r in results if not r["error"])
        err = sum(1 for r in results if r["error"])
        empty = sum(1 for r in results if len(r["response"].strip()) == 0)
        print(f"  {name} done: {ok} OK, {err} ERR, {empty} empty responses")

    elapsed = time.time() - t0
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"qk_benchmark_v2_qwen3_rl_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n=== Done in {elapsed:.0f}s | {len(all_results)} inferences → {out} ===")

    print_comparison(all_results, out)


if __name__ == "__main__":
    main()
