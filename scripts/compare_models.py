"""Side-by-side comparison: bare 9B vs bare 120B (raw / 素の state).

Reads every JSONL in benchmarks/results/ and produces a single Markdown
report with:
  - per-benchmark mean score (ASCII bars)
  - per-governance-category mean score (ASCII bars)
  - per-subject inhouse_mc accuracy (ASCII bars)
  - latency comparison
  - placeholder benchmarks listed for completeness
  - sample-level disagreements (where 9B and 120B differ)

These are the 'bare' / 'raw' model profiles — there is no MMV-governed
runtime wired in yet (mobius-mmv-governed is status: placeholder). The
report header makes that distinction explicit.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"
REPORTS_DIR = REPO_ROOT / "benchmarks" / "reports"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.lib.config_loader import get_benchmark, load_benchmark_matrix

PROFILE_9B = "local-ollama-9b"
PROFILE_120B = "groq-gpt-oss-120b"
BAR_WIDTH = 24


def _read_all(results_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for p in sorted(results_dir.glob("*.jsonl")):
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def _bar(value: float, width: int = BAR_WIDTH) -> str:
    """Build a unicode block-bar for a value in [0, 1]."""
    if value is None:
        return " " * width
    v = max(0.0, min(1.0, float(value)))
    filled = int(round(v * width))
    return "█" * filled + "░" * (width - filled)


def _arrow(d9: float | None, d120: float | None) -> str:
    if d9 is None or d120 is None:
        return "·"
    diff = d120 - d9
    if abs(diff) < 1e-9:
        return "="
    return "↑" if diff > 0 else "↓"


def _delta_cell(d9: float | None, d120: float | None) -> str:
    if d9 is None or d120 is None:
        return "—"
    return f"{d120 - d9:+.3f}"


def _agg(rows: list[dict], group_keys: tuple[str, ...]) -> dict[tuple, dict]:
    """Group rows by group_keys; collect scores and latencies per group."""
    bucket: dict[tuple, dict[str, Any]] = defaultdict(
        lambda: {"scores": [], "latencies": [], "errors": 0, "samples": 0}
    )
    for r in rows:
        key = tuple(r.get(k) for k in group_keys)
        b = bucket[key]
        b["samples"] += 1
        b["latencies"].append(int(r.get("latency_ms") or 0))
        if r.get("error"):
            b["errors"] += 1
            continue
        s = r.get("score")
        if isinstance(s, (int, float)):
            b["scores"].append(float(s))
    return bucket


def _disagreements(rows: list[dict]) -> list[tuple[str, str, dict, dict]]:
    """Return (benchmark, sample_id, row_9b, row_120b) where scores differ."""
    by_key: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        if r.get("error") or not isinstance(r.get("score"), (int, float)):
            continue
        key = (r["benchmark"], r["sample_id"])
        by_key[key][r["model_profile"]] = r

    out = []
    for (bench, sid), profs in by_key.items():
        r9 = profs.get(PROFILE_9B)
        r120 = profs.get(PROFILE_120B)
        if r9 is None or r120 is None:
            continue
        if r9["score"] != r120["score"]:
            out.append((bench, sid, r9, r120))
    return out


def write_report(
    results_dir: Path | None = None,
    reports_dir: Path | None = None,
) -> Path:
    results_dir = results_dir or RESULTS_DIR
    reports_dir = reports_dir or REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_all(results_dir)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = reports_dir / f"comparison_9b_vs_120b_{stamp}.md"

    L: list[str] = []
    L.append(f"# Bare 9B vs Bare 120B — visual comparison ({stamp})")
    L.append("")
    L.append(f"- 9B  profile: `{PROFILE_9B}` — Ollama / qwen3.5:9b (think:false)")
    L.append(f"- 120B profile: `{PROFILE_120B}` — Groq / openai/gpt-oss-120b")
    L.append(
        "- Both profiles are the **bare / 素の state** of the underlying models. "
        "No MMV runtime in front. The `mobius-mmv-governed` profile is "
        "currently `status: placeholder` (HTTP wrapper not yet wired)."
    )
    L.append("")

    # ─── per-benchmark mean ────────────────────────────────────────────
    per_bench = _agg(rows, ("benchmark", "model_profile"))
    bench_names = sorted({k[0] for k in per_bench.keys()})

    scored_benches = []
    placeholder_benches = []
    for b in bench_names:
        s9 = per_bench.get((b, PROFILE_9B), {}).get("scores", [])
        s120 = per_bench.get((b, PROFILE_120B), {}).get("scores", [])
        if s9 or s120:
            scored_benches.append(b)
        else:
            placeholder_benches.append(b)

    L.append("## Per-benchmark mean score (scored benchmarks only)")
    L.append("")
    L.append("```")
    L.append(f"{'benchmark':<22} {'9B bar':<{BAR_WIDTH}}  9B mean  "
             f"{'120B bar':<{BAR_WIDTH}} 120B mean  Δ(120-9)  n")
    L.append("─" * (22 + 2 * BAR_WIDTH + 40))
    for b in scored_benches:
        s9 = per_bench[(b, PROFILE_9B)]["scores"] if (b, PROFILE_9B) in per_bench else []
        s120 = per_bench[(b, PROFILE_120B)]["scores"] if (b, PROFILE_120B) in per_bench else []
        m9 = mean(s9) if s9 else None
        m120 = mean(s120) if s120 else None
        L.append(
            f"{b:<22} "
            f"{_bar(m9):<{BAR_WIDTH}}  "
            f"{(f'{m9:.3f}' if m9 is not None else '  —  '):>7}  "
            f"{_bar(m120):<{BAR_WIDTH}} "
            f"{(f'{m120:.3f}' if m120 is not None else '  —  '):>9}  "
            f"{_delta_cell(m9, m120):>8}  "
            f"{max(len(s9), len(s120))}"
        )
    L.append("```")
    L.append("")
    L.append("| Benchmark | Metric | 9B mean | 120B mean | Δ (120−9) | n |")
    L.append("|---|---|---:|---:|---:|---:|")
    for b in scored_benches:
        s9 = per_bench[(b, PROFILE_9B)]["scores"] if (b, PROFILE_9B) in per_bench else []
        s120 = per_bench[(b, PROFILE_120B)]["scores"] if (b, PROFILE_120B) in per_bench else []
        m9 = mean(s9) if s9 else None
        m120 = mean(s120) if s120 else None
        try:
            metric = get_benchmark(b).get("metric", "—")
        except Exception:
            metric = "—"
        L.append(
            f"| `{b}` | {metric} | "
            f"{(f'{m9:.3f}' if m9 is not None else '—')} | "
            f"{(f'{m120:.3f}' if m120 is not None else '—')} | "
            f"{_delta_cell(m9, m120)} "
            f"{_arrow(m9, m120)} | {max(len(s9), len(s120))} |"
        )
    L.append("")

    # ─── governance per-category ──────────────────────────────────────
    L.append("## Möbius governance — per-category pass rate")
    L.append("")
    gov_rows = [r for r in rows
                if r["benchmark"] in ("mobius_governance", "sycophancy_eval")
                and isinstance(r.get("score"), (int, float))]
    cat_bucket: dict[tuple, list[float]] = defaultdict(list)
    for r in gov_rows:
        cat_bucket[(r["task"], r["model_profile"])].append(float(r["score"]))
    categories = sorted({k[0] for k in cat_bucket.keys()})

    L.append("```")
    L.append(f"{'category':<28} {'9B bar':<{BAR_WIDTH}}  9B    "
             f"{'120B bar':<{BAR_WIDTH}}  120B   Δ      n(9B/120B)")
    L.append("─" * (28 + 2 * BAR_WIDTH + 40))
    for c in categories:
        s9 = cat_bucket.get((c, PROFILE_9B), [])
        s120 = cat_bucket.get((c, PROFILE_120B), [])
        m9 = mean(s9) if s9 else None
        m120 = mean(s120) if s120 else None
        L.append(
            f"{c:<28} "
            f"{_bar(m9):<{BAR_WIDTH}}  "
            f"{(f'{m9:.2f}' if m9 is not None else ' —  '):>4}  "
            f"{_bar(m120):<{BAR_WIDTH}}  "
            f"{(f'{m120:.2f}' if m120 is not None else ' —  '):>5}  "
            f"{(f'{(m120-m9):+.2f}' if m9 is not None and m120 is not None else '  —  '):>5}  "
            f"({len(s9)}/{len(s120)})"
        )
    L.append("```")
    L.append("")

    # ─── per-subject inhouse_mc ──────────────────────────────────────
    imc_rows = [r for r in rows
                if r["benchmark"] == "inhouse_mc_smoke"
                and isinstance(r.get("score"), (int, float))]
    if imc_rows:
        L.append("## inhouse_mc_smoke — per-subject accuracy")
        L.append("")
        subj_bucket: dict[tuple, list[float]] = defaultdict(list)
        for r in imc_rows:
            subj_bucket[(r["task"], r["model_profile"])].append(float(r["score"]))
        subjects = sorted({k[0] for k in subj_bucket.keys()})
        L.append("```")
        L.append(f"{'subject':<22} {'9B bar':<{BAR_WIDTH}}  9B    "
                 f"{'120B bar':<{BAR_WIDTH}}  120B   Δ      n(9B/120B)")
        L.append("─" * (22 + 2 * BAR_WIDTH + 40))
        for s in subjects:
            s9 = subj_bucket.get((s, PROFILE_9B), [])
            s120 = subj_bucket.get((s, PROFILE_120B), [])
            m9 = mean(s9) if s9 else None
            m120 = mean(s120) if s120 else None
            L.append(
                f"{s:<22} "
                f"{_bar(m9):<{BAR_WIDTH}}  "
                f"{(f'{m9:.2f}' if m9 is not None else ' —  '):>4}  "
                f"{_bar(m120):<{BAR_WIDTH}}  "
                f"{(f'{m120:.2f}' if m120 is not None else ' —  '):>5}  "
                f"{(f'{(m120-m9):+.2f}' if m9 is not None and m120 is not None else '  —  '):>5}  "
                f"({len(s9)}/{len(s120)})"
            )
        L.append("```")
        L.append("")

    # ─── latency ──────────────────────────────────────────────────────
    L.append("## Latency comparison (per sample, scored rows only)")
    L.append("")
    lat: dict[str, list[int]] = defaultdict(list)
    tok_in: dict[str, int] = defaultdict(int)
    tok_out: dict[str, int] = defaultdict(int)
    for r in rows:
        if r.get("error"):
            continue
        if not isinstance(r.get("score"), (int, float)):
            continue
        prof = r["model_profile"]
        lat[prof].append(int(r.get("latency_ms") or 0))
        tok_in[prof] += int(r.get("tokens_in") or 0)
        tok_out[prof] += int(r.get("tokens_out") or 0)

    def _lat_bar(ms: float, vmax: float) -> str:
        if vmax <= 0:
            return " " * BAR_WIDTH
        filled = int(round(min(1.0, ms / vmax) * BAR_WIDTH))
        return "█" * filled + "░" * (BAR_WIDTH - filled)

    vmax = max((max(v) for v in lat.values() if v), default=1.0)
    L.append("```")
    L.append(f"{'profile':<24} {'mean-latency bar':<{BAR_WIDTH}}  mean(ms)  "
             f"p95(ms)  total(s)  samples  tokens_in  tokens_out")
    L.append("─" * (24 + BAR_WIDTH + 60))
    for prof, lats in sorted(lat.items()):
        if not lats:
            continue
        m = mean(lats)
        p95 = sorted(lats)[int(0.95 * (len(lats) - 1))]
        total_s = sum(lats) / 1000
        L.append(
            f"{prof:<24} {_lat_bar(m, vmax):<{BAR_WIDTH}}  "
            f"{m:>8.0f}  {p95:>7}  {total_s:>8.1f}  "
            f"{len(lats):>7}  {tok_in[prof]:>9}  {tok_out[prof]:>10}"
        )
    L.append("```")
    L.append("")

    # ─── sample-level disagreements ──────────────────────────────────
    disagreements = _disagreements(rows)
    L.append("## Where 9B and 120B disagree (sample-level)")
    L.append("")
    if not disagreements:
        L.append("_No score-level disagreement on shared samples._")
    else:
        L.append(f"Total {len(disagreements)} disagreement(s) across shared samples.")
        L.append("")
        L.append("| Benchmark | Sample | 9B | 120B | Category | Excerpt (winner) |")
        L.append("|---|---|---:|---:|---|---|")
        for bench, sid, r9, r120 in disagreements[:25]:
            winner = r120 if r120["score"] > r9["score"] else r9
            cat = winner.get("task", "—")
            excerpt = (winner.get("metadata", {}) or {}).get("response_excerpt", "")
            excerpt = (excerpt or "")[:120].replace("\n", " ").replace("|", "\\|")
            L.append(
                f"| `{bench}` | `{sid}` | {r9['score']:.0f} | {r120['score']:.0f} | "
                f"{cat} | {excerpt} |"
            )
        if len(disagreements) > 25:
            L.append("")
            L.append(f"_({len(disagreements) - 25} more disagreements not shown.)_")
    L.append("")

    # ─── placeholders ────────────────────────────────────────────────
    L.append("## Placeholder benchmarks (no score yet)")
    L.append("")
    if placeholder_benches:
        L.append("| Benchmark | Category | Status | Why |")
        L.append("|---|---|---|---|")
        for b in placeholder_benches:
            try:
                entry = get_benchmark(b)
                cat = entry.get("category", "—")
                status = entry.get("status", "—")
                deps = entry.get("requires_external_install", []) or []
                why = "needs: " + ", ".join(deps) if deps else "runner shim TODO"
            except Exception:
                cat = status = why = "—"
            L.append(f"| `{b}` | {cat} | {status} | {why} |")
    else:
        L.append("_All benchmarks listed have at least one scored row._")
    L.append("")

    # ─── final note ─────────────────────────────────────────────────
    L.append("## Reading notes")
    L.append("")
    L.append("- Bars are scaled to [0, 1]; full bar = 100% pass rate / accuracy.")
    L.append("- Δ = mean(120B) − mean(9B). Positive = 120B better.")
    L.append("- Latencies include all scored samples; 9B latencies on Ollama "
             "are dominated by the local generate loop, 120B by Groq round-trip.")
    L.append("- For per-category sample sizes, see the (n) columns; categories "
             "with very small n are noisy.")

    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="9B vs 120B visual comparison report"
    )
    p.add_argument("--results-dir", type=str, default=None)
    p.add_argument("--reports-dir", type=str, default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    out = write_report(
        results_dir=Path(args.results_dir) if args.results_dir else None,
        reports_dir=Path(args.reports_dir) if args.reports_dir else None,
    )
    print(f"Wrote comparison report → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
