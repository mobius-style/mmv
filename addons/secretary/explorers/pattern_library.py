"""Explorer: digest `config/pattern_library/` into a small Markdown brief.

Pattern Library is the highest-frequency edit surface in this repo
(top-touched files of the last 80 commits). Each `*.jsonl` file is one
topic; each row is a JSON pattern with a known schema:

  {
    "id", "topic", "intent", "sub_topic", "priority",
    "examples", "negative_examples", "cross_lingual_test_queries",
    "lifecycle": {"audit_status", "hit_count", "history": [...]},
    "deprecated", ...
  }

Output is a deterministic Markdown digest covering:
  - per-file row counts split by audit_status
  - sub-topic saturation (counts per sub_topic, the unit the autodriver
    uses to chase coverage)
  - hit-count distribution (active / cold / dead)
  - recent history (last N updated_at across all patterns)
  - taxonomy + thresholds file presence and size
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TAXONOMY = "_taxonomy.yaml"
THRESHOLDS = "thresholds.yaml"


@dataclass
class FileDigest:
    name: str
    rows: int = 0
    status_counts: Counter = field(default_factory=Counter)
    sub_topics: Counter = field(default_factory=Counter)
    deprecated: int = 0
    avg_priority: float = 0.0
    n_examples_total: int = 0
    n_negatives_total: int = 0
    n_xling_total: int = 0
    cold_patterns: int = 0      # hit_count == 0 or null
    last_history_ts: str | None = None


@dataclass
class LibraryDigest:
    library_dir: Path
    file_digests: list[FileDigest]
    total_rows: int
    total_active: int
    total_quarantined: int
    total_deprecated: int
    sub_topic_totals: Counter
    recent_events: list[tuple[str, str, str, str]]  # (ts, pattern_id, event, actor)
    taxonomy_path: Path | None
    taxonomy_bytes: int
    thresholds_path: Path | None
    thresholds_bytes: int


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # tolerate stray garbage; surface in digest by row count miss
            continue
    return rows


def digest_file(path: Path) -> FileDigest:
    rows = _parse_jsonl(path)
    fd = FileDigest(name=path.stem, rows=len(rows))
    priorities: list[int] = []
    last_ts: str | None = None
    for r in rows:
        lc = r.get("lifecycle") or {}
        status = (lc.get("audit_status") or "unknown")
        fd.status_counts[status] += 1
        if r.get("deprecated"):
            fd.deprecated += 1
        st = r.get("sub_topic") or "(unset)"
        fd.sub_topics[st] += 1
        if r.get("priority") is not None:
            try:
                priorities.append(int(r["priority"]))
            except (ValueError, TypeError):
                pass
        fd.n_examples_total += len(r.get("examples") or [])
        fd.n_negatives_total += len(r.get("negative_examples") or [])
        fd.n_xling_total += len(r.get("cross_lingual_test_queries") or [])
        hit = lc.get("hit_count") or 0
        if not hit:
            fd.cold_patterns += 1
        for ev in (lc.get("history") or []):
            ts = ev.get("timestamp")
            if ts and (last_ts is None or ts > last_ts):
                last_ts = ts
    fd.last_history_ts = last_ts
    if priorities:
        fd.avg_priority = sum(priorities) / len(priorities)
    return fd


def digest_library(library_dir: Path, recent_events_n: int = 10) -> LibraryDigest:
    if not library_dir.exists():
        raise FileNotFoundError(f"pattern library dir not found: {library_dir}")
    file_digests: list[FileDigest] = []
    sub_topic_totals: Counter = Counter()
    recent: list[tuple[str, str, str, str]] = []
    total_rows = total_active = total_quarantined = total_deprecated = 0

    for path in sorted(library_dir.glob("*.jsonl")):
        rows = _parse_jsonl(path)
        fd = digest_file(path)
        file_digests.append(fd)
        total_rows += fd.rows
        total_active += fd.status_counts.get("active", 0)
        total_quarantined += fd.status_counts.get("quarantined", 0)
        total_deprecated += fd.deprecated
        sub_topic_totals.update(fd.sub_topics)
        for r in rows:
            pid = r.get("id", "?")
            for ev in ((r.get("lifecycle") or {}).get("history") or []):
                ts = ev.get("timestamp")
                if not ts:
                    continue
                recent.append(
                    (ts, pid, ev.get("event", "?"), ev.get("actor", "?")),
                )
    recent.sort(key=lambda t: t[0], reverse=True)
    recent = recent[:recent_events_n]

    tax = library_dir / TAXONOMY
    thr = library_dir / THRESHOLDS
    return LibraryDigest(
        library_dir=library_dir,
        file_digests=file_digests,
        total_rows=total_rows,
        total_active=total_active,
        total_quarantined=total_quarantined,
        total_deprecated=total_deprecated,
        sub_topic_totals=sub_topic_totals,
        recent_events=recent,
        taxonomy_path=tax if tax.exists() else None,
        taxonomy_bytes=tax.stat().st_size if tax.exists() else 0,
        thresholds_path=thr if thr.exists() else None,
        thresholds_bytes=thr.stat().st_size if thr.exists() else 0,
    )


def _fmt_counter(c: Counter) -> str:
    if not c:
        return "(none)"
    return ", ".join(f"{k}={v}" for k, v in c.most_common())


def render_digest(d: LibraryDigest, *, release_line: str | None = None) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    L: list[str] = []
    L.append("# Pattern-library digest")
    L.append("")
    L.append(f"- source: `{d.library_dir}`")
    L.append(f"- generated_at: {now}")
    if release_line:
        L.append(f"- secretary_release: {release_line}")
    L.append("")

    L.append("## Totals")
    L.append("")
    L.append(f"- pattern files: **{len(d.file_digests)}**")
    L.append(f"- patterns: **{d.total_rows}** "
             f"(active={d.total_active}, quarantined={d.total_quarantined}, "
             f"deprecated={d.total_deprecated})")
    L.append(f"- distinct sub_topics: **{len(d.sub_topic_totals)}**")
    if d.taxonomy_path:
        L.append(f"- _taxonomy.yaml: {d.taxonomy_bytes} bytes")
    if d.thresholds_path:
        L.append(f"- thresholds.yaml: {d.thresholds_bytes} bytes")
    L.append("")

    L.append("## Per-file")
    L.append("")
    for fd in d.file_digests:
        L.append(f"### {fd.name}")
        L.append("")
        L.append(f"- rows: **{fd.rows}**  (deprecated={fd.deprecated}, "
                 f"cold={fd.cold_patterns})")
        L.append(f"- status: {_fmt_counter(fd.status_counts)}")
        if fd.sub_topics:
            top_sub = ", ".join(
                f"{k}={v}" for k, v in fd.sub_topics.most_common(8)
            )
            tail = ""
            if len(fd.sub_topics) > 8:
                tail = f" (+{len(fd.sub_topics) - 8} more)"
            L.append(f"- sub_topics top-8: {top_sub}{tail}")
        L.append(f"- example/negative/xling totals: "
                 f"{fd.n_examples_total} / {fd.n_negatives_total} / "
                 f"{fd.n_xling_total}")
        L.append(f"- avg priority: {fd.avg_priority:.1f}")
        if fd.last_history_ts:
            L.append(f"- last lifecycle event: {fd.last_history_ts}")
        L.append("")

    L.append("## Sub-topic saturation (top 12)")
    L.append("")
    for st, n in d.sub_topic_totals.most_common(12):
        L.append(f"- `{st}` : {n}")
    L.append("")

    L.append("## Recent lifecycle events")
    L.append("")
    if not d.recent_events:
        L.append("- (no history records found)")
    for ts, pid, event, actor in d.recent_events:
        L.append(f"- {ts} `{pid}` {event} ({actor})")
    L.append("")

    return "\n".join(L)


def build_digest(library_dir: Path, *, release_line: str | None = None) -> str:
    return render_digest(
        digest_library(library_dir), release_line=release_line,
    )
