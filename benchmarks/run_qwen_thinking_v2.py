#!/usr/bin/env python3
"""
Run qwen3.5 thinking-mode benchmark v2 (sufficient token budget).
  Phase 1: qwen3.5:2b + qwen3.5:4b — 2-worker parallel
  Phase 2: qwen3.5:9b — single worker (dual-GPU layer split)
  720 inferences total (60 queries × 4 conditions × 3 models).

v1 had num_predict:1024 → 555/720 empty responses.
v2 uses num_ctx:8192 / num_predict:4096 to give thinking room.

CRITICAL: No "think": false in any Ollama call.

Author : Taiko Toeda / MOBIUS LLC
"""
import json, re, time, sys, threading, requests, argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).parent.parent))
from benchmarks.qk_benchmark_v2 import (
    QUERIES, CONDITIONS, build_no_qk, build_fixed_qk,
    build_ism_qk, build_pass2,
)

MODELS_PHASE1 = [
    {"name": "qwen3.5-2b-thinking", "model_id": "qwen3.5:2b"},
    {"name": "qwen3.5-4b-thinking", "model_id": "qwen3.5:4b"},
]
MODELS_PHASE2 = [
    {"name": "qwen3.5-9b-thinking", "model_id": "qwen3.5:9b"},
]

ENDPOINTS = ["http://localhost:11434", "http://localhost:11435"]

NUM_CTX = 8192
NUM_PREDICT = 4096
NUM_PREDICT_PASS2 = 2048

_print_lock = threading.Lock()

def _log(msg):
    with _print_lock:
        print(msg, flush=True)


def strip_thinking(text):
    """Remove <think>...</think> blocks from response (safety strip)."""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


def call_ollama_thinking(prompt, model, endpoint="http://localhost:11434",
                         max_tokens=NUM_PREDICT, timeout=300):
    """Call Ollama WITHOUT think:false — let thinking mode run."""
    t0 = time.time()
    try:
        r = requests.post(f"{endpoint}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.2, "num_ctx": NUM_CTX,
                              "num_predict": max_tokens}},
            timeout=timeout)
        r.raise_for_status()
        data = r.json()
        text = strip_thinking(data.get("response", ""))
        thinking_len = len(data.get("thinking", "") or "")
        return {"text": text, "latency_ms": int((time.time() - t0) * 1000),
                "error": None, "thinking_len": thinking_len}
    except Exception as e:
        return {"text": "", "latency_ms": int((time.time() - t0) * 1000),
                "error": str(e), "thinking_len": 0}


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

        r1 = call_ollama_thinking(prompt, model_id, endpoint)
        p1, p1l = r1["text"], r1["latency_ms"]
        p2, p2l = "", 0

        if cond == "full_pipeline" and not r1["error"]:
            p2p = build_pass2(p1, q["q"])
            r2 = call_ollama_thinking(p2p, model_id, endpoint,
                                      max_tokens=NUM_PREDICT_PASS2)
            p2, p2l = r2["text"], r2["latency_ms"]

        final = p2 if p2 else p1
        status = "ERR" if r1.get("error") else "OK"
        think_info = f" T={r1['thinking_len']}ch" if r1["thinking_len"] else ""
        empty_flag = " [EMPTY]" if not final.strip() else ""
        _log(f"  [{model_name}:{idx}/{total}] {cond}/{q['id']} "
             f"({p1l + p2l}ms){think_info}{empty_flag} {status}")

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


def run_model_single(model_name, model_id):
    """Run all conditions for one model on single port."""
    endpoint = ENDPOINTS[0]
    all_pairs = [(q, cond) for cond in CONDITIONS for q in QUERIES]
    total = len(all_pairs)
    indexed = [(q, c, i + 1) for i, (q, c) in enumerate(all_pairs)]
    return run_query_batch(endpoint, model_name, model_id, indexed, total)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["phase1", "phase2", "all"], default="all")
    args = parser.parse_args()

    t0 = time.time()
    all_results = []

    if args.phase in ("phase1", "all"):
        print("=" * 60)
        print("PHASE 1: qwen3.5 2B + 4B (2-worker parallel, think:true)")
        print(f"  num_ctx={NUM_CTX}, num_predict={NUM_PREDICT}")
        print("=" * 60)

        for model in MODELS_PHASE1:
            name = model["name"]
            model_id = model["model_id"]

            print(f"\n=== {name} (2-worker parallel, think:true) ===")
            for ep in ENDPOINTS:
                print(f"  Warming {name} on {ep}...")
                call_ollama_thinking("warmup", model_id, ep, max_tokens=1)
            time.sleep(5)

            results = run_model_parallel(name, model_id)
            all_results.extend(results)

            ok = sum(1 for r in results if not r["error"])
            err = sum(1 for r in results if r["error"])
            empty = sum(1 for r in results if not r["response"].strip())
            print(f"  {name} done: {ok} OK, {err} ERR, {empty} empty")

    if args.phase in ("phase2", "all"):
        print("\n" + "=" * 60)
        print("PHASE 2: qwen3.5 9B (single worker, think:true)")
        print(f"  num_ctx={NUM_CTX}, num_predict={NUM_PREDICT}")
        print("=" * 60)

        for model in MODELS_PHASE2:
            name = model["name"]
            model_id = model["model_id"]

            print(f"\n=== {name} (single worker, think:true) ===")
            print(f"  Warming {name} on {ENDPOINTS[0]}...")
            call_ollama_thinking("warmup", model_id, ENDPOINTS[0], max_tokens=1)
            time.sleep(5)

            results = run_model_single(name, model_id)
            all_results.extend(results)

            ok = sum(1 for r in results if not r["error"])
            err = sum(1 for r in results if r["error"])
            empty = sum(1 for r in results if not r["response"].strip())
            print(f"  {name} done: {ok} OK, {err} ERR, {empty} empty")

    elapsed = time.time() - t0
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"qk_benchmark_v2_qwen_thinking_v2_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n=== Done in {elapsed:.0f}s | {len(all_results)} inferences → {out} ===")


if __name__ == "__main__":
    main()
