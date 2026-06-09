# Agent Shared Operating Notes

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

Codex startup is wired through repo-local hooks:

- `.codex/config.toml` enables `hooks`
- `.codex/hooks.json` runs `.codex/hooks/session_start_secretary.py`
- the hook reads this file and `docs/current/HANDOFF.md`, then runs
  `python -m addons.secretary version` and `python -m addons.secretary list`

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

Generate the minimal handoff packet for another local agent with:

```bash
python -m addons.secretary handoff --next-agent-packet
```

Add task-specific files explicitly when useful:

```bash
python -m addons.secretary handoff --next-agent-packet \
  --include-file docs/current/MMV_FRONTIER_CHAT_TRIAL_PACK_RC3_3_L0V8_4.md \
  --include-file docs/current/MMV_FRONTIER_CHAT_TRIAL_PACK_RC3_3_L0V8_4.sources.json
```

The packet answers:

- What is canonical
- What is happening now
- What the next AI should read, in order
