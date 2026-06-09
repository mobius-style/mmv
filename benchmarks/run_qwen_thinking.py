#!/usr/bin/env python3
"""
Run qwen3.5 thinking-mode benchmark comparison.
  qwen3.5:2b / qwen3.5:4b / qwen3.5:9b with think:true (default).
  720 inferences (60 queries × 4 conditions × 3 models).
  2-worker parallel execution.

Purpose: Compare QK effectiveness with thinking mode ON vs OFF.
Existing data uses think:false; this run uses think:true.

CRITICAL: No "think": false in any Ollama call.
  Ollama API returns thinking in separate 'thinking' field.
  Response field is clean. Safety strip applied anyway.

Author : Taiko Toeda / MOBIUS LLC
"""
import json, re, time, sys, threading, requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).parent.parent))
from benchmarks.qk_benchmark_v2 import (
    QUERIES, CONDITIONS, build_no_qk, build_fixed_qk,
    build_ism_qk, build_pass2,
)

MODELS = [
    {"name": "qwen3.5-2b-thinking", "model_id": "qwen3.5:2b",
     "options": {"num_ctx": 4096, "num_predict": 2048}},
    {"name": "qwen3.5-4b-thinking", "model_id": "qwen3.5:4b",
     "options": {"num_ctx": 4096, "num_predict": 2048}},
    {"name": "qwen3.5-9b-thinking", "model_id": "qwen3.5:9b",
     "options": {"num_ctx": 3072, "num_predict": 1536}},
]

ENDPOINTS = ["http://localhost:11434", "http://localhost:11435"]

_print_lock = threading.Lock()

def _log(msg):
    with _print_lock:
        print(msg, flush=True)


def strip_thinking(text):
    """Remove <think>...</think> blocks from response (safety strip)."""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


def call_ollama_thinking(prompt, model, endpoint="http://localhost:11434",
                         max_tokens=1024, timeout=180, model_options=None):
    """Call Ollama WITHOUT think:false — let thinking mode run."""
    t0 = time.time()
    opts = {"temperature": 0.2, "num_predict": max_tokens}
    if model_options:
        opts.update(model_options)
    try:
        r = requests.post(f"{endpoint}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": opts},
            timeout=timeout)
        r.raise_for_status()
        data = r.json()
        # Response field should be clean; thinking is in separate field.
        # Apply safety strip anyway.
        text = strip_thinking(data.get("response", ""))
        thinking_len = len(data.get("thinking", "") or "")
        return {"text": text, "latency_ms": int((time.time() - t0) * 1000),
                "error": None, "thinking_len": thinking_len}
    except Exception as e:
        return {"text": "", "latency_ms": int((time.time() - t0) * 1000),
                "error": str(e), "thinking_len": 0}


def run_query_batch(endpoint, model_name, model_id, query_condition_pairs, total,
                    model_options=None):
    """Run a batch of (query, condition, index) tuples on one endpoint."""
    results = []
    for q, cond, idx in query_condition_pairs:
        prompt = {
            "baseline": build_no_qk,
            "fixed_qk_all": build_fixed_qk,
            "ism_adaptive": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
            "full_pipeline": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
        }[cond](q["q"])

        r1 = call_ollama_thinking(prompt, model_id, endpoint,
                                  model_options=model_options)
        p1, p1l = r1["text"], r1["latency_ms"]
        p2, p2l = "", 0
        think_total = r1["thinking_len"]

        if cond == "full_pipeline" and not r1["error"]:
            p2p = build_pass2(p1, q["q"])
            r2 = call_ollama_thinking(p2p, model_id, endpoint, max_tokens=512,
                                      model_options=model_options)
            p2, p2l = r2["text"], r2["latency_ms"]
            think_total += r2["thinking_len"]

        final = p2 if p2 else p1
        status = "ERR" if r1.get("error") else "OK"
        think_info = f" T={r1['thinking_len']}ch" if r1["thinking_len"] else ""
        _log(f"  [{model_name}:{idx}/{total}] {cond}/{q['id']} "
             f"({p1l + p2l}ms){think_info} {status}")

        results.append({
            "query_id": q["id"], "query": q["q"], "category": q["category"],
            "subtype": q["subtype"], "intent": q["intent"],
            "answer": q["answer"], "common_error": q.get("common_error", ""),
            "trap": q.get("trap", ""),
            "model": model_name, "condition": cond,
            "response": final, "pass1_text": p1, "pass2_text": p2,
            "pass1_latency_ms": p1l, "pass2_latency_ms": p2l,
            "total_latency_ms": p1l + p2l, "error": r1.get("error"),
            "thinking_len": think_total,
            "raw_response_len": len(r1.get("text", "")),
            "clean_response_len": len(final),
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


def print_comparison(thinking_results, thinking_path):
    """Compare think:true results with existing think:false merged data."""
    merged_path = Path("benchmarks/results/qk_benchmark_v2_merged.json")
    if not merged_path.exists():
        print("\n  [WARN] No merged.json found for comparison")
        return

    with open(merged_path) as f:
        merged = json.load(f)

    # Import evaluator
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from benchmarks.qk_evaluate_v2 import classify_all, compute_metrics

    # Classify thinking results
    classify_all(thinking_results)
    think_metrics = compute_metrics(thinking_results)

    # Get think:false data for qwen3.5 models only
    model_map = {
        "qwen3.5-2b-thinking": "qwen3.5-2b",
        "qwen3.5-4b-thinking": "qwen3.5-4b",
        "qwen3.5-9b-thinking": "qwen3.5-9b",
    }
    noethink_data = [r for r in merged if r["model"] in model_map.values()]
    classify_all(noethink_data)
    nothink_metrics = compute_metrics(noethink_data)

    conds = ["baseline", "fixed_qk_all", "ism_adaptive", "full_pipeline"]

    print("\n" + "=" * 80)
    print("COMPARISON: think:false vs think:true")
    print("=" * 80)
    print(f"\n{'Model':<22} {'Condition':<16} {'think:false IA%':>16} {'think:true IA%':>15} {'Delta':>7}")
    print("-" * 80)
    for think_name, nothink_name in model_map.items():
        for c in conds:
            nothink_ia = nothink_metrics.get((nothink_name, c), {}).get("ia_rate", 0)
            think_ia = think_metrics.get((think_name, c), {}).get("ia_rate", 0)
            delta = think_ia - nothink_ia
            short_name = nothink_name
            print(f"  {short_name:<20} {c:<16} {nothink_ia*100:>13.0f}% {think_ia*100:>12.0f}% {delta*100:>+6.0f}%")
        print()

    # Average thinking trace length per model/condition
    from collections import defaultdict
    think_lens = defaultdict(list)
    for r in thinking_results:
        think_lens[(r["model"], r["condition"])].append(r.get("thinking_len", 0))

    print(f"\n{'Model':<22} {'Condition':<16} {'Avg Think Len (ch)':>20}")
    print("-" * 60)
    for think_name in model_map:
        for c in conds:
            lens = think_lens.get((think_name, c), [0])
            avg = sum(lens) / max(len(lens), 1)
            print(f"  {think_name:<20} {c:<16} {avg:>17.0f}")
        print()


def run_model_sequential_single(model_name, model_id, model_options=None):
    """Fallback: run all conditions sequentially on port 11434 only."""
    all_pairs = [(q, cond) for cond in CONDITIONS for q in QUERIES]
    total = len(all_pairs)
    indexed = [(q, c, i + 1) for i, (q, c) in enumerate(all_pairs)]
    return run_query_batch(ENDPOINTS[0], model_name, model_id,
                           indexed, total, model_options)


def main():
    import subprocess

    t0 = time.time()
    all_results = []

    for model in MODELS:
        name = model["name"]
        model_id = model["model_id"]
        opts = model.get("options", {})

        print(f"\n=== {name} (2-worker parallel, think:true) ===")
        print(f"  options: {opts}")
        for ep in ENDPOINTS:
            print(f"  Warming {name} on {ep}...")
            call_ollama_thinking("warmup", model_id, ep, max_tokens=1,
                                 model_options=opts)
        time.sleep(5)

        try:
            results = run_model_parallel(name, model_id, opts)
            err_count = sum(1 for r in results if r["error"])
            # If too many errors on 9B, fall back to sequential
            if "9b" in model_id and err_count > len(results) * 0.3:
                raise RuntimeError(f"Too many errors ({err_count}), likely OOM")
        except Exception as e:
            if "9b" not in model_id:
                raise
            print(f"\n  *** 9B 2-worker failed: {e}")
            print(f"  *** Falling back to single-worker sequential on 11434 ***")
            # Kill 2-worker and restart default systemd Ollama
            subprocess.run(["pkill", "-f", "ollama serve"],
                           capture_output=True)
            time.sleep(3)
            subprocess.run(["systemctl", "--user", "start", "ollama"],
                           capture_output=True)
            time.sleep(5)
            # Retry with larger budget on single GPU (dual-GPU layer split)
            fallback_opts = {"num_ctx": 4096, "num_predict": 2048}
            print(f"  Warming {name} on single worker...")
            call_ollama_thinking("warmup", model_id, ENDPOINTS[0],
                                 max_tokens=1, model_options=fallback_opts)
            time.sleep(5)
            results = run_model_sequential_single(name, model_id, fallback_opts)

        all_results.extend(results)

        ok = sum(1 for r in results if not r["error"])
        err = sum(1 for r in results if r["error"])
        avg_think = sum(r.get("thinking_len", 0) for r in results) / max(len(results), 1)
        print(f"  {name} done: {ok} OK, {err} ERR, avg_thinking={avg_think:.0f}ch")

    elapsed = time.time() - t0
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"qk_benchmark_v2_qwen_thinking_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n=== Done in {elapsed:.0f}s | {len(all_results)} inferences → {out} ===")

    # Print comparison with existing think:false data
    print_comparison(all_results, out)


if __name__ == "__main__":
    main()
