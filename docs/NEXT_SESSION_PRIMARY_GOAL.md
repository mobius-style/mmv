# Next Session Primary Goal — MMV Core Freeze and Secretary Addon Strategy

**Status as of 2026-04-29 (Phase 5A freeze)**: Phase 4 closed. MMV Core
frozen at v0.1-rc1. Cron autodriver deinstalled. Secretary moved to
addon design. Next session opens at this freeze line.

This file supersedes the previous Phase 3-direction goal note (now
historical; see git log if needed).

## Where we are

- **Phase 4 status**: closed (criteria a + e). Tag
  `phase4_close_20260429_0056`.
- **MMV Core**: frozen for public-release preparation. Anchor commit
  `c94eee4` + Phase 5A freeze tag (applied by the freeze commit).
  Policy in [MMV_CORE_FREEZE_POLICY.md](MMV_CORE_FREEZE_POLICY.md).
- **Pattern Library**: 139 active / 26 quarantined / 1,252 FAISS
  vectors. Saturated at 0.92 within-sub-topic threshold.
- **Long-tail golden**: 505 entries; 0/505 Cat A at thresholds
  0.50–0.85 (single milestone, informational).
- **ISM corpus**: 36,282 chunks (Phase 4 ST3 Op-1 applied).
- **Phase 4 autodriver cron**: **removed** (crontab is empty;
  see Phase 5A freeze report).
- **Secretary**: separated — addon strategy documented in
  [SECRETARY_ADDON_STRATEGY.md](SECRETARY_ADDON_STRATEGY.md). No code.

## Primary goal for the next session

Decide which of the three branches below to enter, then execute *one*
of them in focused scope. Do not attempt all three.

### Branch A — Public release preparation (Phase 5B)

Walk the
[Public Release Readiness Checklist](PUBLIC_RELEASE_READINESS_CHECKLIST.md)
and clear the ✗ items so MMV Core v0.1-rc1 can actually be pushed:

- README amendment for v0.1-rc1 (status, link to release notes).
- `THIRD_PARTY_LICENSES.md`.
- Quickstart.md / install path documented.
- ISM-corpus distribution decision + rebuild script if excluded.
- Commercial-license note in README.
- Final secret scan (lightweight pass already in the freeze report).

All items here fall within the freeze-allowed change classes (docs /
packaging / security cleanup). **No Core code changes** required.

Output: a publishable repo state plus one final dry-run of the
public-release checklist.

### Branch B — P9 paper update with measured Phase 4 results

Take the Phase 4 closure record (criteria a + e, 0/505 Cat A, 139
active patterns, 1.0% token budget consumed) and update the P9 paper
draft with measured rather than projected numbers. Carries a small
risk of overclaim — the freeze report and release notes give the
exact caveat language to reuse verbatim:

- 0/505 Cat A is one milestone, not deployment-wide validation.
- 33-scen N=5 baseline inherited from Phase 3 stab, not re-measured.
- Long-tail golden is researcher-curated, not benchmark-drawn.

Output: a P9 v_next document or amendment that is consistent with the
release-notes caveats. **No Core code changes**.

### Branch C — Secretary Stage 0 (read-only briefs)

Begin the **smallest possible** Stage 0 build per
[SECRETARY_ADDON_STRATEGY.md](SECRETARY_ADDON_STRATEGY.md): a
read-only secretary that emits a brief on demand from logs / docs /
git state. Constraints:

- Lives in `addon/secretary/` (or a new repo). **Not** in `src/`.
- Read-only. No file mutations. No `git commit`. No cron writes.
- Uses MMV Core via its public API (dogfooding) — does not import
  anything from `src/` directly.
- Stage 0 only: no proposal queue, no patch proposals, no autonomous
  actions. Just briefs.

If Branch C is chosen first, T should approve the addon-package layout
before any code lands.

## Decisions for T to make (max 3)

1. **Which branch first?** A / B / C / hold-off.
2. **If A**: ISM corpus inclusion in the public package — include
   (with license check), exclude with rebuild script, or defer to v0.2.
3. **If C**: addon-package location — `addon/secretary/` in this repo,
   sibling directory, or new repo.

## What is explicitly *not* the next goal

- New patterns in Pattern Library (frozen).
- New golden entries beyond rc1 baselines (frozen).
- Long-tail Japanese ratio correction (deferred to Phase 5+).
- Sub-topic taxonomy refinement (deferred to Phase 5+).
- LT-2 deep dive (deferred).
- Codex bidirectional integration (deferred).
- Phase 6 broad-evaluation sweeps (deferred).
- AGPL release publication itself (separate user-gated step,
  not a Claude task).

## Files to read first

In order, when picking up this work:

1. [docs/PHASE_5A_CORE_FREEZE_REPORT.md](PHASE_5A_CORE_FREEZE_REPORT.md)
   — what just happened in Phase 5A.
2. [docs/MMV_CORE_FREEZE_POLICY.md](MMV_CORE_FREEZE_POLICY.md) — the
   binding constraint on what may change in Core.
3. One of:
   - Branch A → [docs/PUBLIC_RELEASE_READINESS_CHECKLIST.md](PUBLIC_RELEASE_READINESS_CHECKLIST.md)
   - Branch B → [docs/PATTERN_LIBRARY_PHASE4_RESULTS.md](PATTERN_LIBRARY_PHASE4_RESULTS.md)
   - Branch C → [docs/SECRETARY_ADDON_STRATEGY.md](SECRETARY_ADDON_STRATEGY.md)
