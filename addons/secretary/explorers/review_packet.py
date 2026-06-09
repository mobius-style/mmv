"""Explorer: digest the MMV-Large human-review packet into a small Markdown brief.

Input: a directory laid out like
`operate-fr-bench/reports/human_review_packet_mmv_large_rc3_3/`:

  - `rc3_3_summary.md`            (narrative)
  - `ambiguous_time_audit.csv`    (full-row audit; ~6 rows)
  - `query_neutrality_audit.csv`  (full-row audit; ~11 rows)
  - `stale_premise_audit.csv`     (full-row audit; ~16 rows)
  - `volatile_current_audit.csv`  (full-row audit; ~36 rows)
  - `smoke100_review_targets.csv` (priority targets; ~58 rows)

Output: a Markdown digest at the requested path. The point is to compress
~120 CSV rows + the narrative summary into a structure Claude can read in
a single page, while keeping deterministic counts so the human-review
loop can verify nothing was silently smoothed over.

No LLM call by default — the win here is in the structural compression
itself. A future flag (`--with-synthesis`) will optionally pass this
digest through MMV Large for narrative synthesis.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


AUDIT_FILES = (
    "ambiguous_time_audit.csv",
    "query_neutrality_audit.csv",
    "stale_premise_audit.csv",
    "volatile_current_audit.csv",
)
PRIORITY_FILE = "smoke100_review_targets.csv"
SUMMARY_FILE = "rc3_3_summary.md"


@dataclass
class AuditDigest:
    name: str
    rows: int
    families: Counter
    languages: Counter
    rc3_route_distribution: Counter
    raw_route_distribution: Counter
    rc3_correct: int
    rc3_incorrect: int
    raw_vs_rc3_changed: int
    review_priority: Counter
    failure_task_ids: list[str]


@dataclass
class PriorityDigest:
    rows: int
    priority: Counter
    by_priority_family: dict[str, Counter]
    flags: Counter
    high_priority_ids: list[tuple[str, str, str]]  # (task_id, family, prompt)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


def _bool(s: str) -> bool | None:
    s = (s or "").strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


def digest_audit(path: Path) -> AuditDigest:
    rows = _read_csv(path)
    families: Counter = Counter()
    languages: Counter = Counter()
    rc3_routes: Counter = Counter()
    raw_routes: Counter = Counter()
    priorities: Counter = Counter()
    rc3_correct = 0
    rc3_incorrect = 0
    raw_vs_rc3_changed = 0
    failure_ids: list[str] = []
    for r in rows:
        families[r.get("family", "")] += 1
        languages[r.get("language", "")] += 1
        rc3_routes[r.get("rc3_3_route", "")] += 1
        raw_routes[r.get("raw_route", "")] += 1
        priorities[r.get("review_priority", "")] += 1
        c = _bool(r.get("rc3_3_correct", ""))
        if c is True:
            rc3_correct += 1
        elif c is False:
            rc3_incorrect += 1
            failure_ids.append(r.get("task_id", "?"))
        if _bool(r.get("raw_vs_rc3_3_changed", "")) is True:
            raw_vs_rc3_changed += 1
    return AuditDigest(
        name=path.stem,
        rows=len(rows),
        families=families,
        languages=languages,
        rc3_route_distribution=rc3_routes,
        raw_route_distribution=raw_routes,
        rc3_correct=rc3_correct,
        rc3_incorrect=rc3_incorrect,
        raw_vs_rc3_changed=raw_vs_rc3_changed,
        review_priority=priorities,
        failure_task_ids=failure_ids,
    )


def digest_priority(path: Path) -> PriorityDigest:
    rows = _read_csv(path)
    priority: Counter = Counter()
    by_pf: dict[str, Counter] = defaultdict(Counter)
    flags: Counter = Counter()
    high: list[tuple[str, str, str]] = []
    for r in rows:
        prio = r.get("review_priority", "")
        fam = r.get("family", "")
        priority[prio] += 1
        by_pf[prio][fam] += 1
        for fl in (r.get("flags") or "").split("|"):
            fl = fl.strip()
            if fl:
                flags[fl] += 1
        if prio == "HIGH":
            high.append((r.get("task_id", "?"), fam, r.get("prompt", "")))
    return PriorityDigest(
        rows=len(rows),
        priority=priority,
        by_priority_family=dict(by_pf),
        flags=flags,
        high_priority_ids=high,
    )


def _fmt_counter(c: Counter, *, total: int | None = None) -> str:
    if not c:
        return "(none)"
    parts = []
    for key, n in c.most_common():
        if total:
            parts.append(f"{key or '∅'}={n} ({n / total:.0%})")
        else:
            parts.append(f"{key or '∅'}={n}")
    return ", ".join(parts)


def render_digest(
    *,
    packet_dir: Path,
    audits: list[AuditDigest],
    priority: PriorityDigest | None,
    summary_md: str | None,
    release_line: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append(f"# Review-packet digest")
    lines.append("")
    lines.append(f"- source: `{packet_dir}`")
    lines.append(f"- generated_at: {now}")
    if release_line:
        lines.append(f"- secretary_release: {release_line}")
    lines.append("")

    if priority is not None:
        lines.append("## Priority targets (smoke100)")
        lines.append("")
        lines.append(f"- total rows: **{priority.rows}**")
        lines.append(
            f"- review_priority: {_fmt_counter(priority.priority, total=priority.rows)}"
        )
        lines.append(f"- flags: {_fmt_counter(priority.flags)}")
        for prio in ("HIGH", "MEDIUM", "LOW"):
            fams = priority.by_priority_family.get(prio)
            if fams:
                lines.append(f"- {prio} by family: {_fmt_counter(fams)}")
        if priority.high_priority_ids:
            lines.append("")
            lines.append("### HIGH priority items")
            lines.append("")
            for task_id, fam, prompt in priority.high_priority_ids:
                prompt_short = prompt[:120].replace("\n", " ")
                lines.append(f"- `{task_id}` [{fam}] {prompt_short}")
        lines.append("")

    if audits:
        lines.append("## Per-family audits")
        lines.append("")
        for a in audits:
            lines.append(f"### {a.name}")
            lines.append("")
            lines.append(f"- rows: **{a.rows}**")
            lines.append(
                f"- rc3_3 correct/incorrect: {a.rc3_correct} / {a.rc3_incorrect}"
            )
            lines.append(f"- raw_vs_rc3_3 route changed: {a.raw_vs_rc3_changed}")
            lines.append(f"- languages: {_fmt_counter(a.languages)}")
            lines.append(f"- rc3_3 routes: {_fmt_counter(a.rc3_route_distribution)}")
            lines.append(f"- raw routes: {_fmt_counter(a.raw_route_distribution)}")
            lines.append(f"- review_priority: {_fmt_counter(a.review_priority)}")
            if a.failure_task_ids:
                lines.append(
                    f"- rc3_3 failures: {', '.join('`'+i+'`' for i in a.failure_task_ids)}"
                )
            lines.append("")

    if summary_md is not None:
        lines.append("## Packet summary (verbatim)")
        lines.append("")
        lines.append(summary_md.rstrip())
        lines.append("")

    return "\n".join(lines)


def build_synthesis_prompt(digest_md: str) -> str:
    """Build the synthesis prompt sent to MMV Large.

    The digest is already a compact summary of the packet. We ask the
    governed Large model for a short, structured second-pass synthesis
    focused on what a reviewer should *act on next*. The prompt is
    deliberately short (the digest itself does most of the work) so the
    Large call stays cheap.
    """
    return (
        "You are reviewing a structural digest of a human-review packet for "
        "the MMV-Large RC3.3 evaluation. Produce a short Markdown synthesis "
        "with these three sections, in this exact order, no preamble:\n"
        "\n"
        "## Top 3 priorities\n"
        "Three bullet points naming the most actionable failure clusters "
        "or systematic effects, each with a one-sentence rationale.\n"
        "\n"
        "## Risks to flag\n"
        "Bullet points covering: classifier reward vs user benefit; any "
        "cohort where RC3.3 changed routes systematically; date_bound "
        "hedge quality.\n"
        "\n"
        "## What to ignore\n"
        "Bullet points: items that look low-value to dig into and why.\n"
        "\n"
        "Be specific: cite task_ids and family names from the digest. "
        "Do not invent numbers. Do not repeat content from the verbatim "
        "summary section.\n"
        "\n"
        "Digest:\n"
        "---\n"
        f"{digest_md}\n"
        "---\n"
    )


def build_digest(packet_dir: Path, *, release_line: str | None = None) -> str:
    """Compose the full digest. Missing optional files are tolerated; the
    digest reports what it found."""
    if not packet_dir.exists():
        raise FileNotFoundError(f"packet dir not found: {packet_dir}")

    audits: list[AuditDigest] = []
    for name in AUDIT_FILES:
        p = packet_dir / name
        if p.exists():
            audits.append(digest_audit(p))

    priority_path = packet_dir / PRIORITY_FILE
    priority = digest_priority(priority_path) if priority_path.exists() else None

    summary_path = packet_dir / SUMMARY_FILE
    summary_md = summary_path.read_text(encoding="utf-8") if summary_path.exists() else None

    return render_digest(
        packet_dir=packet_dir,
        audits=audits,
        priority=priority,
        summary_md=summary_md,
        release_line=release_line,
    )
