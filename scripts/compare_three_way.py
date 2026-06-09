"""Three-way per-model visual comparison: raw vs MMV-v1 vs MMV-v2.

For each of 9B and 120B, plots three columns of bars side by side:

    raw      = local-ollama-9b              /  groq-gpt-oss-120b
    MMV v1   = mobius-mmv-governed-9b       /  mobius-mmv-governed-120b
    MMV v2   = mobius-mmv-governed-9b-v2    /  mobius-mmv-governed-120b-v2

v2 adds the benchmark-side post-processor (contextual clarify +
verify-route fallback) on top of v1's RoutingEngine wiring. No src/
modifications.

Reads every JSONL under benchmarks/results/, deduplicates per
(profile, benchmark, sample_id) keeping the latest timestamp.
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

BAR_WIDTH = 18

PAIRS = [
    {
        "label": "9B",
        "raw":  "local-ollama-9b",
        "v1":   "mobius-mmv-governed-9b",
        "v2":   "mobius-mmv-governed-9b-v2",
        "model": "qwen3.5:9b (Ollama)",
    },
    {
        "label": "120B",
        "raw":  "groq-gpt-oss-120b",
        "v1":   "mobius-mmv-governed-120b",
        "v2":   "mobius-mmv-governed-120b-v2",
        "model": "openai/gpt-oss-120b (Groq)",
    },
]


def _read_all(d: Path) -> list[dict]:
    rows: list[dict] = []
    for p in sorted(d.glob("*.jsonl")):
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


def _bar(value: float | None, width: int = BAR_WIDTH) -> str:
    if value is None:
        return " " * width
    v = max(0.0, min(1.0, float(value)))
    filled = int(round(v * width))
    return "█" * filled + "░" * (width - filled)


def _arrow(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "·"
    d = b - a
    if abs(d) < 1e-9:
        return "="
    return "↑" if d > 0 else "↓"


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "—"
    return f"{b - a:+.3f}"


def _agg(rows: list[dict], key: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        out[r.get(key, "*")].append(float(r["score"]))
    return out


def _mean(xs: list[float]) -> float | None:
    return mean(xs) if xs else None


def _render(L: list[str], pair: dict, rows: list[dict]) -> None:
    raw_rows = _filter(rows, pair["raw"])
    v1_rows = _filter(rows, pair["v1"])
    v2_rows = _filter(rows, pair["v2"])

    L.append(f"\n## {pair['label']} ({pair['model']}): raw / MMV-v1 / MMV-v2\n")
    L.append(f"- raw:    `{pair['raw']}`")
    L.append(f"- MMV-v1: `{pair['v1']}` — RoutingEngine, retrieval OFF, no post-proc")
    L.append(f"- MMV-v2: `{pair['v2']}` — v1 + contextual clarify + verify fallback")
    L.append("")

    # ── per-benchmark ──
    raw_b = _agg(raw_rows, "benchmark")
    v1_b = _agg(v1_rows, "benchmark")
    v2_b = _agg(v2_rows, "benchmark")
    benches = sorted(set(raw_b) | set(v1_b) | set(v2_b))

    L.append(f"### {pair['label']} — per-benchmark mean (raw / v1 / v2)\n")
    L.append("```")
    L.append(
        f"{'benchmark':<22} "
        f"{'raw':<{BAR_WIDTH}}   "
        f"{'v1':<{BAR_WIDTH}}   "
        f"{'v2':<{BAR_WIDTH}}    raw    v1     v2    Δ(v2-raw)"
    )
    L.append("─" * (22 + 3 * (BAR_WIDTH + 3) + 35))
    for b in benches:
        ra, v1, v2 = raw_b.get(b, []), v1_b.get(b, []), v2_b.get(b, [])
        ma, mb, mc = _mean(ra), _mean(v1), _mean(v2)
        L.append(
            f"{b:<22} "
            f"{_bar(ma):<{BAR_WIDTH}}   "
            f"{_bar(mb):<{BAR_WIDTH}}   "
            f"{_bar(mc):<{BAR_WIDTH}}   "
            f"{(f'{ma:.2f}' if ma is not None else ' —  '):>5}  "
            f"{(f'{mb:.2f}' if mb is not None else ' —  '):>5}  "
            f"{(f'{mc:.2f}' if mc is not None else ' —  '):>5}  "
            f"{_delta(ma, mc):>9}"
        )
    L.append("```\n")

    L.append("| Benchmark | raw | v1 | v2 | Δ (v2−raw) | Δ (v2−v1) | n |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for b in benches:
        ra, v1, v2 = raw_b.get(b, []), v1_b.get(b, []), v2_b.get(b, [])
        ma, mb, mc = _mean(ra), _mean(v1), _mean(v2)
        L.append(
            f"| `{b}` | "
            f"{(f'{ma:.3f}' if ma is not None else '—')} | "
            f"{(f'{mb:.3f}' if mb is not None else '—')} | "
            f"{(f'{mc:.3f}' if mc is not None else '—')} | "
            f"{_delta(ma, mc)} {_arrow(ma, mc)} | "
            f"{_delta(mb, mc)} {_arrow(mb, mc)} | "
            f"{max(len(ra), len(v1), len(v2))} |"
        )
    L.append("")

    # ── governance per-category ──
    gov_raw = [r for r in raw_rows if r["benchmark"] in (
        "mobius_governance", "sycophancy_eval")]
    gov_v1 = [r for r in v1_rows if r["benchmark"] in (
        "mobius_governance", "sycophancy_eval")]
    gov_v2 = [r for r in v2_rows if r["benchmark"] in (
        "mobius_governance", "sycophancy_eval")]
    raw_c = _agg(gov_raw, "task")
    v1_c = _agg(gov_v1, "task")
    v2_c = _agg(gov_v2, "task")
    cats = sorted(set(raw_c) | set(v1_c) | set(v2_c))

    L.append(f"### {pair['label']} — Möbius governance per-category\n")
    L.append("```")
    L.append(
        f"{'category':<28} "
        f"{'raw':<{BAR_WIDTH}}   "
        f"{'v1':<{BAR_WIDTH}}   "
        f"{'v2':<{BAR_WIDTH}}    raw    v1     v2    Δ(v2-v1)"
    )
    L.append("─" * (28 + 3 * (BAR_WIDTH + 3) + 35))
    for c in cats:
        ra, v1, v2 = raw_c.get(c, []), v1_c.get(c, []), v2_c.get(c, [])
        ma, mb, mc = _mean(ra), _mean(v1), _mean(v2)
        L.append(
            f"{c:<28} "
            f"{_bar(ma):<{BAR_WIDTH}}   "
            f"{_bar(mb):<{BAR_WIDTH}}   "
            f"{_bar(mc):<{BAR_WIDTH}}   "
            f"{(f'{ma:.2f}' if ma is not None else ' —  '):>5}  "
            f"{(f'{mb:.2f}' if mb is not None else ' —  '):>5}  "
            f"{(f'{mc:.2f}' if mc is not None else ' —  '):>5}  "
            f"{_delta(mb, mc):>9}"
        )
    L.append("```\n")

    # ── inhouse_mc per-subject ──
    imc_raw = [r for r in raw_rows if r["benchmark"] == "inhouse_mc_smoke"]
    imc_v1 = [r for r in v1_rows if r["benchmark"] == "inhouse_mc_smoke"]
    imc_v2 = [r for r in v2_rows if r["benchmark"] == "inhouse_mc_smoke"]
    if imc_raw or imc_v1 or imc_v2:
        raw_s = _agg(imc_raw, "task")
        v1_s = _agg(imc_v1, "task")
        v2_s = _agg(imc_v2, "task")
        subjects = sorted(set(raw_s) | set(v1_s) | set(v2_s))
        L.append(f"### {pair['label']} — inhouse_mc per-subject\n")
        L.append("```")
        L.append(
            f"{'subject':<22} "
            f"{'raw':<{BAR_WIDTH}}   "
            f"{'v1':<{BAR_WIDTH}}   "
            f"{'v2':<{BAR_WIDTH}}    raw    v1     v2"
        )
        L.append("─" * (22 + 3 * (BAR_WIDTH + 3) + 25))
        for s in subjects:
            ra, v1, v2 = raw_s.get(s, []), v1_s.get(s, []), v2_s.get(s, [])
            ma, mb, mc = _mean(ra), _mean(v1), _mean(v2)
            L.append(
                f"{s:<22} "
                f"{_bar(ma):<{BAR_WIDTH}}   "
                f"{_bar(mb):<{BAR_WIDTH}}   "
                f"{_bar(mc):<{BAR_WIDTH}}   "
                f"{(f'{ma:.2f}' if ma is not None else ' —  '):>5}  "
                f"{(f'{mb:.2f}' if mb is not None else ' —  '):>5}  "
                f"{(f'{mc:.2f}' if mc is not None else ' —  '):>5}"
            )
        L.append("```\n")

    # ── recovered-from-v1 / regressed-from-v1 ──
    v1_by_key = {(r["benchmark"], r["sample_id"]): r for r in v1_rows}
    v2_by_key = {(r["benchmark"], r["sample_id"]): r for r in v2_rows}
    raw_by_key = {(r["benchmark"], r["sample_id"]): r for r in raw_rows}

    recovered_v1: list[tuple] = []   # v1 0 → v2 1
    regressed_v1: list[tuple] = []   # v1 1 → v2 0
    recovered_raw: list[tuple] = []  # raw 0 → v2 1
    regressed_raw: list[tuple] = []  # raw 1 → v2 0

    shared_v1 = v1_by_key.keys() & v2_by_key.keys()
    for k in shared_v1:
        s1, s2 = v1_by_key[k]["score"], v2_by_key[k]["score"]
        if s1 == s2:
            continue
        item = (k[0], k[1], v1_by_key[k], v2_by_key[k])
        if s2 > s1:
            recovered_v1.append(item)
        else:
            regressed_v1.append(item)

    shared_raw = raw_by_key.keys() & v2_by_key.keys()
    for k in shared_raw:
        s_raw, s2 = raw_by_key[k]["score"], v2_by_key[k]["score"]
        if s_raw == s2:
            continue
        item = (k[0], k[1], raw_by_key[k], v2_by_key[k])
        if s2 > s_raw:
            recovered_raw.append(item)
        else:
            regressed_raw.append(item)

    L.append(f"### {pair['label']} — v2 sample-level deltas\n")
    L.append(f"- vs v1: recovered {len(recovered_v1)}, regressed "
             f"{len(regressed_v1)} (net {len(recovered_v1) - len(regressed_v1):+d})")
    L.append(f"- vs raw: recovered {len(recovered_raw)}, regressed "
             f"{len(regressed_raw)} (net {len(recovered_raw) - len(regressed_raw):+d})")

    def _flip_table(label: str, items: list[tuple], cap: int = 10) -> None:
        if not items:
            return
        L.append("")
        L.append(f"#### {pair['label']} — {label} (up to {cap})\n")
        L.append("| Benchmark | Sample | Category | v2 excerpt |")
        L.append("|---|---|---|---|")
        for bench, sid, _, mv in items[:cap]:
            cat = mv.get("task", "—")
            ex = ((mv.get("metadata", {}) or {}).get("response_excerpt") or "")[:120]
            ex = ex.replace("\n", " ").replace("|", "\\|")
            L.append(f"| `{bench}` | `{sid}` | {cat} | {ex} |")

    _flip_table("recovered (v1 0 → v2 1)", recovered_v1)
    _flip_table("regressed (v1 1 → v2 0)", regressed_v1)


def write_report(
    results_dir: Path | None = None,
    reports_dir: Path | None = None,
) -> Path:
    results_dir = results_dir or RESULTS_DIR
    reports_dir = reports_dir or REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_all(results_dir)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = reports_dir / f"comparison_three_way_{stamp}.md"

    L: list[str] = []
    L.append(f"# raw / MMV-v1 / MMV-v2 — three-way comparison ({stamp})\n")
    L.append(
        "v2 adds two surgical fixes on top of v1's RoutingEngine wiring:\n"
        "  1. **Contextual clarify** — when MMV's ask route returns the "
        "generic clarify boilerplate, rewrite it with the concrete missing "
        "dimension (file, function, deictic referent, real-time data, "
        "medical context, financial personal advice, …).\n"
        "  2. **Verify fallback** — when MMV's verify route returns empty "
        "or near-empty text (typical when retrieval is OFF), re-call the "
        "underlying model with a 'hedge appropriately, do not invent' "
        "instruction.\n"
        "Both fixes live in `benchmarks/lib/mmv_post_processor.py`. No "
        "`src/` modifications. Retrieval remains OFF in both v1 and v2 "
        "so all lift is from the routing layer."
    )

    L.append("\n## Headline\n")
    L.append("| Pair | Benchmark | raw | v1 | v2 | Δ v2−raw | Δ v2−v1 | n |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for pair in PAIRS:
        raw_rows = _filter(rows, pair["raw"])
        v1_rows = _filter(rows, pair["v1"])
        v2_rows = _filter(rows, pair["v2"])
        for b in sorted({r["benchmark"] for r in raw_rows + v1_rows + v2_rows}):
            ra = [r["score"] for r in raw_rows if r["benchmark"] == b]
            v1 = [r["score"] for r in v1_rows if r["benchmark"] == b]
            v2 = [r["score"] for r in v2_rows if r["benchmark"] == b]
            ma, mb, mc = _mean(ra), _mean(v1), _mean(v2)
            L.append(
                f"| **{pair['label']}** | `{b}` | "
                f"{(f'{ma:.3f}' if ma is not None else '—')} | "
                f"{(f'{mb:.3f}' if mb is not None else '—')} | "
                f"{(f'{mc:.3f}' if mc is not None else '—')} | "
                f"{_delta(ma, mc)} {_arrow(ma, mc)} | "
                f"{_delta(mb, mc)} {_arrow(mb, mc)} | "
                f"{max(len(ra), len(v1), len(v2))} |"
            )

    for pair in PAIRS:
        _render(L, pair, rows)

    L.append("\n## Reading notes\n")
    L.append("- Bars: [0, 1]; full bar = 100% pass rate / accuracy.")
    L.append("- 'recovered (v1 → v2)' = a sample v1 failed but v2 passed.")
    L.append("- 'regressed (v1 → v2)' = a sample v1 passed but v2 failed.")
    L.append("- net = recovered − regressed.")
    L.append("- v2 still has no retrieval; freshness probes that would need "
             "a live source still hedge rather than answer with facts.")

    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="three-way raw/v1/v2 comparison")
    p.add_argument("--results-dir", type=str, default=None)
    p.add_argument("--reports-dir", type=str, default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    out = write_report(
        results_dir=Path(args.results_dir) if args.results_dir else None,
        reports_dir=Path(args.reports_dir) if args.reports_dir else None,
    )
    print(f"Wrote three-way comparison → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
