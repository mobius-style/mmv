"""Phase 4 — aggregate the frontier smoke JSONL results.

Reads <outdir>/results/results_<bench>_<condition>.jsonl × 24 and emits:
  - <outdir>/aggregate.yaml     (per-(bench, condition) component vectors)
  - <outdir>/deltas.yaml        (3 pair × 4 bench governance deltas)
  - <outdir>/frontier_table.md  (publication-ready table)
  - <outdir>/judge_review_samples.jsonl  (SimpleQA reviewer pool, ≤50)

Per spec §6.4, the report tail includes reporting discipline notes.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Optional

import yaml

CONDITIONS = [
    "raw_qwen35_9b", "mmv_small",
    "raw_gemma4_26b", "mmv_medium",
    "raw_gpt_oss_120b", "mmv_large",
]
BENCHES = ["mmlu_pro", "gpqa_diamond", "truthfulqa_mc1", "simpleqa"]
PAIRS = [
    ("small", "raw_qwen35_9b", "mmv_small", "qwen3.5:9b"),
    ("medium", "raw_gemma4_26b", "mmv_medium", "gemma4:26b"),
    ("large", "raw_gpt_oss_120b", "mmv_large", "gpt-oss-120b"),
]


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _component_vector(rows: list[dict], bench: str) -> dict:
    n = len(rows)
    if n == 0:
        return {"n_total": 0}
    strict_n = sum(1 for r in rows if r["strict_correct"])
    cond_rows = [r for r in rows if r["conditional_correct"] is not None]
    cond_n = sum(1 for r in cond_rows if r["conditional_correct"])

    routing_counts = Counter(
        (r.get("routing_decision") or "no_routing") for r in rows
    )
    routing_total = sum(routing_counts.values())
    routing_distribution = {
        k: round(v / routing_total, 4) for k, v in routing_counts.items()
    }

    layer_counts = Counter(
        (r.get("parse_layer") or "no_layer") for r in rows
    )
    layer_total = sum(layer_counts.values())
    parse_layer_distribution = {
        k: round(v / layer_total, 4) for k, v in layer_counts.items()
    }
    parse_failure_rate = round(
        sum(1 for r in rows if r.get("parse_failure")) / n, 4
    )

    abstain_rate = None
    needs_judge_review_rate = None
    if bench == "simpleqa":
        abstain_rate = round(
            sum(1 for r in rows if r.get("abstain_detected")) / n, 4
        )
        needs_judge_review_rate = round(
            sum(1 for r in rows if r.get("needs_judge_review")) / n, 4
        )

    latencies = [int(r.get("latency_ms") or 0) for r in rows]
    out_tokens = [r.get("output_tokens") for r in rows
                  if isinstance(r.get("output_tokens"), (int, float))]
    return {
        "n_total": n,
        "strict_accuracy": round(strict_n / n, 4),
        "conditional_accuracy":
            round(cond_n / len(cond_rows), 4) if cond_rows else None,
        "routing_distribution": routing_distribution,
        "parse_layer_distribution": parse_layer_distribution,
        "parse_failure_rate": parse_failure_rate,
        "needs_judge_review_rate": needs_judge_review_rate,
        "abstain_rate": abstain_rate,
        "avg_latency_ms": int(mean(latencies)) if latencies else 0,
        "avg_output_tokens": round(mean(out_tokens), 2) if out_tokens else None,
    }


def _bench_results_path(outdir: Path, bench: str, cond: str) -> Path:
    return outdir / "results" / f"results_{bench}_{cond}.jsonl"


def build_component_vectors(outdir: Path) -> dict:
    cv = {}
    for bench in BENCHES:
        cv[bench] = {}
        for cond in CONDITIONS:
            rows = _read_jsonl(_bench_results_path(outdir, bench, cond))
            cv[bench][cond] = _component_vector(rows, bench)
    return cv


def build_deltas(cv: dict) -> list[dict]:
    out = []
    for label, raw, mmv, base in PAIRS:
        for bench in BENCHES:
            r = cv.get(bench, {}).get(raw, {})
            m = cv.get(bench, {}).get(mmv, {})
            if not r.get("n_total") or not m.get("n_total"):
                continue
            sd = (m["strict_accuracy"] - r["strict_accuracy"]
                  if r.get("strict_accuracy") is not None
                  and m.get("strict_accuracy") is not None else None)
            cd = (m["conditional_accuracy"] - r["conditional_accuracy"]
                  if (r.get("conditional_accuracy") is not None
                      and m.get("conditional_accuracy") is not None)
                  else None)
            entry = {
                "pair": label,
                "base_model": base,
                "bench": bench,
                "raw_condition": raw,
                "mmv_condition": mmv,
                "strict_delta": round(sd, 4) if sd is not None else None,
                "conditional_delta": round(cd, 4) if cd is not None else None,
                "routing_distribution_mmv": m.get("routing_distribution"),
            }
            if bench == "simpleqa":
                entry["abstain_rate_raw"] = r.get("abstain_rate")
                entry["abstain_rate_mmv"] = m.get("abstain_rate")
            out.append(entry)
    return out


def _fmt(x: Optional[float], suffix: str = "") -> str:
    if x is None:
        return " --"
    return f"{x:.3f}{suffix}"


def build_frontier_table(cv: dict) -> str:
    L = []
    L.append("# Frontier-style comparison — 4 benches × 6 conditions")
    L.append("")
    L.append("Each `(bench × condition)` cell shows strict / conditional "
             "accuracy. SimpleQA also exposes the abstain rate (lower for "
             "raw, higher for MMV is the *expected* asymmetry).")
    L.append("")

    headers = ["Bench", "raw qwen3.5:9b", "MMV Small",
               "raw gemma4:26b", "MMV Medium",
               "raw gpt-oss-120b", "MMV Large"]
    L.append("| " + " | ".join(headers) + " |")
    L.append("|" + "|".join(["---"] + ["---:"] * 6) + "|")

    def row_metric(metric_label: str, key: str, fmt_pct=True):
        line = [metric_label]
        for cond in CONDITIONS:
            v = cv.get(bench, {}).get(cond, {}).get(key)
            if v is None:
                line.append("—")
            elif fmt_pct:
                line.append(f"{v:.3f}")
            else:
                line.append(f"{v}")
        L.append("| " + " | ".join(line) + " |")

    for bench in BENCHES:
        L.append(f"|  | | | | | | |")
        L.append(f"| **{bench}** | | | | | | |")
        row_metric(f"{bench} (strict)", "strict_accuracy")
        row_metric(f"{bench} (conditional)", "conditional_accuracy")
        if bench == "simpleqa":
            row_metric(f"{bench} (abstain_rate)", "abstain_rate")
            row_metric(f"{bench} (judge_review_rate)",
                       "needs_judge_review_rate")

    L.append("")
    L.append("## Latency (mean ms per call)")
    L.append("")
    L.append("| Bench | raw qwen3.5:9b | MMV Small | raw gemma4:26b | MMV Medium | raw gpt-oss-120b | MMV Large |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for bench in BENCHES:
        line = [bench]
        for cond in CONDITIONS:
            v = cv.get(bench, {}).get(cond, {}).get("avg_latency_ms")
            line.append(str(v) if v else "—")
        L.append("| " + " | ".join(line) + " |")
    L.append("")

    L.append("## Parse failure rate")
    L.append("")
    L.append("| Bench | raw qwen3.5:9b | MMV Small | raw gemma4:26b | MMV Medium | raw gpt-oss-120b | MMV Large |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for bench in BENCHES:
        line = [bench]
        for cond in CONDITIONS:
            v = cv.get(bench, {}).get(cond, {}).get("parse_failure_rate")
            line.append(f"{v:.1%}" if v is not None else "—")
        L.append("| " + " | ".join(line) + " |")
    L.append("")

    L.append("---")
    L.append("")
    L.append("## Reporting discipline notes (spec §6.4)")
    L.append("")
    L.append("- This smoke evaluates up to 496 questions per condition "
             "(MMLU-Pro 100, GPQA Diamond 198, TruthfulQA MC1 98, SimpleQA 100).")
    L.append("- Strict accuracy includes MMV non-answer routing as 0 points "
             "(OPERATE-FR §10.3 compliant).")
    L.append("- Conditional accuracy excludes non-answer routing from the "
             "denominator.")
    L.append("- Both metrics are reported in parallel; no composite score "
             "is defined.")
    L.append("- Governance is *expected* to lose on direct-answer benchmarks "
             "(MMLU-Pro, GPQA) and win on hallucination benchmarks "
             "(TruthfulQA, SimpleQA). If observed otherwise, the Section 14 "
             "FLAG framework applies before any standard-status claim.")
    L.append("- Vendor-published scores under FP16/BF16 are not directly "
             "comparable to these Q4_K_M Ollama results. `raw_*` columns in "
             "this smoke serve as the same-stack reference.")
    L.append("- raw_gpt_oss_120b uses `max_tokens=4096` to accommodate the "
             "model's internal reasoning channel; the MMV-Large profile "
             "keeps the original 1024 cap because the route_transformer "
             "prefix shortens reasoning. This token-budget asymmetry is "
             "*against* MMV, not in its favor.")
    L.append("- Environment: Ollama 0.24.0 (Ubuntu 24.04, RTX 5070 Ti), "
             "Q4_K_M quantization, 4096 context window. Groq API for "
             "gpt-oss-120b.")
    L.append("")
    return "\n".join(L)


def build_judge_review(outdir: Path, max_n: int = 50) -> list[dict]:
    samples = []
    for cond in CONDITIONS:
        rows = _read_jsonl(_bench_results_path(outdir, "simpleqa", cond))
        for r in rows:
            if r.get("needs_judge_review"):
                samples.append({
                    "condition": r["condition"],
                    "question_id": r["question_id"],
                    "subject_or_category": r.get("subject_or_category"),
                    "user_prompt": r["user_prompt"][:400],
                    "expected": r["expected_answer"],
                    "response": r.get("response_raw", "")[:600],
                    "scoring_layer": r.get("scoring_layer"),
                })
    rng = random.Random(42)
    rng.shuffle(samples)
    return samples[:max_n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    outdir = Path(args.outdir)

    cv = build_component_vectors(outdir)
    deltas = build_deltas(cv)
    table_md = build_frontier_table(cv)
    judge = build_judge_review(outdir)

    with (outdir / "aggregate.yaml").open("w") as fh:
        yaml.safe_dump(cv, fh, sort_keys=False, allow_unicode=True)
    with (outdir / "deltas.yaml").open("w") as fh:
        yaml.safe_dump(deltas, fh, sort_keys=False, allow_unicode=True)
    (outdir / "frontier_table.md").write_text(table_md, encoding="utf-8")
    with (outdir / "judge_review_samples.jsonl").open("w") as fh:
        for s in judge:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")

    print("Wrote:")
    print(" ", outdir / "aggregate.yaml")
    print(" ", outdir / "deltas.yaml")
    print(" ", outdir / "frontier_table.md")
    print(" ", outdir / "judge_review_samples.jsonl",
          f"({len(judge)} samples)")


if __name__ == "__main__":
    main()
