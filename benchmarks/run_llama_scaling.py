#!/usr/bin/env python3
"""
Run 3 Llama family models for QK benchmark v2.
  llama3.2:1b / llama3.2:3b / llama3.1:8b

Purpose: Llama intra-family scaling data (1B → 3B → 8B).
720 inferences total (60 queries × 4 conditions × 3 models).
Uses 2-worker parallel execution across GPU0 (port 11434) and GPU1 (port 11435).

NOTE: Llama models do NOT have thinking mode.
      Uses custom call function WITHOUT "think" parameter.

Author : Taiko Toeda / MOBIUS LLC
"""
import json, time, sys, threading, requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).parent.parent))
from benchmarks.qk_benchmark_v2 import (
    QUERIES, CONDITIONS, build_no_qk, build_fixed_qk,
    build_ism_qk, build_pass2,
)

MODELS = [
    {"name": "llama3.2-1b",  "model_id": "llama3.2:1b"},
    {"name": "llama3.2-3b",  "model_id": "llama3.2:3b"},
    {"name": "llama3.1-8b",  "model_id": "llama3.1:8b"},
]

ENDPOINTS = ["http://localhost:11434", "http://localhost:11435"]

_print_lock = threading.Lock()

def _log(msg):
    with _print_lock:
        print(msg, flush=True)


def call_ollama_llama(prompt, model, endpoint="http://localhost:11434", max_tokens=512, timeout=120):
    """Call Ollama WITHOUT think parameter (Llama has no thinking mode)."""
    t0 = time.time()
    try:
        r = requests.post(f"{endpoint}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.2, "num_predict": max_tokens}},
            timeout=timeout)
        r.raise_for_status()
        return {"text": r.json().get("response", ""),
                "latency_ms": int((time.time() - t0) * 1000), "error": None}
    except Exception as e:
        return {"text": "", "latency_ms": int((time.time() - t0) * 1000),
                "error": str(e)}


def run_query_batch(endpoint, model_name, model_id, query_condition_pairs, total):
    """Run a batch of (query, condition, index) tuples on one endpoint."""
    results = []
    for q, cond, idx in query_condition_pairs:
        prompt = {
            "baseline": build_no_qk,
            "fixed_qk_all": build_fixed_qk,
            "ism_adaptive": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
            "full_pipeline": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
        }[cond](q["q"])

        r1 = call_ollama_llama(prompt, model_id, endpoint)
        p1, p1l = r1["text"], r1["latency_ms"]
        p2, p2l = "", 0

        if cond == "full_pipeline" and not r1["error"]:
            p2p = build_pass2(p1, q["q"])
            r2 = call_ollama_llama(p2p, model_id, endpoint, max_tokens=256)
            p2, p2l = r2["text"], r2["latency_ms"]

        final = p2 if p2 else p1
        status = "ERR" if r1.get("error") else "OK"
        _log(f"  [{model_name}:{idx}/{total}] {cond}/{q['id']} ({p1l + p2l}ms) {status}")

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


def run_model_parallel(model_name, model_id):
    """Run all conditions for one model using 2 workers."""
    all_pairs = [(q, cond) for cond in CONDITIONS for q in QUERIES]
    total = len(all_pairs)

    even_pairs = [(q, c, i + 1) for i, (q, c) in enumerate(all_pairs) if i % 2 == 0]
    odd_pairs = [(q, c, i + 1) for i, (q, c) in enumerate(all_pairs) if i % 2 == 1]

    with ThreadPoolExecutor(max_workers=2) as ex:
        f0 = ex.submit(run_query_batch, ENDPOINTS[0], model_name, model_id, even_pairs, total)
        f1 = ex.submit(run_query_batch, ENDPOINTS[1], model_name, model_id, odd_pairs, total)
        results = f0.result() + f1.result()

    return results


def main():
    t0 = time.time()
    all_results = []

    for model in MODELS:
        name = model["name"]
        model_id = model["model_id"]

        print(f"\n=== {name} (2-worker parallel) ===")
        for ep in ENDPOINTS:
            print(f"  Warming {name} on {ep}...")
            call_ollama_llama("warmup", model_id, ep, max_tokens=1)
        time.sleep(5)

        results = run_model_parallel(name, model_id)
        all_results.extend(results)

        ok = sum(1 for r in results if not r["error"])
        err = sum(1 for r in results if r["error"])
        print(f"  {name} done: {ok} OK, {err} ERR")

    elapsed = time.time() - t0
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"qk_benchmark_v2_llama_scaling_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n=== Done in {elapsed:.0f}s | {len(all_results)} inferences → {out} ===")


if __name__ == "__main__":
    main()
