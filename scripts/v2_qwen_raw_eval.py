#!/usr/bin/env python3
"""
v2_qwen_raw_eval.py — qwen3.5:9b RAW評価（EALなし）
EAL・KVS・Retrieval を全バイパスしてOllamaに直接投げる。
v2ベースライン比較用：raw vs EAL の差を測定する。

Usage:
    python scripts/v2_qwen_raw_eval.py --runs 10
"""
import argparse
import csv
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3.5:9b"
INPUT_CSV    = "eval_results_20260322_073658.csv"

PHASE_H_EAL = {"A": 1.0, "B": 1.0}   # EALあり実証済み値（比較用）


def call_ollama(prompt: str, temperature: float = 0.0, timeout: int = 30) -> tuple[str, float]:
    payload = json.dumps({
        "model":   OLLAMA_MODEL,
        "prompt":  prompt,
        "stream":  False,
        "think":   False,
        "options": {
            "temperature": temperature,
            "num_predict": 256,
            "num_ctx":     2048,
        }
    }).encode("utf-8")
    t0 = time.time()
    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ms = round((time.time() - t0) * 1000, 1)
            return data.get("response", "").strip(), ms
    except Exception as e:
        return f"[ERROR: {e}]", round((time.time() - t0) * 1000, 1)


def build_raw_prompt(question: str) -> str:
    """EALなし・システムプロンプトなし・直接質問"""
    return f"Answer this question concisely in 1-2 sentences:\n\n{question}"


def judge(row: dict, response: str) -> str:
    """phase_h_llm_eval.pyと同じ正誤判定ロジック"""
    resp_lower = response.lower()

    # Cat-C: verify-failedが正解
    if row.get("category") == "C":
        return "verify-failed"

    # 既存モデルの正解応答からヒントを取得
    hints = []
    for model in ["phi4_mini", "phi4_14b", "gptoss_20b", "phi4_mini_reasoning"]:
        if row.get(f"{model}_correct") == "correct":
            raw = row.get(f"{model}_raw", "")
            if raw and len(raw) < 300:
                import re
                nums  = re.findall(r'\b\d+\b', raw)
                names = re.findall(r'\b[A-Z][a-z]{2,}\b', raw)
                hints.extend(nums[:3])
                hints.extend([n.lower() for n in names[:3]])

    if hints:
        if any(h.lower() in resp_lower for h in hints):
            return "correct"
        return "incorrect"

    # ヒントなし → Phase B4でcorrectなら正解とみなす
    b4_correct = row.get("qwen3_5_9b_correct") or row.get("mmv_correct", "")
    if b4_correct == "correct":
        return "correct"
    return "unknown"


def run_raw_eval(queries: list[dict], runs: int, temperature: float) -> dict:
    from collections import defaultdict

    results = []
    cat_correct = defaultdict(list)
    latencies   = []

    total = len(queries) * runs
    done  = 0

    for run_idx in range(runs):
        for row in queries:
            qid      = row.get("qid", "")
            category = row.get("category", "")
            question = row.get("question", "")

            prompt = build_raw_prompt(question)
            response, ms = call_ollama(prompt, temperature=temperature)
            verdict = judge(row, response)

            latencies.append(ms)
            is_correct = (verdict == "correct")
            cat_correct[category].append(is_correct)

            results.append({
                "run":       run_idx + 1,
                "qid":       qid,
                "category":  category,
                "question":  question,
                "response":  response,
                "verdict":   verdict,
                "correct":   is_correct,
                "latency_ms": ms,
            })

            done += 1
            if done % 10 == 0:
                print(f"  [{done}/{total}] run={run_idx+1} qid={qid} "
                      f"verdict={verdict} latency={ms:.0f}ms")

    # 集計
    summary = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "model":       OLLAMA_MODEL,
        "mode":        "RAW (EAL bypass)",
        "n_runs":      runs,
        "n_queries":   len(queries),
        "total_calls": total,
        "temperature": temperature,
        "correct_rate": {},
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
    }

    for cat in ["A", "B", "C"]:
        vals = cat_correct.get(cat, [])
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        summary["correct_rate"][cat] = {
            "mean":    round(mean, 4),
            "n":       len(vals),
            "phase_h_eal": PHASE_H_EAL.get(cat, "N/A"),
            "delta_vs_eal": round(mean - PHASE_H_EAL[cat], 4) if cat in PHASE_H_EAL else "N/A",
        }

    return summary, results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default=INPUT_CSV)
    parser.add_argument("--runs",   type=int,   default=10)
    parser.add_argument("--temp",   type=float, default=0.0)
    parser.add_argument("--max",    type=int,   default=None)
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv  = f"logs/v2_qwen_raw_{ts}.csv"
    out_json = f"logs/v2_qwen_raw_{ts}_summary.json"

    queries = []
    with open(args.input, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            queries.append(row)
    if args.max:
        queries = queries[:args.max]

    print(f"Model : {OLLAMA_MODEL} [RAW mode — EAL bypass]")
    print(f"Input : {args.input} ({len(queries)} queries)")
    print(f"Runs  : {args.runs}")
    print(f"Output: {out_csv}")
    print("=" * 60)

    summary, results = run_raw_eval(queries, args.runs, args.temp)

    # CSV出力
    Path("logs").mkdir(exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

    # JSON出力
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # サマリー表示
    print("=" * 60)
    print(f"Model : {OLLAMA_MODEL} [RAW]")
    print(f"Calls : {summary['total_calls']}")
    print(f"Latency: {summary['avg_latency_ms']:.0f}ms/call")
    for cat, v in summary["correct_rate"].items():
        delta = v['delta_vs_eal']
        delta_str = f"{delta:+.1%}" if isinstance(delta, float) else delta
        print(f"Cat-{cat}: {v['mean']:.1%} (EAL: {v['phase_h_eal']}, Δ={delta_str})")
    print(f"CSV   : {out_csv}")
    print(f"JSON  : {out_json}")


if __name__ == "__main__":
    main()
