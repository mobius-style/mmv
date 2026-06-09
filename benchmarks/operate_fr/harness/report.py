"""Markdown report renderer for OPERATE-FR v0.1.

Produces a component-vector report. No composite score. Distinguishes
"neutral baseline" (non-MMV) from "MMV-side technical report" by the
`section_label` argument.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def render_report(
    summary: dict[str, Any],
    *,
    profile_name: str,
    suite_name: str = "smoke100",
    section_label: str = "neutral_baseline",  # or "mmv_side_technical"
    extra_notes: str = "",
) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines: list[str] = []
    lines.append("# OPERATE-FR v0.1 — component-vector report")
    lines.append("")
    lines.append(f"- Suite: `{suite_name}`")
    lines.append(f"- Profile: `{profile_name}`")
    lines.append(f"- Report section: **{section_label}**")
    lines.append(f"- Generated: {stamp}")
    lines.append("")
    lines.append("> OPERATE-FR is a **candidate operational benchmark track**, "
                 "not a validated standard benchmark.  \n"
                 "> v0.1 reports a component vector. **No official composite score is computed.**  \n"
                 "> Route correctness is the primary metric; cost-side metrics expose trade-offs.")
    lines.append("")

    overall = summary.get("overall_route_correctness")
    lines.append("## Headline component vector")
    lines.append("")
    lines.append("| Metric | Value | n |")
    lines.append("|---|---:|---:|")
    lines.append(
        f"| Overall route correctness | "
        f"{(f'{overall:.3f}' if overall is not None else '—')} | "
        f"{summary.get('n_scored', 0)} |"
    )
    lines.append(
        f"| Stale-commitment rate | "
        f"{_pct(summary.get('stale_commitment_rate'))} | "
        f"in volatile + stale_premise_trap |"
    )
    lines.append(
        f"| Over-verification on stable controls | "
        f"{_pct(summary.get('over_verification_rate_on_stable_controls'))} | "
        f"in stable_control |"
    )
    lines.append(
        f"| Date-boundary clarity rate | "
        f"{_pct(summary.get('date_boundary_clarity_rate'))} | "
        f"where date_bound_answer allowed |"
    )
    lines.append(
        f"| Verification completion rate | "
        f"{_pct(summary.get('verification_completion_rate'))} | "
        f"where tool_calls observed |"
    )
    lines.append(
        f"| Avg response length (chars) | "
        f"{_num(summary.get('average_response_length_chars'))} | — |"
    )
    lines.append(
        f"| Avg latency (ms) | "
        f"{_num(summary.get('average_latency_ms'))} | — |"
    )
    lines.append(f"| Errors | {summary.get('n_errors', 0)} | — |")
    lines.append("")

    # ── per-family ──
    lines.append("## Route correctness by family")
    lines.append("")
    lines.append("| Family | Correctness | n |")
    lines.append("|---|---:|---:|")
    n_by_family = summary.get("n_by_family", {})
    for family in sorted((summary.get("route_correctness_by_family") or {}).keys()):
        v = summary["route_correctness_by_family"][family]
        lines.append(f"| `{family}` | {v:.3f} | {n_by_family.get(family, '—')} |")
    lines.append("")

    # ── failure modes ──
    fm = summary.get("failure_mode_counts") or {}
    lines.append("## Failure-mode counts")
    lines.append("")
    if not fm:
        lines.append("_(none recorded.)_")
    else:
        lines.append("| Failure mode | Count |")
        lines.append("|---|---:|")
        for k, v in sorted(fm.items(), key=lambda kv: -kv[1]):
            lines.append(f"| `{k}` | {v} |")
    lines.append("")

    # ── narrative notes ──
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- Route classifier: rule-based (see `harness/classify_route.py`). "
        "No LLM in the loop.\n"
        "- `verify` is granted for hedged-without-verification responses "
        "(\"I don't have realtime data…\") because OPERATE-FR v0.1 treats this "
        "as a verify-intent route. Tool-mode runs distinguish actual verification.\n"
        "- Tool-mode is not exercised by this harness yet; "
        "`verification_completion_rate` is `null` when no tool calls were observed.\n"
        "- Component vector only; do NOT collapse into a single number."
    )
    if extra_notes:
        lines.append("")
        lines.append(extra_notes)

    lines.append("")
    return "\n".join(lines) + "\n"


def _pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%"


def _num(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}"


def write_report_to(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
