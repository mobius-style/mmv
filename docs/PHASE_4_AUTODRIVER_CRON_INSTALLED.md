# Phase 4 Autodriver — Cron Installation Log

**Installed**: 2026-04-28 10:59:05 JST (01:59:05 UTC)
**Installed by**: Claude Code (this session)
**HEAD at install time**: `d259e4d` (test report commit; manual setup test PASS)

## Pre-conditions

- Manual setup test PASS recorded in
  [PHASE_4_AUTODRIVER_MANUAL_TEST_REPORT.md](PHASE_4_AUTODRIVER_MANUAL_TEST_REPORT.md)
  (HEAD `7d1d1af` → `b21faed`/`1fb9b04`, +6 commits, 125 → 138 active patterns,
  Phase 3 stab baseline preserved, 5/5 success criteria).
- Wrapper accepts run/--run/--dry-run/--status/--enable/--disable=REASON.
- State file valid (head=b21faed, active=138, invoke_count=4, disabled=false).

## Steps performed

### 1. Existing crontab backup

```bash
crontab -l 2>&1
# stdout: "no crontab for happy" (exit 1 — no prior crontab)
```

Backup file (records the empty pre-state for future audits):

```
.cron_backups/crontab_pre_phase4_autodriver_20260428_105905.txt
```

Contents: `# (no prior crontab — fresh install)`.

### 2. Install entry

```bash
( crontab -l 2>/dev/null; \
  echo "0 * * * * $HOME/デスクトップ/mobius_ai/MOBIUS_MMV/scripts/phase4_autodriver.sh >> $HOME/デスクトップ/mobius_ai/MOBIUS_MMV/.phase4_autodriver.log 2>&1" \
) | crontab -
# exit 0
```

### 3. Verify

```bash
$ crontab -l
0 * * * * $HOME/デスクトップ/mobius_ai/MOBIUS_MMV/scripts/phase4_autodriver.sh >> $HOME/デスクトップ/mobius_ai/MOBIUS_MMV/.phase4_autodriver.log 2>&1
```

cron service status: `active` and `enabled` (systemd).

### 4. Next firing time

| | |
|---|---|
| Install time (local) | 2026-04-28 10:59:15 JST |
| Install time (UTC)   | 2026-04-28 01:59:15 UTC |
| **Next firing (local)** | **2026-04-28 11:00:00 JST** |
| **Next firing (UTC)**   | **2026-04-28 02:00:00 UTC** |
| Cadence              | hourly on the hour (`0 * * * *`) |
| Recurrence cap       | none (cron runs until removed/disabled) |

## State at install (entering autonomous operation)

```json
{
  "schema_version": 1,
  "disabled": false,
  "disabled_reason": null,
  "last_invoke_utc": "2026-04-28T01:39:35.932134Z",
  "last_handover": ".../PATTERN_LIBRARY_PHASE4_M1_BATCHES_10_13_HANDOVER.md",
  "head": "b21faed",
  "active": 138,
  "quarantined": 26,
  "faiss_vectors": 1242,
  "tokens_cumul": 510000,
  "milestones_notified": [],
  "token_thresholds_notified_m": [],
  "invoke_count": 4,
  "phase4_closed": false
}
```

## What happens at each cron tick

1. `phase4_autodriver.sh` acquires flock — overlapping ticks skip cleanly.
2. Reads `.phase4_autodriver_state.json` — skips if `disabled=true` or
   `phase4_closed=true`.
3. GPU slot 2 busy-gate (≥6GB AND ≥30% util on GPU index 1 → skip).
4. Locates the latest handover doc in `docs/`.
5. Pre-update state from that doc (catches `AUTODRIVER_HARD_STOP:` /
   `AUTODRIVER_PHASE4_CLOSED` / `AUTODRIVER_SYSTEMIC_BROKEN_COUNT:`
   markers added by the previous conversation).
6. Extracts the paste-block between `<!-- AUTODRIVER_TRIGGER_START/END -->`.
7. Invokes:
   ```
   claude -p \
     --permission-mode bypassPermissions \
     --add-dir <repo> \
     --max-budget-usd 15 \
     --no-session-persistence \
     --output-format text \
     < <trigger-file>
   ```
   with `timeout 21600` (6h SIGTERM).
8. After exit, post-update state from the (possibly newer) handover doc.
   Notifications fire for milestones / token thresholds / hard stops.
9. Logs `tick complete (exit=N)` to `.phase4_autodriver.log`.

## T intervention contract

The user's expressed contract for autonomous mode:

| Event | Mechanism | T action |
|---|---|---|
| Active patterns crosses 1k / 3k / 5k / 10k | normal `notify-send` | review latest handover doc (no required action) |
| Tokens cumul crosses 20M / 40M Groq | normal `notify-send` | continue (informational) |
| Tokens cumul crosses 70M Groq | critical `notify-send` + auto-disable | review + decide whether to re-enable |
| `AUTODRIVER_HARD_STOP:` marker added by inner conversation | critical `notify-send` + auto-disable | diagnose + re-enable when resolved |
| `AUTODRIVER_PHASE4_CLOSED` marker added | critical `notify-send` + auto-disable | celebrate, then write closure follow-up (Evolution Log entry, NEXT_SESSION_PRIMARY_GOAL.md per Phase 4 v2.1 §STEP 7) |
| Manual pause | `bash scripts/phase4_autodriver.sh --disable=manual_pause` | run when needed |
| Manual resume | `bash scripts/phase4_autodriver.sh --enable` | run when ready |
| Inspect current state | `bash scripts/phase4_autodriver.sh --status` | always available |
| Remove cron entry | `crontab -e` and delete the line | when done permanently |

## What to watch in `.phase4_autodriver.log`

Each tick adds a few lines. Healthy pattern:

```
<UTC> trigger extracted: <N> lines from <handover>
<UTC> invoke: claude -p (budget=$15, timeout=21600s)
<UTC> claude exit 0 (ok); inv_log=<inv_log>
<UTC> post: new handover detected: <new_handover>
<UTC> tick complete (exit=0)
```

Unhealthy patterns (T should investigate):

- `skip:` lines for many consecutive ticks → wrapper is blocked
  (disabled flag, phase4_closed, GPU slot 2 busy, or stuck flock).
- `claude exit <non-0>` → inspect the matching `inv_log`.
- `claude killed by timeout after 21600s` → conversation hung; tick log
  shows critical notification.
- `post: no new handover doc` for many ticks → inner conversations are
  not progressing. HEAD won't advance — silence is itself a signal.

## Closure handoff (when Phase 4 closes)

The inner conversation that detects closure is responsible for:

1. Writing `docs/NEXT_SESSION_PRIMARY_GOAL.md` (Phase 5 entry point per
   Phase 4 v2.1 §STEP 7).
2. Appending Evolution Log entry 26 (Phase 4 closure record).
3. Writing the closure report doc.
4. Adding `AUTODRIVER_PHASE4_CLOSED` marker to its handover doc — this
   triggers the autodriver to auto-disable on the next tick and notify T.

The wrapper does NOT generate any of these artifacts — it only delivers
the self-trigger and observes the markers.

## How to remove cron when done

```bash
crontab -e
# delete the line beginning with "0 * * * * $HOME/デスクトップ/mobius_ai/MOBIUS_MMV/scripts/phase4_autodriver.sh"
# save + exit
crontab -l   # confirm removed
```

Or, to fully clear:

```bash
crontab -r   # removes ENTIRE crontab — fine here since it was empty before
```

## Files referenced

| Path | Role |
|---|---|
| `scripts/phase4_autodriver.sh` | wrapper (cron target) |
| `scripts/phase4_autodriver_helpers.py` | state mgmt + handover parsing |
| `scripts/phase4_autodriver_notify.sh` | notify-send + log fan-out |
| `.phase4_autodriver_state.json` | runtime state (gitignored) |
| `.phase4_autodriver.lock` | flock target (gitignored) |
| `.phase4_autodriver.log` | per-tick wrapper log (gitignored) |
| `.phase4_autodriver_invoke_<UTC>.log` | per-invocation claude stdout (gitignored) |
| `.cron_backups/crontab_pre_phase4_autodriver_<UTC>.txt` | pre-install crontab snapshot |
| `docs/PHASE_4_AUTODRIVER_SETUP_REPORT.md` | infra design + isolated tests |
| `docs/PHASE_4_AUTODRIVER_MANUAL_TEST_REPORT.md` | end-to-end manual run record |
| `docs/PHASE_4_AUTODRIVER_CRON_INSTALLED.md` | this file |

## Status

**Phase 4 autodriver is ACTIVE.** Next tick at 11:00:00 JST will pick up
the existing handover (`PATTERN_LIBRARY_PHASE4_M1_BATCHES_10_13_HANDOVER.md`,
HEAD `b21faed`, 138 active patterns) and continue the M1 retry chain.
