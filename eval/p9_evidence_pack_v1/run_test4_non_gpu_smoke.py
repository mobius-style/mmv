#!/usr/bin/env python3
"""P9 Evidence Pack v1 — Test 4: Non-GPU / lightweight operation check.

Methodology:
- 50-query smoke drawn from holdout_english_longtail_v1.jsonl
  (deterministic stride sampling).
- CUDA_VISIBLE_DEVICES="" forces no GPU at the process level.
- We do NOT rebuild any FAISS / ME5 / ISM index. Pre-built Pattern
  Library FAISS index (committed locally) is the only retrieval surface.
- We measure:
    fatal_error_count   : exceptions during routing / retrieval
    mean_latency_s      : per-query wall clock
    routes_returned     : distribution of routes
    sessions_completed  : queries that finished without exception

This is an **operational sanity check**, not a performance benchmark.
We are testing that the local control path (routing / appraisal /
Pattern Library lookup / governance) does not require GPU at runtime.

Limitations (recorded):
- ME5 query-side embedding still runs on CPU through PyTorch. If a
  given install lacks PyTorch CPU support, the pipeline falls back to
  failure; this test would surface it.
- LLM synthesis (answer/verify) still calls Ollama, which itself may
  use GPU. We do NOT enforce no-GPU on Ollama; the wrapper only
  enforces no-GPU on the harness process.
- A "non-GPU full path" implies running synthesis without GPU as well.
  This test does not validate that — see Caveats in the report.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Hard CPU-only at the harness process level. Single-GPU rule satisfied
# trivially because we do not use any GPU here.
os.environ["CUDA_VISIBLE_DEVICES"] = ""

OUT_DIR = Path(__file__).resolve().parent
HOLDOUT = OUT_DIR / "holdout_english_longtail_v1.jsonl"
RESULTS_OUT = OUT_DIR / "non_gpu_smoke_results.json"

N_SMOKE = 50


def main() -> int:
    from scripts.pseudo_ui_runner import PseudoUISession

    if not HOLDOUT.exists():
        print(f"missing: {HOLDOUT}", file=sys.stderr)
        return 1

    queries = []
    for line in HOLDOUT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        queries.append(json.loads(line))

    # Deterministic stride: pick every (len/N)th to span all categories.
    if len(queries) >= N_SMOKE:
        step = len(queries) // N_SMOKE
        sampled = queries[::step][:N_SMOKE]
    else:
        sampled = queries[:N_SMOKE]

    latencies = []
    routes = {}
    fatal_errors = []
    completed = 0
    rows = []

    t_start = time.time()
    for i, q in enumerate(sampled, 1):
        sess = PseudoUISession()
        t0 = time.time()
        try:
            r = sess.process_turn(q["query"])
            ok = True
            elapsed = time.time() - t0
            actual = r.route or "(empty)"
            error = None
            completed += 1
        except Exception as e:
            ok = False
            elapsed = time.time() - t0
            actual = "(error)"
            error = f"{type(e).__name__}: {str(e)[:120]}"
            fatal_errors.append({"id": q["id"], "error": error})
        latencies.append(elapsed)
        routes[actual] = routes.get(actual, 0) + 1

        rows.append({
            "id": q["id"],
            "category": q["category"],
            "query": q["query"][:60],
            "actual_route": actual,
            "elapsed_s": round(elapsed, 3),
            "ok": ok,
            "error": error,
        })
        if i % 10 == 0 or i == len(sampled):
            mean_lat = sum(latencies) / len(latencies)
            print(f"  [{i}/{len(sampled)}] elapsed_total={time.time()-t_start:.1f}s "
                  f"mean_latency={mean_lat:.2f}s errors={len(fatal_errors)}",
                  flush=True)

    summary = {
        "test": "p9_evidence_pack_v1.test_4_non_gpu_smoke",
        "n_smoke": len(sampled),
        "n_completed": completed,
        "n_fatal_errors": len(fatal_errors),
        "fatal_errors": fatal_errors,
        "wall_clock_total_s": round(time.time() - t_start, 1),
        "latency": {
            "mean_s": round(statistics.mean(latencies), 3) if latencies else None,
            "median_s": round(statistics.median(latencies), 3) if latencies else None,
            "p90_s": round(sorted(latencies)[int(len(latencies)*0.9)], 3) if latencies else None,
            "max_s": round(max(latencies), 3) if latencies else None,
        },
        "routes_returned": routes,
        "verdict": "PASS" if len(fatal_errors) == 0 else "FAIL",
        "configuration": {
            "CUDA_VISIBLE_DEVICES": "",
            "harness": "scripts.pseudo_ui_runner.PseudoUISession",
            "fresh_session_per_query": True,
            "no_index_rebuild": True,
        },
        "limitations": [
            "ME5 query-side embedding runs on CPU PyTorch in this run; "
            "fallback failures (e.g. missing torch) would surface here.",
            "LLM synthesis (answer/verify routes) calls Ollama, which is "
            "outside this process. We do NOT enforce no-GPU on Ollama; "
            "this test only enforces no-GPU on the routing/retrieval "
            "harness itself.",
            "This is operational sanity, not performance benchmark. "
            "Latencies are not comparable across hardware.",
        ],
        "rows": rows,
    }

    RESULTS_OUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote results: {RESULTS_OUT}")
    print(f"verdict: {summary['verdict']} | completed={completed}/{len(sampled)} | mean={summary['latency']['mean_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
