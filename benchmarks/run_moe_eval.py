#!/usr/bin/env python3
"""
Run 2 MoE models for QK benchmark v2.
  Phase A: qwen3:30b-a3b  (30B total, 3B active — MoE)
  Phase B: mixtral:8x7b   (46.7B total, ~13B active — MoE)

Purpose: MoE hypothesis test — does "large knowledge pool +
moderate active compute" make an ideal QK target?
480 inferences total (60 queries × 4 conditions × 2 models).
Single Ollama worker (CPU offload, both models >16GB).

NOTE: qwen3 has thinking mode → think:false required.
      mixtral does NOT → no think parameter.

Author : Taiko Toeda / MOBIUS LLC
"""
import json, time, sys, requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from benchmarks.qk_benchmark_v2 import (
    QUERIES, CONDITIONS, build_no_qk, build_fixed_qk,
    build_ism_qk, build_pass2,
)

ENDPOINT = "http://localhost:11434"

MODELS = [
    {
        "name": "qwen3-30b-a3b",
        "model_id": "qwen3:30b-a3b",
        "think_false": True,
    },
    {
        "name": "mixtral-8x7b",
        "model_id": "mixtral:8x7b",
        "think_false": False,
    },
]


def call_ollama(prompt, model, think_false=True, max_tokens=512, timeout=180):
    """Call Ollama. Adds think:false only when required."""
    t0 = time.time()
    payload = {
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.2, "num_predict": max_tokens},
    }
    if think_false:
        payload["think"] = False
    try:
        r = requests.post(f"{ENDPOINT}/api/generate",
                          json=payload, timeout=timeout)
        r.raise_for_status()
        return {"text": r.json().get("response", ""),
                "latency_ms": int((time.time() - t0) * 1000), "error": None}
    except Exception as e:
        return {"text": "", "latency_ms": int((time.time() - t0) * 1000),
                "error": str(e)}


def run_model(model_name, model_id, think_false, queries):
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

            r1 = call_ollama(prompt, model_id, think_false)
            p1, p1l = r1["text"], r1["latency_ms"]
            p2, p2l = "", 0

            if cond == "full_pipeline" and not r1["error"]:
                p2p = build_pass2(p1, q["q"])
                r2 = call_ollama(p2p, model_id, think_false, max_tokens=256)
                p2, p2l = r2["text"], r2["latency_ms"]

            final = p2 if p2 else p1
            status = "ERR" if r1.get("error") else "OK"
            print(f"  [{model_name}:{count}/{total}] {cond}/{q['id']} "
                  f"({p1l + p2l}ms) {status}", flush=True)

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


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["qwen3", "mixtral", "all"], default="all",
                        help="Run specific model phase")
    args = parser.parse_args()

    model_map = {"qwen3": [MODELS[0]], "mixtral": [MODELS[1]], "all": MODELS}
    targets = model_map[args.model]

    t0 = time.time()
    all_results = []

    for model in targets:
        name = model["name"]
        model_id = model["model_id"]
        think_false = model["think_false"]

        print(f"\n=== {name} (single worker, CPU offload) ===")
        print(f"  think:false = {think_false}")
        print(f"  Warming {model_id}...")
        call_ollama("warmup", model_id, think_false, max_tokens=1)
        time.sleep(10)

        results = run_model(name, model_id, think_false, QUERIES)
        all_results.extend(results)

        ok = sum(1 for r in results if not r["error"])
        err = sum(1 for r in results if r["error"])
        print(f"  {name} done: {ok} OK, {err} ERR")

    elapsed = time.time() - t0
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    suffix = f"_{args.model}" if args.model != "all" else ""
    out = out_dir / f"qk_benchmark_v2_moe_eval{suffix}_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n=== Done in {elapsed:.0f}s | {len(all_results)} inferences → {out} ===")


if __name__ == "__main__":
    main()
