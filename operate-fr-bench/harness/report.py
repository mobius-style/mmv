"""Markdown reporter for the OPERATE-FR v0.1 component vector.

Reads a summary JSON (output of score.py) and writes a Markdown report.
The report deliberately presents component metrics side-by-side; it does
NOT produce a composite score. Optional non-official scorecards may be
appended only when explicitly requested by the caller with disclosed
weights.

CLI:
    python -m harness.report \\
        --summary reports/foo_summary.json \\
        --out     reports/foo_report.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _fmt_rate(v: float | None) -> str:
    return "—" if v is None else f"{v:.3f}"


def _fmt_int_or_dash(v: Any) -> str:
    return "—" if v is None else str(v)


def render(summary: dict[str, Any], header_title: str | None = None) -> str:
    cv = summary.get("component_vector") or {}
    note = summary.get("note", "")
    title = header_title or "OPERATE-FR v0.1 — component-vector report"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    L: list[str] = []
    L.append(f"# {title}")
    L.append("")
    L.append(f"_Generated: {stamp}_")
    L.append("")
    L.append(
        "> OPERATE-FR is a **candidate operational benchmark track**, "
        "not a standard benchmark. No external validation. **No "
        "official composite score.** All numbers below are component "
        "metrics; cost-side measurements (length, latency, "
        "over-verification on stable controls) are reported alongside "
        "reliability metrics."
    )
    L.append("")
    if note:
        L.append(f"_Scorer note: {note}_")
        L.append("")

    # ── headline component vector ────────────────────────────────────
    L.append("## Component vector")
    L.append("")
    L.append("| Metric | Value |")
    L.append("|---|---:|")
    L.append(f"| route_correctness_overall | "
             f"{_fmt_rate(cv.get('route_correctness_overall'))} |")
    L.append(f"| preferred_route_match_rate | "
             f"{_fmt_rate(cv.get('preferred_route_match_rate'))} |")
    L.append(f"| stale_commitment_rate | "
             f"{_fmt_rate(cv.get('stale_commitment_rate'))} |")
    L.append(f"| unsupported_current_claim_rate | "
             f"{_fmt_rate(cv.get('unsupported_current_claim_rate'))} |")
    L.append(f"| over_verification_rate_on_stable_controls | "
             f"{_fmt_rate(cv.get('over_verification_rate_on_stable_controls'))} |")
    L.append(f"| date_boundary_clarity_rate | "
             f"{_fmt_rate(cv.get('date_boundary_clarity_rate'))} |")
    L.append(f"| verification_completion_rate | "
             f"{_fmt_rate(cv.get('verification_completion_rate'))} |")
    L.append(f"| query_contamination_rate | "
             f"{_fmt_rate(cv.get('query_contamination_rate'))} |")
    L.append(f"| average_response_length (chars) | "
             f"{int(cv.get('average_response_length', 0))} |")
    L.append(f"| average_latency_ms | "
             f"{int(cv.get('average_latency_ms', 0))} |")
    L.append("")

    # ── per-family ────────────────────────────────────────────────────
    L.append("## Route correctness by family")
    L.append("")
    L.append("| Family | n | correct | rate | preferred-match rate | errored |")
    L.append("|---|---:|---:|---:|---:|---:|")
    family_block = cv.get("route_correctness_by_family") or {}
    for fam, v in sorted(family_block.items()):
        L.append(
            f"| `{fam}` | {v['n']} | {v['correct']} | "
            f"{_fmt_rate(v['rate'])} | "
            f"{_fmt_rate(v.get('preferred_match_rate'))} | "
            f"{v.get('errored', 0)} |"
        )
    L.append("")

    # ── predicted-route distribution ─────────────────────────────────
    L.append("## Predicted route distribution")
    L.append("")
    L.append("| Route | Count |")
    L.append("|---|---:|")
    dist = cv.get("predicted_route_distribution") or {}
    for r, c in sorted(dist.items(), key=lambda kv: kv[1], reverse=True):
        L.append(f"| `{r}` | {c} |")
    L.append("")

    # ── confusion top ────────────────────────────────────────────────
    confusion = cv.get("route_confusion_top") or []
    if confusion:
        L.append("## Top route confusions (preferred → classified)")
        L.append("")
        L.append("| Preferred | Classified | Count |")
        L.append("|---|---|---:|")
        for c in confusion:
            L.append(f"| `{c['preferred']}` | `{c['classified']}` | {c['count']} |")
        L.append("")

    # ── failure modes ────────────────────────────────────────────────
    fms = cv.get("failure_mode_counts") or {}
    if fms:
        L.append("## Failure mode counts")
        L.append("")
        L.append("| Mode | Count |")
        L.append("|---|---:|")
        for fm, n in sorted(fms.items(), key=lambda kv: kv[1], reverse=True):
            L.append(f"| `{fm}` | {n} |")
        L.append("")

    # ── totals ───────────────────────────────────────────────────────
    totals = cv.get("totals") or {}
    if totals:
        L.append("## Totals")
        L.append("")
        L.append("| Field | Count |")
        L.append("|---|---:|")
        for k in ("total_tasks", "scored_tasks", "route_correct",
                  "route_correct_preferred", "errored"):
            L.append(f"| {k} | {totals.get(k, 0)} |")
        L.append("")

    # ── compliance footer ────────────────────────────────────────────
    L.append("## Reporting discipline reminders")
    L.append("")
    L.append("- This report exposes a **component vector**, not a single score.")
    L.append("- For any non-official scorecard, weights MUST be disclosed.")
    L.append("- A neutral baseline report must precede any MMV-side report.")
    L.append("- Standard-benchmark status is NOT claimed.")
    L.append("")
    return "\n".join(L) + "\n"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OPERATE-FR v0.1 reporter")
    p.add_argument("--summary", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--title", default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    md = render(summary, header_title=args.title)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"Wrote report → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
