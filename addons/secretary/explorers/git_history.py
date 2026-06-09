"""Explorer: digest recent git history into a Markdown brief.

Wraps `git log` + `git show --stat` and produces:
  - total commits in range
  - author distribution
  - top-touched files and top-touched directories
  - file-type distribution
  - one-line summaries for the N most recent commits

All reads are local (`git` subprocess). No network.
"""
from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


@dataclass
class CommitSummary:
    sha: str
    short_sha: str
    author: str
    date: str
    subject: str
    touched_files: list[str]
    insertions: int
    deletions: int


def _git(args: Sequence[str], *, cwd: Path) -> str:
    """Run a git command and return stdout. Raises on non-zero exit."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def list_commits(
    *, repo: Path, since: str | None, until: str | None,
    last: int | None, paths: list[str] | None,
) -> list[str]:
    """Return commit SHAs in the requested range, newest first."""
    args = ["log", "--pretty=format:%H"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    if last:
        args.append(f"-n{last}")
    if paths:
        args.append("--")
        args.extend(paths)
    out = _git(args, cwd=repo)
    return [s for s in out.splitlines() if s.strip()]


def describe(sha: str, *, repo: Path) -> CommitSummary:
    fmt = "%H%x09%h%x09%an%x09%aI%x09%s"
    header = _git(["show", "--no-patch", f"--format={fmt}", sha], cwd=repo).strip()
    parts = header.split("\t", 4)
    h, sh, author, date, subject = parts + [""] * (5 - len(parts))
    stat = _git(["show", "--numstat", "--format=", sha], cwd=repo).splitlines()
    files: list[str] = []
    ins = dels = 0
    for line in stat:
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        a, d, path = cols[0], cols[1], cols[2]
        files.append(path)
        try:
            ins += int(a)
        except ValueError:
            pass
        try:
            dels += int(d)
        except ValueError:
            pass
    return CommitSummary(
        sha=h, short_sha=sh, author=author, date=date,
        subject=subject, touched_files=files,
        insertions=ins, deletions=dels,
    )


@dataclass
class HistoryDigest:
    commits: list[CommitSummary]
    authors: Counter
    files: Counter
    top_dirs: Counter
    extensions: Counter


def aggregate(commits: list[CommitSummary]) -> HistoryDigest:
    authors: Counter = Counter()
    files: Counter = Counter()
    top_dirs: Counter = Counter()
    extensions: Counter = Counter()
    for c in commits:
        authors[c.author] += 1
        for f in c.touched_files:
            files[f] += 1
            top = f.split("/", 1)[0] if "/" in f else f
            top_dirs[top] += 1
            ext = Path(f).suffix or "(no-ext)"
            extensions[ext] += 1
    return HistoryDigest(
        commits=commits,
        authors=authors,
        files=files,
        top_dirs=top_dirs,
        extensions=extensions,
    )


def _fmt(c: Counter, *, top: int = 10) -> str:
    items = c.most_common(top)
    if not items:
        return "(none)"
    return ", ".join(f"{k}={n}" for k, n in items)


def render(
    *, repo: Path, digest: HistoryDigest, range_descr: str,
    release_line: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append("# Git-history digest")
    lines.append("")
    lines.append(f"- repo: `{repo}`")
    lines.append(f"- range: {range_descr}")
    lines.append(f"- generated_at: {now}")
    if release_line:
        lines.append(f"- secretary_release: {release_line}")
    lines.append(f"- commits: {len(digest.commits)}")
    lines.append("")
    if not digest.commits:
        lines.append("(no commits in range)")
        return "\n".join(lines)
    lines.append("## Distributions")
    lines.append("")
    lines.append(f"- authors: {_fmt(digest.authors)}")
    lines.append(f"- top dirs: {_fmt(digest.top_dirs)}")
    lines.append(f"- top files: {_fmt(digest.files, top=15)}")
    lines.append(f"- file types: {_fmt(digest.extensions)}")
    lines.append("")
    lines.append("## Commits (newest first)")
    lines.append("")
    for c in digest.commits:
        lines.append(
            f"- `{c.short_sha}` {c.date[:10]} {c.author} — {c.subject}"
            f"  _(+{c.insertions}/-{c.deletions}, {len(c.touched_files)} files)_"
        )
    lines.append("")
    return "\n".join(lines)


def build_digest(
    *, repo: Path, since: str | None = None, until: str | None = None,
    last: int | None = 20, paths: list[str] | None = None,
    release_line: str | None = None,
) -> str:
    shas = list_commits(
        repo=repo, since=since, until=until, last=last, paths=paths,
    )
    commits = [describe(s, repo=repo) for s in shas]
    digest = aggregate(commits)
    descr = []
    if since:
        descr.append(f"since={since}")
    if until:
        descr.append(f"until={until}")
    if last:
        descr.append(f"last={last}")
    if paths:
        descr.append(f"paths={paths}")
    return render(
        repo=repo, digest=digest,
        range_descr=", ".join(descr) or "default",
        release_line=release_line,
    )
