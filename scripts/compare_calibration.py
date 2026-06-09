"""3-way comparison: raw vs MMV-v1 vs MMV-v2 (post-calibration) per model.

For each of {9B, 120B} produces a paired report:
    raw           vs   v1 (MMV without post-cal)   vs   v2 (MMV + post-cal)

Focus is on: does v2 close the regressions v1 introduced over raw, without
losing the lifts v1 added in half_step / over_leading / freshness?

Reads every JSONL in benchmarks/results/. Deduplicates per
(profile, benchmark, sample_id) keeping the LATEST timestamp.
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

BAR_WIDTH = 22

PAIRS = [
    {
        "label": "9B",
        "raw": "local-ollama-9b",
        "v1": "mobius-mmv-governed-9b",
        "v2": "mobius-mmv-governed-9b-v2",
    },
    {
        "label": "120B",
        "raw": "groq-gpt-oss-120b",
        "v1": "mobius-mmv-governed-120b",
        "v2": "mobius-mmv-governed-120b-v2",
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


def _by_sample(rows: list[dict]) -> dict[tuple, dict]:
    return {(r["benchmark"], r["sample_id"]): r for r in rows}


def _agg(rows: list[dict], key: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        out[r.get(key, "*")].append(float(r["score"]))
    return out


def _fmt(v: float | None, fmt: str = ".2f") -> str:
    return f"{v:{fmt}}" if v is not None else " — "


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "  —  "
    return f"{b - a:+.2f}"


def _render_pair(L: list[str], pair: dict, rows: list[dict]) -> None:
    raw_rows = _filter(rows, pair["raw"])
    v1_rows = _filter(rows, pair["v1"])
    v2_rows = _filter(rows, pair["v2"])

    L.append("")
    L.append(f"## {pair['label']}: raw vs v1 vs v2")
    L.append("")
    L.append(f"- raw: `{pair['raw']}`")
    L.append(f"- v1 : `{pair['v1']}`  (RoutingEngine, no post-cal)")
    L.append(f"- v2 : `{pair['v2']}` (RoutingEngine + contextual clarify "
             f"+ verify fallback)")
    L.append("")

    # ── per-benchmark mean ─────────────────────────────────────────────
    L.append(f"### {pair['label']} — per-benchmark mean")
    L.append("")
    by_b_raw = _agg(raw_rows, "benchmark")
    by_b_v1 = _agg(v1_rows, "benchmark")
    by_b_v2 = _agg(v2_rows, "benchmark")
    benches = sorted(set(by_b_raw) | set(by_b_v1) | set(by_b_v2))

    L.append("```")
    L.append(
        f"{'benchmark':<22}  "
        f"{'raw':<{BAR_WIDTH}}  raw   "
        f"{'v1':<{BAR_WIDTH}}  v1    "
        f"{'v2':<{BAR_WIDTH}}  v2    "
        f"Δv1-r  Δv2-v1 Δv2-r"
    )
    L.append("─" * (24 + 3 * BAR_WIDTH + 60))
    for b in benches:
        ra = by_b_raw.get(b, [])
        v1 = by_b_v1.get(b, [])
        v2 = by_b_v2.get(b, [])
        ma = mean(ra) if ra else None
        m1 = mean(v1) if v1 else None
        m2 = mean(v2) if v2 else None
        L.append(
            f"{b:<22}  "
            f"{_bar(ma):<{BAR_WIDTH}}  {_fmt(ma)}  "
            f"{_bar(m1):<{BAR_WIDTH}}  {_fmt(m1)}  "
            f"{_bar(m2):<{BAR_WIDTH}}  {_fmt(m2)}  "
            f"{_delta(ma, m1):>6} {_delta(m1, m2):>6} {_delta(ma, m2):>6}"
        )
    L.append("```")
    L.append("")

    L.append(
        "| Benchmark | raw | v1 | v2 | Δ v1−raw | Δ v2−v1 | Δ v2−raw | n |"
    )
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for b in benches:
        ra = by_b_raw.get(b, [])
        v1 = by_b_v1.get(b, [])
        v2 = by_b_v2.get(b, [])
        ma = mean(ra) if ra else None
        m1 = mean(v1) if v1 else None
        m2 = mean(v2) if v2 else None
        L.append(
            f"| `{b}` | "
            f"{_fmt(ma, '.3f')} | {_fmt(m1, '.3f')} | {_fmt(m2, '.3f')} | "
            f"{_delta(ma, m1)} | {_delta(m1, m2)} | {_delta(ma, m2)} | "
            f"{max(len(ra), len(v1), len(v2))} |"
        )
    L.append("")

    # ── per-category mean (governance only) ────────────────────────────
    L.append(f"### {pair['label']} — Möbius governance per-category")
    L.append("")
    gov_raw = [r for r in raw_rows if r["benchmark"] in
               ("mobius_governance", "sycophancy_eval")]
    gov_v1 = [r for r in v1_rows if r["benchmark"] in
              ("mobius_governance", "sycophancy_eval")]
    gov_v2 = [r for r in v2_rows if r["benchmark"] in
              ("mobius_governance", "sycophancy_eval")]
    by_c_raw = _agg(gov_raw, "task")
    by_c_v1 = _agg(gov_v1, "task")
    by_c_v2 = _agg(gov_v2, "task")
    cats = sorted(set(by_c_raw) | set(by_c_v1) | set(by_c_v2))

    L.append("```")
    L.append(
        f"{'category':<26}  "
        f"{'raw':<{BAR_WIDTH}}  raw   "
        f"{'v1':<{BAR_WIDTH}}  v1    "
        f"{'v2':<{BAR_WIDTH}}  v2    "
        f"Δv1-r  Δv2-v1 Δv2-r"
    )
    L.append("─" * (28 + 3 * BAR_WIDTH + 60))
    for c in cats:
        ra = by_c_raw.get(c, [])
        v1 = by_c_v1.get(c, [])
        v2 = by_c_v2.get(c, [])
        ma = mean(ra) if ra else None
        m1 = mean(v1) if v1 else None
        m2 = mean(v2) if v2 else None
        L.append(
            f"{c:<26}  "
            f"{_bar(ma):<{BAR_WIDTH}}  {_fmt(ma)}  "
            f"{_bar(m1):<{BAR_WIDTH}}  {_fmt(m1)}  "
            f"{_bar(m2):<{BAR_WIDTH}}  {_fmt(m2)}  "
            f"{_delta(ma, m1):>6} {_delta(m1, m2):>6} {_delta(ma, m2):>6}"
        )
    L.append("```")
    L.append("")

    # ── v1 → v2 movement ───────────────────────────────────────────────
    v1_by_sample = _by_sample(v1_rows)
    v2_by_sample = _by_sample(v2_rows)
    raw_by_sample = _by_sample(raw_rows)

    v1_to_v2_recover = []   # v1 fail → v2 pass
    v1_to_v2_regress = []   # v1 pass → v2 fail
    v2_recover_vs_raw = []  # raw fail → v2 pass
    v2_regress_vs_raw = []  # raw pass → v2 fail

    keys = set(v1_by_sample) | set(v2_by_sample) | set(raw_by_sample)
    for k in keys:
        ra = raw_by_sample.get(k)
        v1 = v1_by_sample.get(k)
        v2 = v2_by_sample.get(k)
        if v1 and v2 and v1["score"] != v2["score"]:
            if v2["score"] > v1["score"]:
                v1_to_v2_recover.append((k, v1, v2))
            else:
                v1_to_v2_regress.append((k, v1, v2))
        if ra and v2 and ra["score"] != v2["score"]:
            if v2["score"] > ra["score"]:
                v2_recover_vs_raw.append((k, ra, v2))
            else:
                v2_regress_vs_raw.append((k, ra, v2))

    L.append(f"### {pair['label']} — v1 → v2 movement")
    L.append("")
    L.append(f"- v2 recovered **{len(v1_to_v2_recover)}** samples that v1 failed")
    L.append(f"- v2 regressed **{len(v1_to_v2_regress)}** samples that v1 passed")
    L.append("")
    L.append(f"### {pair['label']} — raw → v2 movement")
    L.append("")
    L.append(f"- v2 recovered **{len(v2_recover_vs_raw)}** samples that raw failed")
    L.append(f"- v2 regressed **{len(v2_regress_vs_raw)}** samples that raw passed")
    L.append("")

    if v1_to_v2_recover:
        L.append(f"#### {pair['label']} — what v2 fixed over v1 (up to 12)")
        L.append("")
        L.append("| Sample | Category | post_cal notes | v2 excerpt |")
        L.append("|---|---|---|---|")
        for (bench, sid), v1, v2 in v1_to_v2_recover[:12]:
            cat = v2.get("task", "—")
            notes = ((v2.get("metadata", {}) or {}).get("response_excerpt") or "")
            notes = notes.replace("\n", " ").replace("|", "\\|")[:140]
            pc_meta = ((v2.get("metadata", {}) or {}).get("post_process_notes")) or "—"
            L.append(f"| `{sid}` | {cat} | {pc_meta} | {notes} |")
        L.append("")

    if v1_to_v2_regress:
        L.append(f"#### {pair['label']} — what v2 broke vs v1 (up to 12)")
        L.append("")
        L.append("| Sample | Category | v2 excerpt |")
        L.append("|---|---|---|")
        for (bench, sid), v1, v2 in v1_to_v2_regress[:12]:
            cat = v2.get("task", "—")
            ex = ((v2.get("metadata", {}) or {}).get("response_excerpt") or "")
            ex = ex.replace("\n", " ").replace("|", "\\|")[:140]
            L.append(f"| `{sid}` | {cat} | {ex} |")
        L.append("")

    # ── latency ────────────────────────────────────────────────────────
    L.append(f"### {pair['label']} — latency")
    L.append("")
    L.append("```")
    L.append(f"{'profile':<28} {'mean(ms)':>10} {'p95(ms)':>10} "
             f"{'samples':>10}")
    L.append("─" * 70)
    for label, rs in (("raw", raw_rows), ("v1", v1_rows), ("v2", v2_rows)):
        lats = [int(r.get("latency_ms") or 0) for r in rs]
        if not lats:
            continue
        p95 = sorted(lats)[int(0.95 * (len(lats) - 1))]
        L.append(
            f"{label+': '+pair[label]:<28} {mean(lats):>10.0f} "
            f"{p95:>10} {len(lats):>10}"
        )
    L.append("```")
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
    out_path = reports_dir / f"compare_calibration_{stamp}.md"

    L: list[str] = []
    L.append(f"# Calibration impact — raw / v1 / v2 ({stamp})")
    L.append("")
    L.append(
        "v1 = MMV RoutingEngine, retrieval OFF (no post-processing). "
        "v2 = v1 + benchmark-side post-processor "
        "(`benchmarks/lib/mmv_post_processor.py`):"
    )
    L.append(
        "  (1) contextual clarify rewrite — when MMV routes to `ask` and "
        "emits a generic clarify, swap in a context-specific template "
        "(file? code? deictic? real-time? medical? financial?)."
    )
    L.append(
        "  (2) verify-route fallback — when MMV routes to `verify` and the "
        "response is empty or too thin (because retrieval is off), reissue "
        "the query to the raw adapter with a hedge-prompt."
    )
    L.append("")
    L.append(
        "Neither v1 nor v2 modifies `src/`. Same probe set (governance N=60 "
        "deduped, inhouse_mc N=30). Latency includes any second call from "
        "verify fallback."
    )
    L.append("")

    # Headline
    L.append("## Headline (mean score per benchmark)")
    L.append("")
    L.append(
        "| Pair | Benchmark | raw | v1 | v2 | Δ v1−raw | Δ v2−v1 | Δ v2−raw |"
    )
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for pair in PAIRS:
        raw_rows = _filter(rows, pair["raw"])
        v1_rows = _filter(rows, pair["v1"])
        v2_rows = _filter(rows, pair["v2"])
        by_b_raw = _agg(raw_rows, "benchmark")
        by_b_v1 = _agg(v1_rows, "benchmark")
        by_b_v2 = _agg(v2_rows, "benchmark")
        benches = sorted(set(by_b_raw) | set(by_b_v1) | set(by_b_v2))
        for b in benches:
            ra = by_b_raw.get(b, [])
            v1 = by_b_v1.get(b, [])
            v2 = by_b_v2.get(b, [])
            ma = mean(ra) if ra else None
            m1 = mean(v1) if v1 else None
            m2 = mean(v2) if v2 else None
            L.append(
                f"| **{pair['label']}** | `{b}` | "
                f"{_fmt(ma, '.3f')} | {_fmt(m1, '.3f')} | {_fmt(m2, '.3f')} | "
                f"{_delta(ma, m1)} | {_delta(m1, m2)} | {_delta(ma, m2)} |"
            )
    L.append("")

    for pair in PAIRS:
        _render_pair(L, pair, rows)

    L.append("## Reading notes")
    L.append("")
    L.append("- Bars scaled to [0, 1]; full bar = 100%.")
    L.append("- Δ v1−raw shows how much MMV (no post-cal) moved the needle.")
    L.append("- Δ v2−v1 shows the **post-calibration contribution**.")
    L.append("- Δ v2−raw shows whether MMV+post-cal beats the bare model overall.")
    L.append("- `post_cal notes` in the recovery table shows which intervention "
             "fired: `clarify_rewritten` (contextual ask), `verify_fallback` "
             "(hedged answer to a thin verify), or both.")

    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="raw / v1 / v2 3-way comparison")
    p.add_argument("--results-dir", type=str, default=None)
    p.add_argument("--reports-dir", type=str, default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    out = write_report(
        results_dir=Path(args.results_dir) if args.results_dir else None,
        reports_dir=Path(args.reports_dir) if args.reports_dir else None,
    )
    print(f"Wrote calibration comparison → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
