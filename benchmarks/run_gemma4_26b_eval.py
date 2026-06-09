#!/usr/bin/env python3
"""
Run gemma4:26b for QK benchmark v2.
  Single model, single worker (GPU0 only, CPU offload ~10.5GB).
  240 inferences (60 queries × 4 conditions).

Purpose: MMV proof-of-concept evaluation with gemma4:26b (26B).
Compare with qwen3.5:9b (production) and all other benchmarked models.

NOTE: gemma4:26b requires think:false — without it, response is empty.
      14 tok/s expected due to CPU offload.

Author : Taiko Toeda / MOBIUS LLC
"""
import json, time, sys, requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from benchmarks.qk_benchmark_v2 import (
    QUERIES, CONDITIONS, build_no_qk, build_fixed_qk,
    build_ism_qk, build_pass2,
)

MODEL_NAME = "gemma4-26b"
MODEL_ID   = "gemma4:26b"
ENDPOINT   = "http://localhost:11434"


def call_ollama_gemma(prompt, model=MODEL_ID, endpoint=ENDPOINT,
                      max_tokens=512, timeout=180):
    """Call Ollama WITH think:false (gemma4 requires it)."""
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


def run_model(queries):
    results = []
    total = len(queries) * len(CONDITIONS)
    count = 0

    for cond in CONDITIONS:
        for q in queries:
            count += 1
            prompt = {
                "baseline": build_no_qk,
                "fixed_qk_all": build_fixed_qk,
                "ism_adaptive": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
                "full_pipeline": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
            }[cond](q["q"])

            r1 = call_ollama_gemma(prompt)
            p1, p1l = r1["text"], r1["latency_ms"]
            p2, p2l = "", 0

            # Condition D: Pass2 on same endpoint (single worker)
            if cond == "full_pipeline" and not r1["error"]:
                p2p = build_pass2(p1, q["q"])
                r2 = call_ollama_gemma(p2p, max_tokens=256)
                p2, p2l = r2["text"], r2["latency_ms"]

            final = p2 if p2 else p1
            status = "ERR" if r1.get("error") else "OK"
            print(f"  [{MODEL_NAME}:{count}/{total}] {cond}/{q['id']} "
                  f"({p1l + p2l}ms) {status}", flush=True)

            results.append({
                "query_id": q["id"], "query": q["q"], "category": q["category"],
                "subtype": q["subtype"], "intent": q["intent"],
                "answer": q["answer"], "common_error": q.get("common_error", ""),
                "trap": q.get("trap", ""),
                "model": MODEL_NAME, "condition": cond,
                "response": final, "pass1_text": p1, "pass2_text": p2,
                "pass1_latency_ms": p1l, "pass2_latency_ms": p2l,
                "total_latency_ms": p1l + p2l, "error": r1.get("error"),
            })
    return results


def main():
    t0 = time.time()

    print(f"=== gemma4:26b QK Benchmark v2 (single worker, GPU0) ===")
    print(f"  {len(QUERIES)} queries × {len(CONDITIONS)} conditions = "
          f"{len(QUERIES) * len(CONDITIONS)} inferences")
    print(f"  Model: {MODEL_ID} @ {ENDPOINT}")
    print(f"  Expected: ~14 tok/s (CPU offload)")
    print()

    # Pre-warm
    print(f"  Warming {MODEL_ID}...")
    call_ollama_gemma("warmup", max_tokens=1)
    time.sleep(5)

    results = run_model(QUERIES)

    ok = sum(1 for r in results if not r["error"])
    err = sum(1 for r in results if r["error"])
    print(f"\n  {MODEL_NAME} done: {ok} OK, {err} ERR")

    elapsed = time.time() - t0
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"qk_benchmark_v2_gemma4_26b_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n=== Done in {elapsed:.0f}s | {len(results)} inferences → {out} ===")


if __name__ == "__main__":
    main()
