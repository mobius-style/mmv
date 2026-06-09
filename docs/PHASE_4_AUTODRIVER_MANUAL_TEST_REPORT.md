# Phase 4 Autodriver — Manual Setup Test Report

**Date**: 2026-04-28
**Tester**: Claude Code (Opus 4.7 1M-context, outer conversation)
**Result**: **PASS** — all success criteria met. Cron-eligible.

## Test design

Per the user's request, manually invoke `scripts/phase4_autodriver.sh` once
to verify the actual `claude -p` CLI invocation chain works end-to-end. This
is the gate before scheduling cron.

Success criteria (all required):

| # | Criterion | Result |
|---|---|---|
| 1 | claude -p exits cleanly (or graceful exit) | ✓ exit code 0 |
| 2 | New commits land on main branch | ✓ +6 commits |
| 3 | Phase 3 stab baseline preserved | ✓ 33-scen 31/33 |
| 4 | State file is valid JSON | ✓ |
| 5 | AUTODRIVER_TRIGGER_START/END markers in new handover doc | ✓ both present |

## Pre-flight (00:43:00 UTC)

| Check | Value |
|---|---|
| HEAD | `7d1d1af` (autodriver infra commit) |
| Active patterns | 125 |
| Quarantined | 26 |
| GPU slot 1 | 75 MiB / 0% util (idle) |
| GPU slot 2 | 15 MiB / 0% util (idle) |
| `claude --version` | 2.1.117 |
| `claude` path | `$HOME/.local/bin/claude` |
| `.phase4_autodriver.lock` | exists (0-byte flock target, fine) |
| state file | initialised, head=e4c8c4a, active=125 (caught up to handover) |
| handover doc | `docs/PATTERN_LIBRARY_PHASE4_M1_BATCHES_4_9_HANDOVER.md` |

## Manual invocation

```bash
cd ~/デスクトップ/mobius_ai/MOBIUS_MMV/
./scripts/phase4_autodriver.sh
```

Note: `./scripts/phase4_autodriver.sh run` initially failed with exit 2
(`unknown arg: run`). Fixed in the same session — wrapper now accepts
`run`, `--run`, `--dry-run`, `--status`, `--enable`, `--disable=REASON`,
`-h/--help`. Default mode is no-arg.

## Wrapper progression (from `.phase4_autodriver.log`)

```
00:43:11Z trigger extracted: 114 lines from PATTERN_LIBRARY_PHASE4_M1_BATCHES_4_9_HANDOVER.md
00:43:11Z invoke: claude -p (budget=$15, timeout=21600s)
01:39:35Z claude exit 0 (ok); inv_log=.phase4_autodriver_invoke_20260428T004311Z.log
01:39:35Z post: new handover detected: PATTERN_LIBRARY_PHASE4_M1_BATCHES_10_13_HANDOVER.md
01:39:35Z tick complete (exit=0)
```

**Inner conversation duration**: 56 minutes 24 seconds.

**Process tree confirmed during run**:

```
phase4_autodriver.sh (PID 2251589)
└── timeout 21600 claude -p ... (PID 2251623)
    └── claude -p --permission-mode bypassPermissions ... (PID 2251624)
```

`-p text` mode buffered output until the assistant's user-facing text
emitted near completion. Initial silence in the invoke log was
expected (~30 minutes of internal tool calls produced no text events).

## Inner conversation outcomes

The inner claude continued Phase 4 M1 retry from the handover state and
landed 6 commits across 4 batches plus 1 fix plus 1 handover doc:

```
1fb9b04  chore(phase4): handover doc for batches 10-13 (HEAD b21faed, 138 active)
b21faed  feat(pattern_lib): M1 retry batch 13 — 2 patterns; ce_mobius_core + co_frame saturated
ffab142  fix(pattern_lib): consolidate batch 12 patterns into conceptual_explain.jsonl
65298dd  feat(pattern_lib): M1 retry batch 12 — 4 patterns via 1-spec/sub-topic Priority 3 expansion
1921238  feat(pattern_lib): M1 retry batch 11 — 4 patterns via 1-spec/sub-topic Priority 2 expansion
165483b  feat(pattern_lib): M1 retry batch 10 — 3 patterns via 1-spec/sub-topic yield-up strategy
```

| Item | Pre | Post | Δ |
|---|---|---|---|
| HEAD | `7d1d1af` | `b21faed` (+ `1fb9b04` handover) | +6 commits |
| Active patterns | 125 | 138 | +13 |
| Quarantined | 26 | 26 | 0 |
| FAISS vectors | 1,128 | 1,242 | +114 |
| Golden 200 | 88.5% (177/200) | 88.5% (177/200) | stable, all topics ≥ 85% |
| 33-scen | 31/33 | 31/33 | = Phase 3 stab baseline |
| Tokens cumul Groq | ~390K | ~510K | +120K (0.78% → 1.02% of 50M ST1) |
| Combined batch yield | — | 13/18 = 72.2% | within healthy 50-80% band |

**Strategic findings the inner conversation captured** (per its handover):

1. *Novel-axis > sub-topic-emptiness for yield* — batch 12 (Priority 3
   sub-topics with novel discriminating axes: boundary, complexity,
   geology, redirection) hit 100% yield vs batch 10 (Priority 1 1-2
   pattern sub-topics) at 60%. Counter-intuitive but consistent with the
   batch-9 1-spec/sub-topic finding from the prior conversation.
2. *Cross-sub-topic saturation pattern* — same-topic, different-sub-topic
   conflict-magnets are now appearing (e.g., co_frame premise_correction
   blocked by co_polite member at 0.936). New failure mode beyond
   within-sub-topic saturation.
3. *Filename mapping bug fixed* (commit `ffab142`) — batch 12 originally
   wrote to a wrong jsonl due to pre-existing rename mapping; consolidated
   into the canonical `${topic}.jsonl`.

## Post-test state file (`.phase4_autodriver_state.json`)

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

`invoke_count=4` reflects: setup --status (1), setup --dry-run (2), the
manual invocation pre-update (3), and post-update (4).

## New handover doc validation

`docs/PATTERN_LIBRARY_PHASE4_M1_BATCHES_10_13_HANDOVER.md`:

- Both `<!-- AUTODRIVER_TRIGGER_START -->` and `<!-- AUTODRIVER_TRIGGER_END -->`
  present — markers preserved.
- `extract-trigger` produces 128 lines of paste-block content.
- `parse-state` returns valid JSON with the expected fields populated
  (head=b21faed, active=138, faiss=1242, tokens=510K, hard_stop=false,
  phase4_closed=false).
- The next autodriver tick can chain off this doc with no additional
  human intervention.

## Anomalies observed (none blocking)

1. *Initial `run` arg rejection*: cosmetic, fixed in this session.
2. *Inner claude `-p text` mode buffers output*: expected behavior;
   produced silence during ~30 min of internal tool work, then ~1500
   bytes of summary at the end. Not a wrapper issue.
3. *Pre-update on dry-run* moves state forward to current handover even
   without invoking claude. Acceptable — it just catches state up to the
   actual handover. First post-test full-run will not double-fire any
   notifications because milestone/threshold dedup is per-state.

## Notifications fired during test

None. Active count (138) is below the first 1k milestone, and tokens
(510K) are below the first 20M threshold. The inner conversation also
did not write any AUTODRIVER_HARD_STOP markers.

## Constitutional Invariants / Phase 3 stab baseline

Preserved per inner conversation's self-audit (golden 200 all topics ≥
85%, 33-scen 31/33 = baseline, identity_leakage = 0). The inner
conversation followed the same surgical-quarantine + threshold-calibration
discipline established in batches 4-9.

## Recommendation

**APPROVED for cron scheduling.**

T can install the cron entry now using the command from the setup report.
Suggested cadence: hourly (matches the user's specification and gives ~24
ticks/day; observed tick duration ~56 min for a single Phase 4
conversation, so successive ticks won't normally overlap, and the flock
gate handles the rare case when they do).

## Cron command (re-articulated for T)

```bash
( crontab -l 2>/dev/null; \
  echo "0 * * * * $HOME/デスクトップ/mobius_ai/MOBIUS_MMV/scripts/phase4_autodriver.sh >> $HOME/デスクトップ/mobius_ai/MOBIUS_MMV/.phase4_autodriver.log 2>&1" \
) | crontab -

crontab -l   # verify
```

To pause without removing the cron entry:

```bash
~/デスクトップ/mobius_ai/MOBIUS_MMV/scripts/phase4_autodriver.sh --disable=manual_pause
# resume:
~/デスクトップ/mobius_ai/MOBIUS_MMV/scripts/phase4_autodriver.sh --enable
```

To remove cron entry: `crontab -e` and delete the line.

## What T should watch for after enabling cron

1. **First couple of ticks**: confirm `.phase4_autodriver.log` shows
   successful `tick complete (exit=0)` lines hourly and HEAD advances.
2. **Milestone notifications**: at 1k/3k/5k/10k active patterns. T
   reviews the latest handover doc on each milestone.
3. **Token threshold notifications**: at 20M/40M/70M Groq tokens. The
   70M crossing auto-disables the wrapper.
4. **Silence as a signal**: if HEAD stops advancing across multiple
   ticks but no notification fires, inspect the inner-invoke logs
   (`.phase4_autodriver_invoke_*.log`) for stuck conversations. The
   wrapper itself does not detect "stuck without progress" — T's role.
5. **OAuth credential expiry**: if claude -p starts failing, refresh
   `claude` auth (the wrapper logs non-zero exit and skips state update,
   so resuming is just re-authenticating).

## Conclusion

The Phase 4 autodriver infrastructure is fully operational. All five
success criteria pass. The system is ready for unattended Phase 4
chaining via cron.
