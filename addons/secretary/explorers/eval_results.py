"""Explorer: digest a generic eval directory (CSV / JSONL / log / md).

Schema-agnostic: walks the target, samples each file, and reports
structural facts — row counts, low-cardinality column distributions,
sample rows. Built for `eval/p9_evidence_pack_v1/`, `eval/rc3_2/`,
`eval/rc2_raw_vs_governed_comparison/`, and the like.

Output: a Markdown digest written to state/digests/eval_results_<ts>.md
by default.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Per-column distinct-value sample limits. Columns with more distinct
# values than `MAX_DISTINCT_REPORT` are reported as "(unique-like)".
MAX_DISTINCT_REPORT = 12
SAMPLE_ROWS = 3
MAX_BYTES_FOR_FULL_SCAN = 64 * 1024 * 1024  # 64 MiB / file


@dataclass
class FileDigest:
    relpath: str
    kind: str  # csv|jsonl|log|md|other
    bytes_: int
    rows: int | None
    columns: list[str] | None
    distributions: dict[str, Counter]
    sample: list[dict[str, Any]] | None
    note: str | None = None


def _kind(p: Path) -> str:
    s = p.suffix.lower()
    if s == ".csv":
        return "csv"
    if s == ".jsonl":
        return "jsonl"
    if s == ".log":
        return "log"
    if s == ".md":
        return "md"
    if s == ".json":
        return "json"
    return "other"


def _column_distribution(rows: list[dict[str, Any]], col: str) -> Counter:
    """Counter of values for column `col`. Returns capped representation
    if the column looks like a unique identifier."""
    c: Counter = Counter()
    for r in rows:
        v = r.get(col)
        if isinstance(v, (list, dict)):
            v = type(v).__name__
        c[str(v) if v is not None else "∅"] += 1
    return c


def _digest_tabular(
    path: Path, kind: str, rows: list[dict[str, Any]],
) -> FileDigest:
    columns = list(rows[0].keys()) if rows else []
    dists: dict[str, Counter] = {}
    for col in columns:
        c = _column_distribution(rows, col)
        if len(c) <= MAX_DISTINCT_REPORT:
            dists[col] = c
    sample = rows[:SAMPLE_ROWS] if rows else None
    return FileDigest(
        relpath=str(path),
        kind=kind,
        bytes_=path.stat().st_size,
        rows=len(rows),
        columns=columns,
        distributions=dists,
        sample=sample,
    )


def digest_csv(path: Path) -> FileDigest:
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = [dict(r) for r in csv.DictReader(fh)]
    return _digest_tabular(path, "csv", rows)


def digest_jsonl(path: Path) -> FileDigest:
    rows: list[dict[str, Any]] = []
    note = None
    if path.stat().st_size > MAX_BYTES_FOR_FULL_SCAN:
        note = f"truncated: file > {MAX_BYTES_FOR_FULL_SCAN // 1024**2} MiB"
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
            if note and len(rows) >= 5000:
                break
    fd = _digest_tabular(path, "jsonl", rows)
    fd.note = note
    return fd


def digest_text(path: Path, kind: str) -> FileDigest:
    bytes_ = path.stat().st_size
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    sample = [{"line": ln} for ln in lines[:SAMPLE_ROWS]]
    tail = [{"line": ln} for ln in lines[-SAMPLE_ROWS:]] if len(lines) > SAMPLE_ROWS else None
    return FileDigest(
        relpath=str(path),
        kind=kind,
        bytes_=bytes_,
        rows=len(lines),
        columns=None,
        distributions={},
        sample=sample,
        note=(f"tail: {json.dumps([d['line'] for d in tail], ensure_ascii=False)}" if tail else None),
    )


def digest_file(path: Path) -> FileDigest:
    kind = _kind(path)
    if kind == "csv":
        return digest_csv(path)
    if kind == "jsonl":
        return digest_jsonl(path)
    if kind in ("log", "md"):
        return digest_text(path, kind)
    # other / json: report size only
    return FileDigest(
        relpath=str(path),
        kind=kind,
        bytes_=path.stat().st_size,
        rows=None,
        columns=None,
        distributions={},
        sample=None,
        note="not digested (unsupported kind)",
    )


def _fmt_counter(c: Counter) -> str:
    if not c:
        return "(empty)"
    parts = [f"{k}={n}" for k, n in c.most_common()]
    return ", ".join(parts)


def render(
    *,
    target: Path,
    files: list[FileDigest],
    release_line: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append("# Eval-results digest")
    lines.append("")
    lines.append(f"- source: `{target}`")
    lines.append(f"- generated_at: {now}")
    if release_line:
        lines.append(f"- secretary_release: {release_line}")
    lines.append(f"- files_digested: {len(files)}")
    lines.append("")
    for fd in files:
        lines.append(f"## `{fd.relpath}` ({fd.kind})")
        size_kib = fd.bytes_ // 1024
        lines.append(f"- size: {size_kib} KiB")
        if fd.rows is not None:
            lines.append(f"- rows: {fd.rows}")
        if fd.columns:
            lines.append(f"- columns ({len(fd.columns)}): {', '.join(fd.columns)}")
        for col, dist in fd.distributions.items():
            lines.append(f"  - **{col}**: {_fmt_counter(dist)}")
        if fd.sample:
            lines.append("- sample:")
            for r in fd.sample:
                short = json.dumps(r, ensure_ascii=False, default=str)
                if len(short) > 240:
                    short = short[:240] + "…"
                lines.append(f"  - {short}")
        if fd.note:
            lines.append(f"- note: {fd.note}")
        lines.append("")
    return "\n".join(lines)


def collect(target: Path, *, max_files: int = 30) -> list[FileDigest]:
    """Walk target (non-recursive by default would miss subdirs; we go
    one level deep for the canonical eval/*/ layout)."""
    if not target.exists():
        raise FileNotFoundError(f"eval dir not found: {target}")
    out: list[FileDigest] = []
    for p in sorted(target.rglob("*")):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if _kind(p) == "other":
            continue
        out.append(digest_file(p))
        if len(out) >= max_files:
            break
    return out


def build_digest(target: Path, *, release_line: str | None = None) -> str:
    files = collect(target)
    return render(target=target, files=files, release_line=release_line)
