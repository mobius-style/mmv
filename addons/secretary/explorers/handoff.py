"""Explorer: cross-agent handoff kit.

The default mode is a read-only readiness digest. With explicit install,
the helper writes portable shared-memory files for agent supervisors.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


AGENTS_REL = Path("AGENTS.md")
HANDOFF_REL = Path("docs/current/HANDOFF.md")
DIGESTS_REL = Path("addons/secretary/state/digests")
LOGS_REL = Path("addons/secretary/state/logs")
AUTHORITY_MAP_REL = Path("docs/current/DOCS_AUTHORITY_MAP.md")
TRIAL_PACK_REL = Path("docs/current/MMV_FRONTIER_CHAT_TRIAL_PACK_RC3_3_L0V8_4.md")
TRIAL_SOURCES_REL = Path(
    "docs/current/MMV_FRONTIER_CHAT_TRIAL_PACK_RC3_3_L0V8_4.sources.json"
)

CANONICAL_SOURCE_RELS = [
    AUTHORITY_MAP_REL,
    TRIAL_PACK_REL,
    TRIAL_SOURCES_REL,
]

NEXT_AGENT_READ_ORDER = [
    AGENTS_REL,
    HANDOFF_REL,
    AUTHORITY_MAP_REL,
]

CURRENT_WORK_SUMMARY = (
    "MMV is being prepared as a governance-aware, multi-agent workbench. "
    "Do not treat newest notes as authoritative unless the authority map "
    "says so."
)


AGENTS_TEMPLATE = """# Agent Shared Operating Notes

This file is intentionally vendor-neutral. It is the shared entry point
for Codex, Claude Code, OpenCode-style agents, and other local coding
assistants working in this repository.

## Secretary Addon

Use `addons/secretary/` as the token-offload delegate for read-heavy
surveys before opening many files directly.

Run once at the start of a new agent session:

```bash
python -m addons.secretary version
python -m addons.secretary list
```

Prefer the project virtualenv when available:

```bash
$HOME/デスクトップ/mobius_ai/venv313/bin/python -m addons.secretary version
$HOME/デスクトップ/mobius_ai/venv313/bin/python -m addons.secretary list
```

Reach for the secretary when:

- Reading more than 3 files in a directory to understand its shape
- Surveying recent activity or who-touched-what
- Running repo-wide grep that needs a structural roll-up
- You do not remember available verbs or their permission surface

Skip the secretary for targeted edits, single-line debugging, or tasks
with fewer than 3 files in scope.

Before invoking an unfamiliar verb, inspect its permission surface:

```bash
python -m addons.secretary explain <verb>
```

`review-packet --with-synthesis` may call the configured MMV-Large
provider. Treat the structural digest as ground truth and any synthesis
as a draft.

## Shared Memory

Use these files as cross-agent handoff state:

- `addons/secretary/state/digests/*.md`: generated survey digests
- `addons/secretary/state/logs/*.jsonl`: per-invocation audit logs
- `docs/current/HANDOFF.md`: human-written current work handoff
- `operate-fr-bench/releases/large/current.yaml`: active MMV-Large binding

When handing work to another agent, leave a short note in
`docs/current/HANDOFF.md` with the current task, files touched, latest
digest paths, open decisions, and next safe command.

## Next AI Packet

Generate a minimal handoff packet for another local agent with:

```bash
python -m addons.secretary handoff --next-agent-packet
```

The packet answers:

- What is canonical
- What is happening now
- What the next AI should read, in order
"""


HANDOFF_TEMPLATE = """# Current Handoff

This file is shared memory for local coding agents. Keep it short,
append-friendly, and factual.

## Current Task

- Status: not started
- Owner/session: unset
- Last updated: unset

## Relevant Files

- `AGENTS.md`
- `addons/secretary/state/digests/`
- `addons/secretary/state/logs/`

## Latest Secretary Digests

- None recorded yet.

## Decisions

- Use `addons.secretary` for read-heavy surveys.
- Treat generated synthesis as draft and structural digests as ground truth.
- Give the next AI: `AGENTS.md`, `docs/current/HANDOFF.md`,
  `docs/current/DOCS_AUTHORITY_MAP.md`, task-specific source files, and
  the latest relevant secretary digest.

## Open Questions

- None recorded yet.

## Next Safe Command

```bash
python -m addons.secretary version && python -m addons.secretary list
```
"""


@dataclass
class InstallResult:
    path: Path
    action: str


def _rel_status(root: Path, rel: Path) -> str:
    path = root / rel
    if path.exists():
        size = path.stat().st_size
        return f"present ({size} bytes)"
    return "missing"


def _latest_files(path: Path, *, limit: int = 5) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        (p for p in path.iterdir() if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]


def _status_item(root: Path, rel: Path) -> str:
    return f"- `{rel}`: {_rel_status(root, rel)}"


def _latest_relevant_digest(root: Path) -> Path | None:
    latest = _latest_files(root / DIGESTS_REL, limit=20)
    for path in latest:
        if path.name.startswith("."):
            continue
        return path
    return None


def _render_read_order(root: Path, task_files: list[str] | None = None) -> list[str]:
    lines: list[str] = []
    order = list(NEXT_AGENT_READ_ORDER)
    for idx, rel in enumerate(order, start=1):
        lines.append(f"{idx}. `{rel}`")
    n = len(order) + 1
    if task_files:
        for item in task_files:
            lines.append(f"{n}. `{item}`")
            n += 1
    else:
        lines.append(f"{n}. Task-specific source files")
        n += 1
    latest = _latest_relevant_digest(root)
    if latest is not None:
        lines.append(f"{n}. `{latest.relative_to(root)}`")
    else:
        lines.append(f"{n}. Latest relevant secretary digest, if one exists")
    return lines


def build_digest(root: Path, *, release_line: str | None = None) -> str:
    """Build a concise readiness digest for cross-agent handoff."""
    root = root.resolve()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = [
        "# Handoff digest",
        "",
        f"- root: `{root}`",
        f"- generated_at: {now}",
    ]
    if release_line:
        lines.append(f"- secretary_release: {release_line}")
    lines.extend([
        "",
        "## Shared files",
        "",
        f"- `{AGENTS_REL}`: {_rel_status(root, AGENTS_REL)}",
        f"- `{HANDOFF_REL}`: {_rel_status(root, HANDOFF_REL)}",
        f"- `{DIGESTS_REL}`: {_rel_status(root, DIGESTS_REL)}",
        f"- `{LOGS_REL}`: {_rel_status(root, LOGS_REL)}",
        "",
        "## Latest digests",
        "",
    ])
    latest_digests = _latest_files(root / DIGESTS_REL)
    if latest_digests:
        for path in latest_digests:
            rel = path.relative_to(root)
            lines.append(f"- `{rel}` ({path.stat().st_size} bytes)")
    else:
        lines.append("- None found.")
    lines.extend([
        "",
        "## Latest logs",
        "",
    ])
    latest_logs = _latest_files(root / LOGS_REL)
    if latest_logs:
        for path in latest_logs:
            rel = path.relative_to(root)
            lines.append(f"- `{rel}` ({path.stat().st_size} bytes)")
    else:
        lines.append("- None found.")
    lines.extend([
        "",
        "## Give next AI",
        "",
        "### Canonical sources",
        "",
    ])
    for rel in CANONICAL_SOURCE_RELS:
        lines.append(_status_item(root, rel))
    lines.extend([
        "",
        "### Current work",
        "",
        CURRENT_WORK_SUMMARY,
        "",
        "### Read order",
        "",
        *_render_read_order(root),
        "",
        "## Recommended handoff checklist",
        "",
        "- Record the active task and status.",
        "- Link the latest secretary digest paths.",
        "- List files touched and files intentionally not touched.",
        "- Capture open questions and the next safe command.",
    ])
    return "\n".join(lines) + "\n"


def build_next_agent_packet(
    root: Path,
    *,
    task_files: list[str] | None = None,
    release_line: str | None = None,
) -> str:
    """Build the minimal packet to hand to the next local AI agent."""
    root = root.resolve()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = [
        "# Next AI Handoff Packet",
        "",
        f"- root: `{root}`",
        f"- generated_at: {now}",
    ]
    if release_line:
        lines.append(f"- secretary_release: {release_line}")
    lines.extend([
        "",
        "## What Is Canonical",
        "",
    ])
    for rel in CANONICAL_SOURCE_RELS:
        lines.append(_status_item(root, rel))
    lines.extend([
        "",
        "Canonical means: not the newest note, but the document designated by "
        "`DOCS_AUTHORITY_MAP.md` and supported by the paired sources file.",
        "",
        "## What Is Happening Now",
        "",
        CURRENT_WORK_SUMMARY,
        "",
        "## What To Give The Next AI",
        "",
        "Read in this order:",
        "",
        *_render_read_order(root, task_files=task_files),
        "",
        "## Guardrails",
        "",
        "- Use `addons.secretary` for read-heavy surveys.",
        "- Inspect `addons/secretary/permission_ladder.yaml` or run "
        "`python -m addons.secretary explain <verb>` before unfamiliar verbs.",
        "- Treat structural digests as ground truth and LLM synthesis as draft.",
        "- Do not treat newest files as authoritative unless the authority map "
        "says so.",
    ])
    return "\n".join(lines) + "\n"


def install_common_files(root: Path, *, force: bool = False) -> list[InstallResult]:
    """Install vendor-neutral shared-memory templates.

    Existing files are left untouched unless `force` is true.
    """
    root = root.resolve()
    targets = [
        (root / AGENTS_REL, AGENTS_TEMPLATE),
        (root / HANDOFF_REL, HANDOFF_TEMPLATE),
    ]
    results: list[InstallResult] = []
    for path, text in targets:
        existed = path.exists()
        if existed and not force:
            results.append(InstallResult(path=path, action="skipped_existing"))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        results.append(InstallResult(
            path=path,
            action="overwritten" if existed else "created",
        ))
    return results
