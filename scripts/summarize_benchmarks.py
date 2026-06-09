"""Aggregate every JSONL in benchmarks/results/ into a Markdown report.

Output:
  - benchmarks/reports/summary_<timestamp>.md
  - benchmarks/reports/summary_<timestamp>.csv  (per-(benchmark,profile,task) rows)

The Markdown report covers:
  - overall score table per (benchmark, profile)
  - per-category aggregation
  - failed / placeholder benchmarks
  - cost/time approximation from latencies
  - re-run command for each non-enabled row
  - governance scoring summary
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"
REPORTS_DIR = REPO_ROOT / "benchmarks" / "reports"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _gather(results_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for p in sorted(results_dir.glob("*.jsonl")):
        rows.extend(_read_jsonl(p))
    return rows


def _bench_category(name: str) -> str:
    try:
        from benchmarks.lib.config_loader import get_benchmark
        return str(get_benchmark(name).get("category", "uncategorized"))
    except Exception:
        return "uncategorized"


def _agg_by(rows: list[dict], keys: list[str]) -> dict[tuple, dict[str, Any]]:
    bucket: dict[tuple, dict[str, Any]] = defaultdict(
        lambda: {"scores": [], "errors": 0, "latencies_ms": [],
                 "placeholders": 0, "samples": 0, "metric": None,
                 "tokens_in": 0, "tokens_out": 0}
    )
    for r in rows:
        k = tuple(r.get(x) for x in keys)
        b = bucket[k]
        b["samples"] += 1
        b["metric"] = r.get("metric_name") or b["metric"]
        b["latencies_ms"].append(int(r.get("latency_ms") or 0))
        b["tokens_in"] += int(r.get("tokens_in") or 0)
        b["tokens_out"] += int(r.get("tokens_out") or 0)
        err = r.get("error")
        if err:
            b["errors"] += 1
            if str(err).startswith("PLACEHOLDER"):
                b["placeholders"] += 1
        s = r.get("score")
        if isinstance(s, (int, float)):
            b["scores"].append(float(s))
    return bucket


def _format_score(scores: list[float]) -> str:
    if not scores:
        return "—"
    return f"{mean(scores):.3f} (n={len(scores)})"


def write_summary(
    results_dir: Path | None = None,
    reports_dir: Path | None = None,
) -> tuple[Path, Path]:
    results_dir = results_dir or RESULTS_DIR
    reports_dir = reports_dir or REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    rows = _gather(results_dir)

    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = reports_dir / f"summary_{stamp}.md"
    csv_path = reports_dir / f"summary_{stamp}.csv"

    # ── CSV: one row per (benchmark, profile, task) ─────────────────────
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        wcsv = csv.writer(fh)
        wcsv.writerow([
            "benchmark", "profile", "task", "samples", "scored_samples",
            "errors", "placeholders", "mean_score", "metric",
            "mean_latency_ms", "tokens_in_sum", "tokens_out_sum",
        ])
        for (b, p, t), v in sorted(_agg_by(rows, ["benchmark", "model_profile", "task"]).items()):
            wcsv.writerow([
                b, p, t, v["samples"], len(v["scores"]),
                v["errors"], v["placeholders"],
                f"{mean(v['scores']):.4f}" if v["scores"] else "",
                v["metric"] or "",
                f"{mean(v['latencies_ms']):.0f}" if v["latencies_ms"] else "",
                v["tokens_in"], v["tokens_out"],
            ])

    # ── Markdown report ────────────────────────────────────────────────
    try:
        rel_src = results_dir.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel_src = str(results_dir)
    lines: list[str] = [
        f"# Benchmark summary — {stamp}",
        "",
        f"- Source: `{rel_src}` ({len(rows)} rows from "
        f"{len(list(results_dir.glob('*.jsonl')))} files)",
        "",
        "## Overall scores (mean per benchmark × profile)",
        "",
        "| Benchmark | Profile | Samples | Scored | Errors | Placeholders | Mean score | Metric | Mean latency (ms) |",
        "|---|---|---:|---:|---:|---:|---|---|---:|",
    ]
    overall = _agg_by(rows, ["benchmark", "model_profile"])
    for (b, p), v in sorted(overall.items()):
        score_cell = (
            f"**{mean(v['scores']):.3f}**" if v["scores"]
            else ("—" if v["placeholders"] else "no_score")
        )
        latency_cell = f"{mean(v['latencies_ms']):.0f}" if v["latencies_ms"] else "—"
        lines.append(
            f"| {b} | {p} | {v['samples']} | {len(v['scores'])} | "
            f"{v['errors']} | {v['placeholders']} | {score_cell} | "
            f"{v['metric'] or '—'} | {latency_cell} |"
        )

    # ── Per-category ───────────────────────────────────────────────────
    lines += ["", "## Per-category mean score (enabled rows only)", "",
              "| Category | Profile | Mean score | n |", "|---|---|---|---:|"]
    cat_bucket: dict[tuple, list[float]] = defaultdict(list)
    for r in rows:
        s = r.get("score")
        if not isinstance(s, (int, float)):
            continue
        cat = _bench_category(r["benchmark"])
        cat_bucket[(cat, r["model_profile"])].append(float(s))
    for (c, p), scores in sorted(cat_bucket.items()):
        lines.append(f"| {c} | {p} | {mean(scores):.3f} | {len(scores)} |")

    # ── Failed / placeholder ──────────────────────────────────────────
    lines += ["", "## Placeholder / failed benchmarks", ""]
    bad = [(b, p, v) for (b, p), v in overall.items()
           if v["placeholders"] or v["errors"]]
    if not bad:
        lines.append("_None — every row produced a score._")
    else:
        lines += [
            "| Benchmark | Profile | Errors | Placeholders | Re-run hint |",
            "|---|---|---:|---:|---|",
        ]
        for b, p, v in sorted(bad):
            hint = f"`python benchmarks/run_suite.py --suite standard --profiles {p}`"
            lines.append(f"| {b} | {p} | {v['errors']} | {v['placeholders']} | {hint} |")

    # ── Cost / time approximation ──────────────────────────────────────
    lines += ["", "## Cost & time", "", "Approximate per-profile wall-clock from latencies:"]
    prof_latency: dict[str, list[int]] = defaultdict(list)
    prof_tokens_in: dict[str, int] = defaultdict(int)
    prof_tokens_out: dict[str, int] = defaultdict(int)
    for r in rows:
        prof_latency[r["model_profile"]].append(int(r.get("latency_ms") or 0))
        prof_tokens_in[r["model_profile"]] += int(r.get("tokens_in") or 0)
        prof_tokens_out[r["model_profile"]] += int(r.get("tokens_out") or 0)
    lines += ["", "| Profile | Total latency (s) | Tokens in | Tokens out |",
              "|---|---:|---:|---:|"]
    for p, lats in sorted(prof_latency.items()):
        lines.append(
            f"| {p} | {sum(lats)/1000:.1f} | {prof_tokens_in[p]} | {prof_tokens_out[p]} |"
        )

    # ── Governance focus ─────────────────────────────────────────────
    lines += ["", "## Möbius governance summary", ""]
    gov_rows = [r for r in rows if r["benchmark"] in ("mobius_governance",
                                                     "sycophancy_eval")]
    if not gov_rows:
        lines.append("_No governance rows in this batch._")
    else:
        # by (task = category, profile)
        gov_bucket: dict[tuple, list[float]] = defaultdict(list)
        for r in gov_rows:
            s = r.get("score")
            if isinstance(s, (int, float)):
                gov_bucket[(r["task"], r["model_profile"])].append(float(s))
        lines += ["| Probe category | Profile | Pass rate | n |",
                  "|---|---|---:|---:|"]
        for (cat, p), scores in sorted(gov_bucket.items()):
            lines.append(f"| {cat} | {p} | {mean(scores):.3f} | {len(scores)} |")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, csv_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Summarize benchmark JSONL into Markdown + CSV")
    p.add_argument("--results-dir", type=str, default=None)
    p.add_argument("--reports-dir", type=str, default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    import sys
    args = _parse_args(argv)
    md, csv_p = write_summary(
        results_dir=Path(args.results_dir) if args.results_dir else None,
        reports_dir=Path(args.reports_dir) if args.reports_dir else None,
    )
    print(f"Wrote summary → {md}")
    print(f"Wrote CSV     → {csv_p}")
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main(_sys.argv[1:]))
