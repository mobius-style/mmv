"""Explorer: structured grep — hit counts, file distribution, samples.

Wraps `grep -rIn` (or ripgrep if available). For a given pattern + paths
constraint, produces:

  - total hit count
  - top N files by hit count
  - top dirs by hit count
  - sample lines from the top files

Designed to save Claude from reading raw grep output, which can run to
thousands of lines when the pattern is common.
"""
from __future__ import annotations

import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SAMPLES_PER_FILE = 3
TOP_FILES = 15


@dataclass
class Hit:
    path: str
    line_no: int
    line: str


def _have_rg() -> bool:
    return shutil.which("rg") is not None


def run_grep(
    pattern: str, *, paths: list[str] | None, repo: Path,
    ignore_case: bool = False, max_hits: int = 2000,
) -> list[Hit]:
    """Run ripgrep if available, else falls back to GNU grep -rIn."""
    targets = paths or ["."]
    if _have_rg():
        cmd = ["rg", "-n", "--no-heading", "--max-count", "500"]
        if ignore_case:
            cmd.append("-i")
        cmd.extend([pattern, *targets])
    else:
        cmd = ["grep", "-rIn"]
        if ignore_case:
            cmd.append("-i")
        cmd.extend([pattern, *targets])
    try:
        result = subprocess.run(
            cmd, cwd=str(repo),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            check=False,  # 1 means "no match", not an error
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            f"grep tool not found: {e}. Install ripgrep (`rg`) or GNU grep."
        ) from e
    hits: list[Hit] = []
    for line in result.stdout.splitlines():
        # Format: <path>:<lineno>:<text>
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        path, no, text = parts
        try:
            no_i = int(no)
        except ValueError:
            continue
        hits.append(Hit(path=path, line_no=no_i, line=text))
        if len(hits) >= max_hits:
            break
    return hits


@dataclass
class GrepDigest:
    pattern: str
    paths: list[str]
    total: int
    by_file: Counter
    by_dir: Counter
    samples: dict[str, list[Hit]]  # top file → first N hits


def aggregate(hits: list[Hit], pattern: str, paths: list[str]) -> GrepDigest:
    by_file: Counter = Counter()
    by_dir: Counter = Counter()
    file_hits: dict[str, list[Hit]] = {}
    for h in hits:
        by_file[h.path] += 1
        d = h.path.rsplit("/", 1)[0] if "/" in h.path else "."
        by_dir[d] += 1
        file_hits.setdefault(h.path, []).append(h)
    samples: dict[str, list[Hit]] = {}
    for f, _ in by_file.most_common(TOP_FILES):
        samples[f] = file_hits[f][:SAMPLES_PER_FILE]
    return GrepDigest(
        pattern=pattern, paths=paths,
        total=len(hits), by_file=by_file, by_dir=by_dir,
        samples=samples,
    )


def render(digest: GrepDigest, *, release_line: str | None = None) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append("# Repo-grep digest")
    lines.append("")
    lines.append(f"- pattern: `{digest.pattern}`")
    lines.append(f"- paths: {digest.paths or ['.']}")
    lines.append(f"- generated_at: {now}")
    if release_line:
        lines.append(f"- secretary_release: {release_line}")
    lines.append(f"- total hits: {digest.total}")
    lines.append(f"- files matched: {len(digest.by_file)}")
    lines.append("")
    if digest.by_dir:
        lines.append("## Top dirs")
        lines.append("")
        for d, n in digest.by_dir.most_common(10):
            lines.append(f"- `{d}/`: {n}")
        lines.append("")
    if digest.by_file:
        lines.append(f"## Top files (up to {TOP_FILES})")
        lines.append("")
        for f, n in digest.by_file.most_common(TOP_FILES):
            lines.append(f"- `{f}`: {n} hits")
            for h in digest.samples.get(f, []):
                trimmed = h.line[:160].replace("\n", " ")
                lines.append(f"    - L{h.line_no}: `{trimmed}`")
        lines.append("")
    return "\n".join(lines)


def build_digest(
    pattern: str, *, paths: list[str] | None = None,
    repo: Path, ignore_case: bool = False,
    release_line: str | None = None,
) -> str:
    hits = run_grep(pattern, paths=paths, repo=repo, ignore_case=ignore_case)
    digest = aggregate(hits, pattern, paths or [])
    return render(digest, release_line=release_line)
