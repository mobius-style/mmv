#!/usr/bin/env python3
"""
Run 4 DeepSeek R1 models for QK benchmark v2.
  Phase A: deepseek-r1:1.5b / deepseek-r1:7b / deepseek-r1:8b (2-worker parallel)
  Phase B: deepseek-r1:14b (single worker, needs full VRAM)

Purpose: Reasoning-model family scaling (1.5B → 7B → 8B → 14B).
960 inferences total (60 queries × 4 conditions × 4 models).

NOTE: DeepSeek R1 has thinking mode.
      "think": false is added to ALL Ollama calls to suppress
      thinking tokens from leaking into responses.

Author : Taiko Toeda / MOBIUS LLC
"""
import json, time, sys, threading, requests, subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).parent.parent))
from benchmarks.qk_benchmark_v2 import (
    QUERIES, CONDITIONS, build_no_qk, build_fixed_qk,
    build_ism_qk, build_pass2,
)

MODELS_PHASE_A = [
    {"name": "deepseek-r1-1.5b", "model_id": "deepseek-r1:1.5b"},
    {"name": "deepseek-r1-7b",   "model_id": "deepseek-r1:7b"},
    {"name": "deepseek-r1-8b",   "model_id": "deepseek-r1:8b"},
]

MODEL_PHASE_B = {"name": "deepseek-r1-14b", "model_id": "deepseek-r1:14b"}

ENDPOINTS = ["http://localhost:11434", "http://localhost:11435"]

_print_lock = threading.Lock()

def _log(msg):
    with _print_lock:
        print(msg, flush=True)


def call_ollama_r1(prompt, model, endpoint="http://localhost:11434", max_tokens=512, timeout=120):
    """Call Ollama WITH think:false (DeepSeek R1 has thinking mode)."""
    t0 = time.time()
    try:
        r = requests.post(f"{endpoint}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "think": False,
                  "options": {"temperature": 0.2, "num_predict": max_tokens}},
            timeout=timeout)
        r.raise_for_status()
        return {"text": r.json().get("response", ""),
                "latency_ms": int((time.time() - t0) * 1000), "error": None}
    except Exception as e:
        return {"text": "", "latency_ms": int((time.time() - t0) * 1000),
                "error": str(e)}


def run_query_batch(endpoint, model_name, model_id, query_condition_pairs, total, timeout=120):
    """Run a batch of (query, condition, index) tuples on one endpoint."""
    results = []
    for q, cond, idx in query_condition_pairs:
        prompt = {
            "baseline": build_no_qk,
            "fixed_qk_all": build_fixed_qk,
            "ism_adaptive": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
            "full_pipeline": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
        }[cond](q["q"])

        r1 = call_ollama_r1(prompt, model_id, endpoint, timeout=timeout)
        p1, p1l = r1["text"], r1["latency_ms"]
        p2, p2l = "", 0

        if cond == "full_pipeline" and not r1["error"]:
            p2p = build_pass2(p1, q["q"])
            r2 = call_ollama_r1(p2p, model_id, endpoint, max_tokens=256, timeout=timeout)
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


def run_model_single(model_name, model_id, timeout=180):
    """Run all conditions for one model on single port (for large models)."""
    endpoint = ENDPOINTS[0]
    all_pairs = [(q, cond) for cond in CONDITIONS for q in QUERIES]
    total = len(all_pairs)
    indexed = [(q, c, i + 1) for i, (q, c) in enumerate(all_pairs)]
    return run_query_batch(endpoint, model_name, model_id, indexed, total, timeout=timeout)


def switch_to_single_worker():
    """Stop 2-worker Ollama, start default single instance."""
    print("\n=== Switching to single-worker Ollama for Phase B ===")
    subprocess.run(
        "ps aux | grep 'ollama serve' | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null",
        shell=True)
    time.sleep(3)
    subprocess.run(["sudo", "systemctl", "start", "ollama"])
    time.sleep(10)
    # Verify
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=10)
        print(f"  Single-worker Ollama: OK ({len(r.json().get('models',[]))} models)")
    except Exception as e:
        print(f"  WARNING: Ollama check failed: {e}")


def restore_two_workers():
    """Restore 2-worker Ollama after Phase B."""
    print("\n=== Restoring 2-worker Ollama ===")
    subprocess.run(["sudo", "systemctl", "stop", "ollama"])
    time.sleep(3)
    subprocess.run(["bash", str(Path.home() / "setup-ollama-2workers.sh")])
    time.sleep(5)


def main():
    t0 = time.time()
    all_results = []

    # ── Phase A: 1.5b, 7b, 8b (2-worker parallel) ──
    print("=" * 60)
    print("PHASE A: deepseek-r1 1.5b / 7b / 8b (2-worker parallel)")
    print("=" * 60)

    for model in MODELS_PHASE_A:
        name = model["name"]
        model_id = model["model_id"]

        print(f"\n=== {name} (2-worker parallel) ===")
        for ep in ENDPOINTS:
            print(f"  Warming {name} on {ep}...")
            call_ollama_r1("warmup", model_id, ep, max_tokens=1)
        time.sleep(5)

        results = run_model_parallel(name, model_id)
        all_results.extend(results)

        ok = sum(1 for r in results if not r["error"])
        err = sum(1 for r in results if r["error"])
        print(f"  {name} done: {ok} OK, {err} ERR")

    phase_a_time = time.time() - t0
    print(f"\n  Phase A complete: {len(all_results)} inferences in {phase_a_time:.0f}s")

    # ── Phase B: 14b (single worker) ──
    print("\n" + "=" * 60)
    print("PHASE B: deepseek-r1-14b (single worker)")
    print("=" * 60)

    switch_to_single_worker()

    name = MODEL_PHASE_B["name"]
    model_id = MODEL_PHASE_B["model_id"]

    print(f"\n=== {name} (single worker) ===")
    print(f"  Warming {name} on {ENDPOINTS[0]}...")
    call_ollama_r1("warmup", model_id, ENDPOINTS[0], max_tokens=1, timeout=180)
    time.sleep(5)

    results = run_model_single(name, model_id, timeout=180)
    all_results.extend(results)

    ok = sum(1 for r in results if not r["error"])
    err = sum(1 for r in results if r["error"])
    print(f"  {name} done: {ok} OK, {err} ERR")

    # Restore 2-worker
    restore_two_workers()

    # ── Save results ──
    elapsed = time.time() - t0
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"qk_benchmark_v2_deepseek_scaling_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n=== Done in {elapsed:.0f}s | {len(all_results)} inferences → {out} ===")


if __name__ == "__main__":
    main()
