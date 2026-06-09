"""Raw vs MMV (RoutingEngine variant) visual comparison — gemma4:26b pair.

Sibling of `compare_raw_vs_mmv.py` (which is hard-coded to 9B / 120B
pairs). Same rendering logic, only the PAIRS list differs.

Pair under test:
    gemma4:26b  raw: raw-gemma4-26b
                MMV: mobius-mmv-governed-gemma4-26b

IMPORTANT — what the "MMV" column here means:
    The benchmarks/ harness wraps the model through the local
    RoutingEngine (src/kernel/routing_engine.py) plus the benchmark-
    side post-processor (benchmarks/lib/mmv_post_processor.py). This
    is the same governance stack as the 9B path. It is NOT the same
    as OPERATE-FR's "Medium RC3.3", which uses the Large RC3.3 v3.1
    stack (route_transformer + post_validator + force_reanchor_v2 in
    operate-fr-bench/harness/route_transformer.py). Both are valid
    "MMV governance over gemma4:26b" experiments — they probe
    DIFFERENT governance architectures.
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

from benchmarks.lib.config_loader import get_benchmark

BAR_WIDTH = 24

PAIRS = [
    {
        "label": "gemma4-26b",
        "raw": "raw-gemma4-26b",
        "mmv": "mobius-mmv-governed-gemma4-26b",
        "raw_desc": "gemma4:26b via Ollama (think:false), no governance",
        "mmv_desc": "RoutingEngine + gemma4:26b (Ollama adapter, no retrieval) "
                    "— RoutingEngine variant, NOT OPERATE-FR Medium RC3.3",
    },
]


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


def _bar(value: float | None, width: int = BAR_WIDTH) -> str:
    if value is None:
        return " " * width
    v = max(0.0, min(1.0, float(value)))
    filled = int(round(v * width))
    return "█" * filled + "░" * (width - filled)


def _delta_cell(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "—"
    return f"{b - a:+.3f}"


def _arrow(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "·"
    d = b - a
    if abs(d) < 1e-9:
        return "="
    return "↑" if d > 0 else "↓"


def _filter(rows: list[dict], profile: str) -> list[dict]:
    keep: dict[tuple, dict] = {}
    for r in rows:
        if r.get("model_profile") != profile:
            continue
        if not isinstance(r.get("score"), (int, float)):
            continue
        if r.get("error"):
            continue
        key = (r["benchmark"], r["sample_id"])
        prev = keep.get(key)
        if prev is None or (r.get("timestamp", "") > prev.get("timestamp", "")):
            keep[key] = r
    return list(keep.values())


def _agg(rows: list[dict], key: str) -> dict[str, list[float]]:
    bucket: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        bucket[r.get(key, "*")].append(float(r["score"]))
    return bucket


def _render_pair(L: list[str], pair: dict, rows: list[dict]) -> None:
    raw_rows = _filter(rows, pair["raw"])
    mmv_rows = _filter(rows, pair["mmv"])

    L.append("")
    L.append(f"## {pair['label']}: raw vs MMV")
    L.append("")
    L.append(f"- raw: `{pair['raw']}` — {pair['raw_desc']}")
    L.append(f"- MMV: `{pair['mmv']}` — {pair['mmv_desc']}")
    L.append("")

    # ── per-benchmark mean ─────────────────────────────────────────────
    L.append(f"### {pair['label']} — per-benchmark mean")
    L.append("")
    raw_by_bench = _agg(raw_rows, "benchmark")
    mmv_by_bench = _agg(mmv_rows, "benchmark")
    benches = sorted(set(raw_by_bench) | set(mmv_by_bench))

    L.append("```")
    L.append(
        f"{'benchmark':<22} "
        f"{'raw bar':<{BAR_WIDTH}}   raw    "
        f"{'MMV bar':<{BAR_WIDTH}}   MMV    Δ        n(raw/MMV)"
    )
    L.append("─" * (22 + 2 * BAR_WIDTH + 50))
    for b in benches:
        ra = raw_by_bench.get(b, [])
        mv = mmv_by_bench.get(b, [])
        ma = mean(ra) if ra else None
        mm = mean(mv) if mv else None
        L.append(
            f"{b:<22} "
            f"{_bar(ma):<{BAR_WIDTH}}  "
            f"{(f'{ma:.3f}' if ma is not None else '  —  '):>5}  "
            f"{_bar(mm):<{BAR_WIDTH}}  "
            f"{(f'{mm:.3f}' if mm is not None else '  —  '):>5}  "
            f"{_delta_cell(ma, mm):>7}  "
            f"({len(ra)}/{len(mv)})"
        )
    L.append("```")
    L.append("")

    L.append(
        "| Benchmark | Metric | raw mean | MMV mean | Δ (MMV−raw) | n (raw/MMV) |"
    )
    L.append("|---|---|---:|---:|---:|---:|")
    for b in benches:
        ra = raw_by_bench.get(b, [])
        mv = mmv_by_bench.get(b, [])
        ma = mean(ra) if ra else None
        mm = mean(mv) if mv else None
        try:
            metric = get_benchmark(b).get("metric", "—")
        except Exception:
            metric = "—"
        L.append(
            f"| `{b}` | {metric} | "
            f"{(f'{ma:.3f}' if ma is not None else '—')} | "
            f"{(f'{mm:.3f}' if mm is not None else '—')} | "
            f"{_delta_cell(ma, mm)} {_arrow(ma, mm)} | "
            f"{len(ra)} / {len(mv)} |"
        )
    L.append("")

    # ── governance per-category ──────────────────────────────────────
    gov_raw = [r for r in raw_rows
               if r["benchmark"] in ("mobius_governance", "sycophancy_eval")]
    gov_mmv = [r for r in mmv_rows
               if r["benchmark"] in ("mobius_governance", "sycophancy_eval")]
    raw_by_cat = _agg(gov_raw, "task")
    mmv_by_cat = _agg(gov_mmv, "task")
    cats = sorted(set(raw_by_cat) | set(mmv_by_cat))

    L.append(f"### {pair['label']} — Möbius governance per-category")
    L.append("")
    L.append("```")
    L.append(
        f"{'category':<28} "
        f"{'raw bar':<{BAR_WIDTH}}   raw   "
        f"{'MMV bar':<{BAR_WIDTH}}   MMV   Δ        n(raw/MMV)"
    )
    L.append("─" * (28 + 2 * BAR_WIDTH + 50))
    for c in cats:
        ra = raw_by_cat.get(c, [])
        mv = mmv_by_cat.get(c, [])
        ma = mean(ra) if ra else None
        mm = mean(mv) if mv else None
        L.append(
            f"{c:<28} "
            f"{_bar(ma):<{BAR_WIDTH}}  "
            f"{(f'{ma:.2f}' if ma is not None else ' —  '):>4}  "
            f"{_bar(mm):<{BAR_WIDTH}}  "
            f"{(f'{mm:.2f}' if mm is not None else ' —  '):>4}  "
            f"{_delta_cell(ma, mm):>7}  "
            f"({len(ra)}/{len(mv)})"
        )
    L.append("```")
    L.append("")

    # ── inhouse_mc per-subject ───────────────────────────────────────
    imc_raw = [r for r in raw_rows if r["benchmark"] == "inhouse_mc_smoke"]
    imc_mmv = [r for r in mmv_rows if r["benchmark"] == "inhouse_mc_smoke"]
    if imc_raw or imc_mmv:
        raw_by_subj = _agg(imc_raw, "task")
        mmv_by_subj = _agg(imc_mmv, "task")
        subjects = sorted(set(raw_by_subj) | set(mmv_by_subj))
        L.append(f"### {pair['label']} — inhouse_mc per-subject")
        L.append("")
        L.append("```")
        L.append(
            f"{'subject':<22} "
            f"{'raw bar':<{BAR_WIDTH}}   raw   "
            f"{'MMV bar':<{BAR_WIDTH}}   MMV   Δ        n(raw/MMV)"
        )
        L.append("─" * (22 + 2 * BAR_WIDTH + 50))
        for s in subjects:
            ra = raw_by_subj.get(s, [])
            mv = mmv_by_subj.get(s, [])
            ma = mean(ra) if ra else None
            mm = mean(mv) if mv else None
            L.append(
                f"{s:<22} "
                f"{_bar(ma):<{BAR_WIDTH}}  "
                f"{(f'{ma:.2f}' if ma is not None else ' —  '):>4}  "
                f"{_bar(mm):<{BAR_WIDTH}}  "
                f"{(f'{mm:.2f}' if mm is not None else ' —  '):>4}  "
                f"{_delta_cell(ma, mm):>7}  "
                f"({len(ra)}/{len(mv)})"
            )
        L.append("```")
        L.append("")

    # ── latency ───────────────────────────────────────────────────────
    raw_lat = [int(r.get("latency_ms") or 0) for r in raw_rows]
    mmv_lat = [int(r.get("latency_ms") or 0) for r in mmv_rows]
    vmax = max(max(raw_lat or [1]), max(mmv_lat or [1]))

    def _lat_bar(ms: float) -> str:
        if vmax <= 0:
            return " " * BAR_WIDTH
        filled = int(round(min(1.0, ms / vmax) * BAR_WIDTH))
        return "█" * filled + "░" * (BAR_WIDTH - filled)

    raw_mean = mean(raw_lat) if raw_lat else 0
    mmv_mean = mean(mmv_lat) if mmv_lat else 0
    raw_p95 = sorted(raw_lat)[int(0.95 * (len(raw_lat) - 1))] if raw_lat else 0
    mmv_p95 = sorted(mmv_lat)[int(0.95 * (len(mmv_lat) - 1))] if mmv_lat else 0

    L.append(f"### {pair['label']} — latency (per sample, scored rows only)")
    L.append("")
    L.append("```")
    L.append(
        f"{'profile':<34} {'mean-bar':<{BAR_WIDTH}}  mean(ms)  p95(ms)  total(s)  samples"
    )
    L.append("─" * (34 + BAR_WIDTH + 50))
    L.append(
        f"{pair['raw']:<34} {_lat_bar(raw_mean):<{BAR_WIDTH}}  "
        f"{raw_mean:>8.0f}  {raw_p95:>7}  {sum(raw_lat)/1000:>8.1f}  "
        f"{len(raw_lat):>7}"
    )
    L.append(
        f"{pair['mmv']:<34} {_lat_bar(mmv_mean):<{BAR_WIDTH}}  "
        f"{mmv_mean:>8.0f}  {mmv_p95:>7}  {sum(mmv_lat)/1000:>8.1f}  "
        f"{len(mmv_lat):>7}"
    )
    L.append("```")
    L.append("")

    # ── sample-level state changes ─────────────────────────────────
    raw_by_key = {(r["benchmark"], r["sample_id"]): r for r in raw_rows}
    mmv_by_key = {(r["benchmark"], r["sample_id"]): r for r in mmv_rows}
    flipped_up: list[tuple] = []
    flipped_dn: list[tuple] = []
    for k in raw_by_key.keys() & mmv_by_key.keys():
        ra, mv = raw_by_key[k], mmv_by_key[k]
        if ra["score"] == mv["score"]:
            continue
        item = (k[0], k[1], ra, mv)
        if mv["score"] > ra["score"]:
            flipped_up.append(item)
        else:
            flipped_dn.append(item)

    L.append(f"### {pair['label']} — sample flips (raw vs MMV)")
    L.append("")
    L.append(
        f"- MMV recovered {len(flipped_up)} samples that raw failed "
        f"(raw 0 → MMV 1)."
    )
    L.append(
        f"- MMV regressed {len(flipped_dn)} samples that raw passed "
        f"(raw 1 → MMV 0)."
    )
    L.append("")

    if flipped_up:
        L.append(f"#### {pair['label']} — recovered (raw 0 → MMV 1, sample of up to 12)")
        L.append("")
        L.append("| Benchmark | Sample | Category | MMV excerpt |")
        L.append("|---|---|---|---|")
        for bench, sid, ra, mv in flipped_up[:12]:
            cat = mv.get("task", "—")
            ex = ((mv.get("metadata", {}) or {}).get("response_excerpt") or "")[:140]
            ex = ex.replace("\n", " ").replace("|", "\\|")
            L.append(f"| `{bench}` | `{sid}` | {cat} | {ex} |")
        L.append("")

    if flipped_dn:
        L.append(f"#### {pair['label']} — regressed (raw 1 → MMV 0, sample of up to 12)")
        L.append("")
        L.append("| Benchmark | Sample | Category | MMV excerpt |")
        L.append("|---|---|---|---|")
        for bench, sid, ra, mv in flipped_dn[:12]:
            cat = mv.get("task", "—")
            ex = ((mv.get("metadata", {}) or {}).get("response_excerpt") or "")[:140]
            ex = ex.replace("\n", " ").replace("|", "\\|")
            L.append(f"| `{bench}` | `{sid}` | {cat} | {ex} |")
        L.append("")


def write_report(
    results_dir: Path | None = None,
    reports_dir: Path | None = None,
) -> Path:
    results_dir = results_dir or RESULTS_DIR
    reports_dir = reports_dir or REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_all(results_dir)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = reports_dir / f"comparison_raw_vs_mmv_gemma4_{stamp}.md"

    L: list[str] = []
    L.append(f"# Raw vs MMV (gemma4:26b) — visual comparison ({stamp})")
    L.append("")
    L.append(
        "Holds the underlying model constant (gemma4:26b via local Ollama) "
        "and toggles the MMV RoutingEngine + post-processor on/off. "
        "Retrieval (RAG / Box B / web) is **off** for the MMV profile so "
        "the comparison isolates the routing + governance contribution alone."
    )
    L.append("")
    L.append(
        "**Architectural note**: this is the *RoutingEngine variant* "
        "(src/kernel/routing_engine.py + benchmarks/lib/mmv_post_processor.py), "
        "the same governance stack used for the local 9B path. It is "
        "**different** from OPERATE-FR's \"Medium RC3.3\", which uses the "
        "Large RC3.3 v3.1 stack (route_transformer + post_validator + "
        "force_reanchor_v2). Both are valid \"MMV governance over "
        "gemma4:26b\" experiments — they probe different architectures."
    )
    L.append("")

    L.append("## Headline")
    L.append("")
    L.append("| Pair | Benchmark | raw mean | MMV mean | Δ (MMV−raw) | n |")
    L.append("|---|---|---:|---:|---:|---:|")
    for pair in PAIRS:
        raw_rows = _filter(rows, pair["raw"])
        mmv_rows = _filter(rows, pair["mmv"])
        for b in sorted({r["benchmark"] for r in raw_rows + mmv_rows}):
            ra = [r["score"] for r in raw_rows if r["benchmark"] == b]
            mv = [r["score"] for r in mmv_rows if r["benchmark"] == b]
            ma = mean(ra) if ra else None
            mm = mean(mv) if mv else None
            L.append(
                f"| **{pair['label']}** | `{b}` | "
                f"{(f'{ma:.3f}' if ma is not None else '—')} | "
                f"{(f'{mm:.3f}' if mm is not None else '—')} | "
                f"{_delta_cell(ma, mm)} {_arrow(ma, mm)} | "
                f"{max(len(ra), len(mv))} |"
            )
    L.append("")

    for pair in PAIRS:
        _render_pair(L, pair, rows)

    L.append("## Reading notes")
    L.append("")
    L.append("- Bars are scaled to [0, 1]; full bar = 100% pass rate / accuracy.")
    L.append("- Δ = MMV mean − raw mean. Positive = MMV better.")
    L.append("- Latency bars in each pair are scaled to the pair's own max.")
    L.append("- 'recovered' = raw failed but MMV passed for the same sample.")
    L.append("- 'regressed' = raw passed but MMV failed for the same sample.")
    L.append("- MMV runs use RoutingEngine with retrieval OFF: the lift comes "
             "from routing decisions (ask / verify / abstain / answer) and the "
             "framing applied by the kernel, not from extra evidence.")
    L.append("- See the OPERATE-FR Smoke-100 comparison "
             "(`operate-fr-bench/reports/gemma4_26b_route_transformer_plus_validator_v3_1_summary.json` "
             "vs `..._raw_gemma4_26b_no_tool_summary.json`) for the *Large stack* "
             "variant of \"MMV Medium over gemma4:26b\".")

    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="raw vs MMV per-model comparison report (gemma4:26b pair)")
    p.add_argument("--results-dir", type=str, default=None)
    p.add_argument("--reports-dir", type=str, default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    out = write_report(
        results_dir=Path(args.results_dir) if args.results_dir else None,
        reports_dir=Path(args.reports_dir) if args.reports_dir else None,
    )
    print(f"Wrote raw-vs-MMV (gemma4) comparison → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
