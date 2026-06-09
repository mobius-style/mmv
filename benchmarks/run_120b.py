#!/usr/bin/env python3
"""
Run gpt-oss-120b benchmark via Groq API.
60 queries x 4 conditions = 240 inferences.

Author : Taiko Toeda / MOBIUS LLC
"""
import json, time, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from benchmarks.qk_benchmark_v2 import (
    QUERIES, CONDITIONS, build_no_qk, build_fixed_qk,
    build_ism_qk, build_pass2, call_groq, load_groq_key,
)

def main():
    key = load_groq_key()
    model = "openai/gpt-oss-120b"
    print(f"Model: {model} | Queries: {len(QUERIES)} | Conditions: {len(CONDITIONS)}")
    print(f"Total: {len(QUERIES)*len(CONDITIONS)} inferences\n")

    results = []
    total = len(QUERIES) * len(CONDITIONS)
    count = 0
    t0 = time.time()

    for cond in CONDITIONS:
        for q in QUERIES:
            count += 1
            prompt = {"baseline": build_no_qk, "fixed_qk_all": build_fixed_qk,
                      "ism_adaptive": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
                      "full_pipeline": lambda qr, i=q["intent"]: build_ism_qk(qr, i),
                      }[cond](q["q"])

            r1 = call_groq(prompt, model, api_key=key)
            time.sleep(1.0)
            p1, p1l = r1["text"], r1["latency_ms"]
            p2, p2l = "", 0

            if cond == "full_pipeline" and not r1["error"]:
                p2p = build_pass2(p1, q["q"])
                r2 = call_groq(p2p, model, api_key=key, max_tokens=256)
                time.sleep(1.0)
                p2, p2l = r2["text"], r2["latency_ms"]

            final = p2 if p2 else p1
            status = "ERR" if r1.get("error") else "OK"
            print(f"  [{count}/{total}] {cond}/{q['id']} ({p1l+p2l}ms) {status}", flush=True)

            results.append({
                "query_id": q["id"], "query": q["q"], "category": q["category"],
                "subtype": q["subtype"], "intent": q["intent"],
                "answer": q["answer"], "common_error": q.get("common_error", ""),
                "trap": q.get("trap", ""),
                "model": "gpt-oss-120b", "condition": cond,
                "response": final, "pass1_text": p1, "pass2_text": p2,
                "pass1_latency_ms": p1l, "pass2_latency_ms": p2l,
                "total_latency_ms": p1l + p2l, "error": r1.get("error"),
            })

    elapsed = time.time() - t0
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"qk_benchmark_v2_120b_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n=== Done in {elapsed:.0f}s | {len(results)} inferences → {out} ===")

if __name__ == "__main__":
    main()
