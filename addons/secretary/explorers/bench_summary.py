"""Explorer: catalog `benchmarks/reports/` outputs into a Markdown brief.

The benchmarks/reports/ directory is full of timestamped artifacts —
comparison_*.md, summary_*.csv, comparison_*.csv, etc. Reading each one
costs tokens. This explorer:

  - lists every report file with size + mtime
  - groups by family (comparison / summary / orchestrator / ablation)
  - for `summary_*.csv` files, includes a head + row count

No network, no LLM.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


REPORT_FAMILIES = (
    ("ablation",       "ablation_"),
    ("comparison_md",  "comparison_"),
    ("orchestrator",   "_orchestrator"),
    ("summary_md",     "summary_"),
    ("summary_csv",    "summary_"),
)


@dataclass
class ReportFile:
    relpath: str
    family: str
    bytes_: int
    mtime: str
    extra: dict[str, str] = field(default_factory=dict)


def _family(name: str) -> str:
    """Heuristic: match by name prefix + extension."""
    if name.startswith("ablation_"):
        return "ablation"
    if name.startswith("comparison_"):
        return "comparison_md" if name.endswith(".md") else "comparison_other"
    if name.startswith("summary_"):
        return "summary_md" if name.endswith(".md") else "summary_csv"
    if "orchestrator" in name:
        return "orchestrator"
    if name.endswith(".jsonl"):
        return "jsonl"
    return "other"


def _summary_csv_head(path: Path, n: int = 3) -> dict[str, str]:
    """First N data rows + total row count for a summary_*.csv."""
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            rdr = csv.reader(fh)
            rows = list(rdr)
    except Exception as e:
        return {"error": str(e)}
    if not rows:
        return {"rows": "0"}
    header, data = rows[0], rows[1:]
    return {
        "rows": str(len(data)),
        "columns": ", ".join(header),
        "head": " | ".join(
            "; ".join(f"{h}={v}" for h, v in zip(header, row))
            for row in data[:n]
        ),
    }


def collect(reports_dir: Path) -> list[ReportFile]:
    if not reports_dir.exists():
        raise FileNotFoundError(f"reports dir not found: {reports_dir}")
    out: list[ReportFile] = []
    for p in sorted(reports_dir.iterdir()):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        stat = p.stat()
        rf = ReportFile(
            relpath=str(p),
            family=_family(p.name),
            bytes_=stat.st_size,
            mtime=datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc,
            ).isoformat(timespec="seconds"),
        )
        if rf.family == "summary_csv":
            rf.extra = _summary_csv_head(p)
        out.append(rf)
    return out


def render(
    *, reports_dir: Path, files: list[ReportFile],
    release_line: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    by_family: dict[str, list[ReportFile]] = defaultdict(list)
    for f in files:
        by_family[f.family].append(f)
    lines: list[str] = []
    lines.append("# Bench-summary digest")
    lines.append("")
    lines.append(f"- source: `{reports_dir}`")
    lines.append(f"- generated_at: {now}")
    if release_line:
        lines.append(f"- secretary_release: {release_line}")
    lines.append(f"- total files: {len(files)}")
    lines.append("")
    for fam in sorted(by_family):
        items = by_family[fam]
        lines.append(f"## {fam} ({len(items)})")
        lines.append("")
        for f in sorted(items, key=lambda x: x.mtime, reverse=True):
            kib = f.bytes_ // 1024
            lines.append(f"- `{Path(f.relpath).name}` — {kib} KiB · {f.mtime}")
            for k, v in f.extra.items():
                lines.append(f"    - {k}: {v}")
        lines.append("")
    return "\n".join(lines)


def build_digest(
    reports_dir: Path, *, release_line: str | None = None,
) -> str:
    files = collect(reports_dir)
    return render(reports_dir=reports_dir, files=files, release_line=release_line)
