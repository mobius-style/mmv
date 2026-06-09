"""Explorer: digest `docs/*.md` into a small Markdown brief.

docs/ is the second-highest-frequency edit surface in this repo
(54 commits in the last 80). 115+ top-level .md files makes a flat
listing useless. This explorer groups files by topic prefix and pulls
the first heading + first paragraph for each, giving Claude a
single-page map of what reports exist without reading the files.

Schema:
  - one section per topic prefix (CLAUDE_CODE_PHASE_, COMPLETION_REPORT_,
    RC3_, PHASE_4_, SECRETARY_, etc.)
  - per file: title (first H1), summary (first non-heading paragraph),
    bytes, mtime
  - optional: `--recent-days N` filter
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path


_PREFIX_RE = re.compile(r"^([A-Z][A-Z0-9_]+?)(?:_[0-9]|$)")


@dataclass
class DocEntry:
    path: Path
    title: str
    summary: str
    bytes: int
    mtime: float

    @property
    def mtime_iso(self) -> str:
        return datetime.fromtimestamp(
            self.mtime, tz=timezone.utc,
        ).isoformat(timespec="seconds")


def _classify_prefix(name: str) -> str:
    """Group docs by their first uppercase token, trailing digits stripped.

    PHASE_4_FINDINGS.md  → PHASE
    PHASE_5A_CORE.md     → PHASE
    RC3_2_REPORT.md      → RC
    COMPLETION_REPORT.md → COMPLETION
    mmv_proxy_status.md  → OTHER  (lowercase first token)
    """
    stem = name.removesuffix(".md")
    parts = stem.split("_")
    if not parts:
        return "OTHER"
    first = parts[0]
    if not (first and first[0].isalpha() and first[0].isupper()):
        return "OTHER"
    stripped = re.sub(r"\d+$", "", first)
    return stripped or first


def _parse_md(path: Path) -> DocEntry:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    title = ""
    summary = ""
    # First H1
    for line in lines:
        s = line.strip()
        if s.startswith("# "):
            title = s.lstrip("# ").strip()
            break
    # First non-heading, non-empty paragraph after the title.
    in_para: list[str] = []
    seen_title = False
    for line in lines:
        s = line.strip()
        if not s:
            if in_para:
                break
            continue
        if s.startswith("#"):
            seen_title = True
            continue
        if seen_title or title == "":
            in_para.append(s)
            if len(" ".join(in_para)) > 240:
                break
    if in_para:
        summary = " ".join(in_para)
        if len(summary) > 240:
            summary = summary[:237] + "..."
    stat = path.stat()
    return DocEntry(
        path=path,
        title=title or path.name,
        summary=summary,
        bytes=stat.st_size,
        mtime=stat.st_mtime,
    )


def digest_docs(
    docs_dir: Path,
    *,
    recent_days: int | None = None,
    max_per_group: int = 12,
) -> dict[str, list[DocEntry]]:
    if not docs_dir.exists():
        raise FileNotFoundError(f"docs dir not found: {docs_dir}")
    cutoff_ts: float | None = None
    if recent_days is not None:
        cutoff_ts = (
            datetime.now(timezone.utc)
            - timedelta(days=recent_days)
        ).timestamp()

    by_prefix: dict[str, list[DocEntry]] = defaultdict(list)
    for path in sorted(docs_dir.glob("*.md")):
        if cutoff_ts is not None and path.stat().st_mtime < cutoff_ts:
            continue
        entry = _parse_md(path)
        prefix = _classify_prefix(path.name)
        by_prefix[prefix].append(entry)

    # Sort each group by mtime desc, cap.
    for prefix, entries in by_prefix.items():
        entries.sort(key=lambda e: e.mtime, reverse=True)
        by_prefix[prefix] = entries[:max_per_group]
    return dict(by_prefix)


def render_digest(
    docs_dir: Path,
    groups: dict[str, list[DocEntry]],
    *,
    recent_days: int | None,
    release_line: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total = sum(len(es) for es in groups.values())
    L: list[str] = []
    L.append("# Docs digest")
    L.append("")
    L.append(f"- source: `{docs_dir}`")
    L.append(f"- generated_at: {now}")
    if release_line:
        L.append(f"- secretary_release: {release_line}")
    if recent_days is not None:
        L.append(f"- recent_days filter: last {recent_days} days")
    L.append(f"- groups: **{len(groups)}**  · entries shown: **{total}**")
    L.append("")

    # Order groups by max-mtime so the freshest section is on top.
    def latest_mtime(es: list[DocEntry]) -> float:
        return max((e.mtime for e in es), default=0.0)

    for prefix in sorted(groups, key=lambda p: latest_mtime(groups[p]), reverse=True):
        entries = groups[prefix]
        L.append(f"## {prefix}  ({len(entries)})")
        L.append("")
        for e in entries:
            L.append(
                f"- `{e.path.name}`  ({e.bytes} B, mtime={e.mtime_iso})"
            )
            L.append(f"  - **{e.title}**")
            if e.summary:
                L.append(f"  - {e.summary}")
        L.append("")
    return "\n".join(L)


def build_digest(
    docs_dir: Path,
    *,
    recent_days: int | None = None,
    max_per_group: int = 12,
    release_line: str | None = None,
) -> str:
    groups = digest_docs(
        docs_dir, recent_days=recent_days, max_per_group=max_per_group,
    )
    return render_digest(
        docs_dir, groups, recent_days=recent_days, release_line=release_line,
    )
