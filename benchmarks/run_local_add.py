#!/usr/bin/env python3
"""
Run 2 additional local models for QK benchmark v2.
  Phase A: ministral-3 (pipeline mode, both GPUs)
  Phase B: phi4 14B (single worker, spans both GPUs)

Author : Taiko Toeda / MOBIUS LLC
"""
import json, time, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from benchmarks.qk_benchmark_v2 import (
    QUERIES, CONDITIONS, build_no_qk, build_fixed_qk,
    build_ism_qk, build_pass2, call_ollama,
)


def run_model(name, model_id, endpoint, endpoint2, queries):
    results = []
    total = len(queries) * len(CONDITIONS)
    count = 0

    for cond in CONDITIONS:
        for q in queries:
            count += 1
            prompt = {"baseline": build_no_qk, "fixed_qk_all": build_fixed_qk,
                      "ism_adaptive": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
                      "full_pipeline": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
                      }[cond](q["q"])

            r1 = call_ollama(prompt, model_id, endpoint)
            p1, p1l = r1["text"], r1["latency_ms"]
            p2, p2l = "", 0

            if cond == "full_pipeline" and not r1["error"]:
                ep2 = endpoint2 or endpoint
                p2p = build_pass2(p1, q["q"])
                r2 = call_ollama(p2p, model_id, ep2, max_tokens=256)
                p2, p2l = r2["text"], r2["latency_ms"]

            final = p2 if p2 else p1
            status = "ERR" if r1.get("error") else "OK"
            print(f"  [{name}:{count}/{total}] {cond}/{q['id']} ({p1l+p2l}ms) {status}", flush=True)

            results.append({
                "query_id": q["id"], "query": q["q"], "category": q["category"],
                "subtype": q["subtype"], "intent": q["intent"],
                "answer": q["answer"], "common_error": q.get("common_error", ""),
                "trap": q.get("trap", ""),
                "model": name, "condition": cond,
                "response": final, "pass1_text": p1, "pass2_text": p2,
                "pass1_latency_ms": p1l, "pass2_latency_ms": p2l,
                "total_latency_ms": p1l + p2l, "error": r1.get("error"),
            })
    return results


def main():
    t0 = time.time()
    all_results = []

    # Phase A: ministral-3 (pipeline)
    print("=== Phase A: ministral-3 (pipeline) ===")
    print("  Warming port 11434...")
    call_ollama("warmup", "ministral-3:latest", "http://localhost:11434", max_tokens=1)
    print("  Warming port 11435...")
    call_ollama("warmup", "ministral-3:latest", "http://localhost:11435", max_tokens=1)
    time.sleep(5)
    all_results.extend(run_model(
        "ministral-3", "ministral-3:latest",
        "http://localhost:11434", "http://localhost:11435", QUERIES))

    # Phase B: phi4 14B (single worker)
    print("\n=== Phase B: phi4-14b (single worker) ===")
    print("  Warming port 11434 (14B, may take a moment)...")
    call_ollama("warmup", "phi4:latest", "http://localhost:11434", max_tokens=1)
    time.sleep(10)
    all_results.extend(run_model(
        "phi4-14b", "phi4:latest",
        "http://localhost:11434", None, QUERIES))

    elapsed = time.time() - t0
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"qk_benchmark_v2_local_add_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n=== Done in {elapsed:.0f}s | {len(all_results)} inferences → {out} ===")


if __name__ == "__main__":
    main()
