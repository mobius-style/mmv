# Phase 4 Autodriver — Setup Report

## Purpose

Allow Claude Code to chain Phase 4 conversations across multiple cron
ticks until closure, removing the need for T to open new conversations
and paste self-trigger blocks manually.

## Components

| File | Role | Tracked? |
|---|---|---|
| `scripts/phase4_autodriver.sh` | Main wrapper invoked by cron | yes |
| `scripts/phase4_autodriver_helpers.py` | State + handover parsing + threshold logic | yes |
| `scripts/phase4_autodriver_notify.sh` | notify-send + log fan-out (replaceable) | yes |
| `.phase4_autodriver_state.json` | Runtime state (HEAD, active count, milestones notified, disabled flag) | gitignored |
| `.phase4_autodriver.lock` | flock target — mutual exclusion across cron ticks | gitignored |
| `.phase4_autodriver.log` | All wrapper events + notification log | gitignored |
| `.phase4_autodriver_invoke_<UTC>.log` | Per-invocation claude stdout/stderr dump | gitignored |

Each handover doc must contain the explicit markers:

```
<!-- AUTODRIVER_TRIGGER_START -->
... self-trigger paste-block contents ...
<!-- AUTODRIVER_TRIGGER_END -->
```

The active handover doc
(`docs/PATTERN_LIBRARY_PHASE4_M1_BATCHES_4_9_HANDOVER.md`) was
retrofitted with these markers as part of this setup.

## Wrapper modes

| Command | Effect |
|---|---|
| `phase4_autodriver.sh` | Full run — pre-checks, extract trigger, invoke claude, post-update state |
| `phase4_autodriver.sh --dry-run` | Show plan (handover, trigger size, invocation, state) without invoking claude |
| `phase4_autodriver.sh --status` | Print state JSON |
| `phase4_autodriver.sh --enable` | Clear `state.disabled` |
| `phase4_autodriver.sh --disable=REASON` | Set `state.disabled=true` with reason |

## Runtime gates (in order, conservative)

1. **flock(.phase4_autodriver.lock, non-blocking)** — overlapping ticks skip cleanly
2. **state.disabled** — manual or marker-driven halt
3. **state.phase4_closed** — closure flag from prior handover
4. **GPU slot 2 (GPU index 1) busy check** — skip if memory ≥ 6GB AND utilization ≥ 30%
   (Ollama serving on slot 2 is OK; an active Phase 4 embedding pipeline on
   slot 2 would trip this and skip the tick)
5. **Pre-update state from current handover** — catches AUTODRIVER markers
   added by the prior conversation. If a marker flips state.disabled, abort
   before invoking claude.

## HARD STOP detection (machine-readable markers)

The wrapper recognizes only explicit markers in handover docs — discussion
of "hard stop" or "system down" in prose does not trigger:

| Marker | Trigger |
|---|---|
| `AUTODRIVER_HARD_STOP: <reason>` | sets `state.disabled=true` + critical notification |
| `AUTODRIVER_SYSTEMIC_BROKEN_COUNT: N` (N ≥ 3) | ditto |
| `AUTODRIVER_PHASE4_CLOSED` | sets `state.disabled=true` + closure notification |

Token budget thresholds are evaluated at every state update:

| Cumulative Groq tokens | Action |
|---|---|
| crossing 20M | normal notification (continue) |
| crossing 40M | normal notification (continue) |
| crossing 70M | critical notification + auto-disable |

## Milestone notifications

Active-pattern crossings of `1000 / 3000 / 5000 / 10000` fire a normal-urgency
notification. Each milestone fires only once (deduped by
`state.milestones_notified`).

## Notification mechanism

`scripts/phase4_autodriver_notify.sh` is the single point for delivering
notifications. It fires `notify-send` (with explicit
`DBUS_SESSION_BUS_ADDRESS=/run/user/UID/bus` for cron compatibility) and
appends a timestamped line to `.phase4_autodriver.log`.

To switch to email/Slack/Discord, replace the body of this script.
The wrapper does not depend on notify-send specifically.

Notification urgency ladder:
- `low`: routine info (currently unused)
- `normal`: milestone crossed, token threshold crossed (continue)
- `critical`: HARD STOP, closure, claude timeout/exit-non-zero,
  no handover doc found

## Manual setup test (2026-04-28) — PASS

End-to-end manual invocation succeeded; see
[PHASE_4_AUTODRIVER_MANUAL_TEST_REPORT.md](PHASE_4_AUTODRIVER_MANUAL_TEST_REPORT.md)
for the full record. Highlights:

- `claude -p` exit code: 0 (after 56:24 wall clock)
- New commits: 6 (batches 10-13 + 1 fix + 1 handover doc)
- HEAD: `7d1d1af` → `1fb9b04` (handover) on top of `b21faed`
- Active patterns: 125 → 138 (+13 net)
- Phase 3 stab baseline preserved (33-scen 31/33)
- Golden 200 stable at 88.5% (all topics ≥ 85%)
- New handover has valid AUTODRIVER markers; chainable as-is
- No notifications fired (below first milestone/threshold)
- State file valid JSON, `invoke_count=4`, `disabled=false`

**Cron is now eligible.** T may run the cron-install command (below) at
their discretion.

## Pre-cron setup tests (2026-04-28, isolated)

| Test | Result |
|---|---|
| `chmod +x` on wrapper, helpers.py, notify.sh | ✓ |
| `--status` initialised state file from defaults | ✓ |
| `--dry-run` extracted 114-line trigger from current handover | ✓ |
| `--dry-run` updated state to HEAD `e4c8c4a`, active=125 | ✓ |
| Direct `phase4_autodriver_notify.sh` fired notify-send + log line | ✓ (notify-send exit 0) |
| `--disable=test_setup_verify` flipped state, default-mode skipped, log noted | ✓ |
| `--enable` cleared state.disabled | ✓ |
| Synthetic handover with `active: 1500` + `tokens_cumul ~22M` triggered MILESTONE 1000 + TOKEN THRESHOLD 20M | ✓ |
| Synthetic handover with `AUTODRIVER_HARD_STOP:` marker auto-disabled | ✓ |
| State reset and confirmed clean post-tests (HEAD e4c8c4a, active 125) | ✓ |

What was **not** tested in the pre-cron isolated harness (intentional):
the actual `claude -p` invocation. That has now been validated in the
"Manual setup test" section above (2026-04-28, PASS).

## Manual setup test (T runs this once before scheduling cron)

```bash
cd ~/デスクトップ/mobius_ai/MOBIUS_MMV/

# Inspect plan without invoking claude
./scripts/phase4_autodriver.sh --dry-run

# Verify state file is sane
./scripts/phase4_autodriver.sh --status

# Real invocation (one tick). Watch the per-invocation log live.
./scripts/phase4_autodriver.sh
```

Expected on success:
- A new handover doc is committed (HEAD advances)
- `.phase4_autodriver.log` shows `tick complete (exit=0)`
- `--status` shows updated `last_handover`, `head`, `active`, `tokens_cumul`,
  and `invoke_count` incremented

If claude exits non-zero or times out, inspect
`.phase4_autodriver_invoke_<UTC>.log` and decide whether to retry or
escalate (auth issue, OAuth token expired, etc.).

## Cron command (T runs to enable scheduling)

The cron job is **not** auto-installed. T runs this manually after the
setup test passes:

```bash
( crontab -l 2>/dev/null; echo "0 * * * * $HOME/デスクトップ/mobius_ai/MOBIUS_MMV/scripts/phase4_autodriver.sh >> $HOME/デスクトップ/mobius_ai/MOBIUS_MMV/.phase4_autodriver.log 2>&1" ) | crontab -
crontab -l
```

To stop: remove that line from `crontab -e`. Or use the disable switch
without removing the cron entry:
```bash
./scripts/phase4_autodriver.sh --disable=manual_pause
# resume:
./scripts/phase4_autodriver.sh --enable
```

## Environment overrides (optional)

```bash
PHASE4_AUTODRIVER_BUDGET=20         # USD cap per conversation (default 15)
PHASE4_AUTODRIVER_TIMEOUT=10800     # seconds before SIGTERM (default 21600 = 6h)
CLAUDE_BIN=/path/to/claude          # if claude is not on PATH
```

These are read each tick — change them in the cron line as needed.

## Hard constraints honored

- **Phase 4 v2.1 prompt is the source of truth** for what each conversation
  does. The wrapper only delivers the self-trigger + waits for the
  handover-doc contract; it does not alter Phase 4 protocol.
- **Constitutional Invariants / existing fixes** preserved — the inner
  conversation runs the same `phase4_seed_driver.py` + golden + 33-scen
  validation pipeline that batches 4-9 used.
- **GPU electrical saturation rule** — GPU slot 2 idle gate before
  starting work. CPU FAISS rebuild is the established fallback when
  Ollama occupies GPU0/1.
- **M1 retry self-audit protocol** unchanged — surgical quarantine,
  threshold calibration discipline, golden 200 ≥ 85% per-topic gate.

## T's intended review windows (per user's request)

- **At each milestone crossing** (1k / 3k / 5k / 10k patterns):
  T receives a normal notification, opens the latest handover doc,
  reviews the recent commits and stats, and may pause via `--disable`
  if anomalies are spotted.
- **At each token threshold** (20M / 40M / 70M Groq tokens):
  T notification, same review opportunity.
- **At HARD STOP / Phase 4 CLOSED**:
  T notification, autodriver auto-disables, T resumes manually after
  resolution.

The cron-scheduled hourly cadence balances throughput against T's
chance to detect things the inner conversation's self-audit missed
(M1 incident-style violations).

## Known limitations / future improvements

- **OAuth credential expiry**: claude CLI's `.credentials.json` has a
  finite lifetime. If a tick fails because the token expired, the
  wrapper logs the non-zero exit and skips updating state. T should
  re-authenticate (`claude login` or equivalent) and the next tick will
  resume.
- **No automatic retry on transient claude errors**: by design — the
  next cron tick is the retry. If a real failure persists across
  several ticks, the handover doc won't advance and milestone
  notifications won't fire (silence is itself a signal).
- **Notification on Phase 4 CLOSED is best-effort**: the wrapper
  detects the marker but does not generate the closure report itself.
  The conversation that detects closure is responsible for writing
  `docs/NEXT_SESSION_PRIMARY_GOAL.md`, the Evolution Log entry, and
  the closure report (per Phase 4 v2.1 prompt §STEP 7).
- **One repo at a time**: the wrapper hardcodes the repo path via its
  own location. Multi-repo autodriver would need a config file.
- **Stuck conversation detection**: a 6h timeout (default) is the
  upper bound. If a conversation gets stuck at lower than 6h but past
  reasonable progress, T must notice via the handover doc not
  advancing across multiple ticks (no new commits, milestone
  silence).

## Escalation points (per user's "困難な点があれば articulate")

1. **claude CLI auth path in cron**: confirmed `.credentials.json`
   exists and `--print` mode without `--bare` reads it. End-to-end
   test still pending T's manual setup test before cron scheduling.

2. **DBUS/notify-send in cron**: confirmed `/run/user/1000/bus`
   socket present and `XDG_RUNTIME_DIR` set. notify-send fired during
   setup test. Cron-launched ticks should also work because the wrapper
   exports the bus address explicitly.

3. **GPU race**: addressed via flock + slot 2 busy check. The
   conservative skip is intentional — false skips are harmless
   (next tick retries), false invocations could cause electrical
   saturation per HARD CONSTRAINT 5.

4. **State drift**: if the state file is deleted, the next tick
   re-derives state from the latest handover doc — milestones
   already passed will fire notifications again the first time
   after deletion. Acceptable.
