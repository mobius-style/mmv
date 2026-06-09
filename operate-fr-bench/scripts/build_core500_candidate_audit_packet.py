"""Build a paper-facing audit packet for Core-500 candidate runs.

This script intentionally treats Core-500 candidate as a controlled
Smoke-100-derived stress suite, not as an independent benchmark standard.
It collects component-vector metrics, Wilson intervals, row counts, and
SHA-256 hashes so a later paper draft can cite a reproducible artifact set
without overstating the claim boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

DEFAULT_LINE_PATTERNS = {
    "Small RC3.3": "small_rc3_3_core500_candidate_*_summary.json",
    "Medium RC0.1": "medium_rc0_1_core500_candidate_*_summary.json",
    "Large RC3.3": "large_rc3_3_core500_candidate_*_summary.json",
}

STATIC_ARTIFACTS = [
    ROOT / "data" / "core500.jsonl",
    ROOT / "data" / "labels" / "core500_route_labels.jsonl",
    ROOT / "configs" / "suite_core500.yaml",
    ROOT / "docs" / "CORE500_CANDIDATE_PROTOCOL_20260521.md",
    ROOT / "scripts" / "build_core500_from_smoke100.py",
    ROOT / "scripts" / "build_core500_candidate_audit_packet.py",
    ROOT / "reports" / "operate_fr_core500_candidate_s_m_l_20260521.md",
]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _count_jsonl(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for line in fh if line.strip())


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _latest(pattern: str) -> Path | None:
    matches = sorted(REPORTS.glob(pattern))
    return matches[-1] if matches else None


def _line_files(summary_path: Path) -> dict[str, Path]:
    stem = summary_path.name.removesuffix("_summary.json")
    return {
        "summary": summary_path,
        "results": REPORTS / f"{stem}.jsonl",
        "report": REPORTS / f"{stem}_report.md",
    }


def _wilson(correct: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return (math.nan, math.nan)
    p = correct / total
    den = 1 + z * z / total
    center = (p + z * z / (2 * total)) / den
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / den
    return (center - margin, center + margin)


def _fmt(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and math.isnan(value):
        return "-"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def _collect_line(label: str, summary_path: Path) -> dict[str, Any]:
    files = _line_files(summary_path)
    summary = _read_json(summary_path)
    cv = summary["component_vector"]
    totals = cv["totals"]
    correct = int(totals["route_correct"])
    scored = int(totals["scored_tasks"])
    ci_low, ci_high = _wilson(correct, scored)

    return {
        "label": label,
        "files": {k: str(v.relative_to(ROOT)) for k, v in files.items() if v.exists()},
        "n": scored,
        "errored": int(totals["errored"]),
        "route_correct": correct,
        "route_correctness": cv["route_correctness_overall"],
        "wilson_95_ci": [round(ci_low, 6), round(ci_high, 6)],
        "preferred_route_match_rate": cv["preferred_route_match_rate"],
        "stale_commitment_rate": cv["stale_commitment_rate"],
        "unsupported_current_claim_rate": cv["unsupported_current_claim_rate"],
        "over_verification_rate_on_stable_controls": cv[
            "over_verification_rate_on_stable_controls"
        ],
        "date_boundary_clarity_rate": cv["date_boundary_clarity_rate"],
        "average_response_length": cv["average_response_length"],
        "average_latency_ms": cv["average_latency_ms"],
        "route_correctness_by_family": cv["route_correctness_by_family"],
        "failure_mode_counts": cv["failure_mode_counts"],
        "predicted_route_distribution": cv["predicted_route_distribution"],
    }


def _artifact_record(path: Path) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "path": str(path.relative_to(ROOT)),
        "exists": path.exists(),
    }
    if path.exists():
        rec["sha256"] = _sha256(path)
        rec["bytes"] = path.stat().st_size
        if path.suffix == ".jsonl":
            rec["rows"] = _count_jsonl(path)
    return rec


def _render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# OPERATE-FR Core-500 Candidate -- Paper Audit Packet",
        "",
        f"Generated UTC: {packet['generated_utc']}",
        "",
        "## Claim Boundary",
        "",
        "Core-500 candidate is a controlled 5x neutral prompt-frame expansion",
        "of OPERATE-FR Smoke-100. It is suitable as larger-N candidate-line",
        "stress evidence, but it is not an independent benchmark standard,",
        "not externally validated, and not a deployment-wide validation claim.",
        "",
        "## Headline Results",
        "",
        "| Line | n | errored | route_correctness | Wilson 95% CI | preferred |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for line in packet["lines"]:
        ci = line["wilson_95_ci"]
        lines.append(
            "| {label} | {n} | {errored} | {rc} | {lo}-{hi} | {pref} |".format(
                label=line["label"],
                n=line["n"],
                errored=line["errored"],
                rc=_fmt(line["route_correctness"]),
                lo=_fmt(ci[0]),
                hi=_fmt(ci[1]),
                pref=_fmt(line["preferred_route_match_rate"]),
            )
        )

    families = [
        "volatile_current",
        "stale_premise_trap",
        "stable_control",
        "date_boundary",
        "query_neutrality",
        "ambiguous_time_frame",
    ]
    lines.extend([
        "",
        "## Per-Family Route Correctness",
        "",
        "| Family | Small RC3.3 | Medium RC0.1 | Large RC3.3 |",
        "|---|---:|---:|---:|",
    ])
    by_label = {line["label"]: line for line in packet["lines"]}
    for fam in families:
        row = [fam]
        for label in ("Small RC3.3", "Medium RC0.1", "Large RC3.3"):
            line = by_label.get(label)
            if not line:
                row.append("-")
                continue
            fam_rec = line["route_correctness_by_family"].get(fam, {})
            row.append(_fmt(fam_rec.get("rate")))
        lines.append(f"| `{row[0]}` | {row[1]} | {row[2]} | {row[3]} |")

    lines.extend([
        "",
        "## Artifact Hashes",
        "",
        "| Path | Rows | SHA-256 |",
        "|---|---:|---|",
    ])
    for artifact in packet["artifacts"]:
        rows = artifact.get("rows", "")
        sha = artifact.get("sha256", "missing")
        lines.append(f"| `{artifact['path']}` | {rows} | `{sha}` |")

    lines.extend([
        "",
        "## Reporting Discipline",
        "",
        "- Component vectors are reported; no official composite score is computed.",
        "- Any future composite score must disclose weights.",
        "- The Smoke-100-derived Core-500 candidate does not replace an",
        "  independently authored Core-500 suite.",
        "- Medium and Small results must be cited as their own line results;",
        "  they do not inherit Large RC3.3 performance.",
        "",
    ])
    return "\n".join(lines)


def build_packet() -> dict[str, Any]:
    lines: list[dict[str, Any]] = []
    dynamic_artifacts: list[Path] = []
    for label, pattern in DEFAULT_LINE_PATTERNS.items():
        summary = _latest(pattern)
        if summary is None:
            continue
        line = _collect_line(label, summary)
        lines.append(line)
        for p in _line_files(summary).values():
            if p.exists():
                dynamic_artifacts.append(p)

    artifacts = [_artifact_record(p) for p in STATIC_ARTIFACTS + dynamic_artifacts]
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": (
            "Controlled Smoke-100-derived Core-500 candidate; not an "
            "independent benchmark standard."
        ),
        "lines": lines,
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-md", default="reports/core500_candidate_paper_audit_20260521.md")
    parser.add_argument("--out-json", default="reports/core500_candidate_paper_audit_20260521.manifest.json")
    args = parser.parse_args()

    packet = build_packet()
    out_md = ROOT / args.out_md
    out_json = ROOT / args.out_json
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    out_md.write_text(_render_markdown(packet), encoding="utf-8")
    print(f"Wrote {out_md}")
    print(f"Wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
