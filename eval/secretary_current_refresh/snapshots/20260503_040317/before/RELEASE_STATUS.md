---
doc_status: current
authority: canonical
scope: rc3_release
last_verified_utc: 2026-05-02
current_release_candidate_tag: mmv_core_v0_1_rc3_release_candidate_20260430_2336
current_release_candidate_commit: 7f53fe1dbdf189f014b0cd2643a996148fc5dba7
supersedes:
  - docs/RC3_RELEASE_READINESS_FINAL_CHECK.md  # evidence; not current authority
  - docs/MMV_CORE_V0_1_RC1_RELEASE_NOTES.md     # rc1 historical
  - docs/PHASE_5B_PUBLIC_RELEASE_PREP_REPORT.md # rc1 historical
  - any rc1 / rc2 readiness or status notes
do_not_treat_older_release_notes_as_current: true
---

# MMV Core — current release status

This file is the **canonical answer** to "what is the current release
candidate?" Every other document in the repo is either evidence,
historical, or superseded relative to this file. If anything in this
file disagrees with live `git` state, live `git` wins; if anything in
older docs disagrees with this file, this file wins.

## Current release candidate

| Field | Value |
|---|---|
| Tag | `mmv_core_v0_1_rc3_release_candidate_20260430_2336` |
| Commit | `7f53fe1dbdf189f014b0cd2643a996148fc5dba7` |
| Branch from which tag was cut | `coverage-repair-alpha-beta` |
| Status | technical release candidate. **T-gated external items remain.** Not yet published. |

## Current technical blockers

**None known** as of `last_verified_utc`. Specifically:

- The M-1 micro-fix that added 29 previously-untracked `src/` files
  was applied and committed before the RC3 tag. Import integrity is
  intact at the RC3 commit.
- The RC3 readiness audit and module-integrity audit both completed.
- All 20+ RC3 unit tests pass at the tag commit. Stage 0-A through
  0-F regression smokes (33/33 in Stage 0-D, 33/33 in Stage 0-C,
  20/20 in Stage 0-A) all pass against this state.
- Stage 0-F integrated OpenCode as a read-only frontend without
  changing any Core source.

## Current T-gated decisions

These are external decisions only T can clear. They are **not**
technical blockers — the build is technically ready — they are
release-window approvals.

1. **Patent attorney review (Path C).** Required for AGPL public
   distribution. No internal remedy; T must obtain a legal opinion.
2. **Public push / release channel.** Whether and where to publish
   (GitHub public, Zenodo, Hugging Face, all/none) is a T decision.
3. **Untracked artefacts policy.** ~150 working-tree paths
   (tests/, scripts/, eval/, docs/, prompts/, corpus/) are
   untracked. Recommended deferral to v0.2 unless T explicitly
   wants a tracking sweep before RC3 publication. Detail in
   [`eval/secretary_stage0c/t_decision_brief_untracked_files.md`](../../eval/secretary_stage0c/t_decision_brief_untracked_files.md).
4. **RC3 release notes / version-label cosmetics.** If T wants
   visible version strings (`pyproject.toml`, `THIRD_PARTY_LICENSES.md`
   header, etc.) updated to "v0.1-rc3" before the publish step,
   this is a small T-call. See
   [`docs/current/SETUP_GAPS.md`](SETUP_GAPS.md).

## Current warnings

- **Untracked tests / scripts / docs / eval artefacts** exist in the
  working tree (~150 paths). They are NOT release blockers under
  the recommended Option B (defer to v0.2). They WOULD become a
  blocker only if T chooses Option A (track-everything) and the
  in-repo tarball must be byte-reproducible from the RC3 tag.
- **Standard benchmarks (Phase 5N–5P)** are subset / bridge
  measurements (n ≤ 50 mostly), not leaderboard claims. The bench
  panel reports document this explicitly.
- **OpenCode integration is optional.** It is a Stage 0-F addition
  for the operator's convenience as a read-only chat frontend. The
  Secretary Python CLI remains the audit-grade brief generator and
  is the canonical tool for release-window briefs.

## Resolved / stale items (older reports may still mention these)

- ✓ **RC3 release-candidate tag has already been created.** The
  exact tag is named in this file's front matter. **Do NOT create
  another RC3 tag**; do NOT cut a new one with a different timestamp.
- ✓ **Old RC3 tags are historical artifacts.** Specifically:
  - `mmv_core_v0_1_rc3_ux_polish_20260430_1827` (UX polish snapshot)
  - `mmv_core_v0_1_rc3_project_log_review_preset_20260430_1922`
    (preset snapshot)

  These exist for git history but are **not** release artefacts
  and must not be used for public push.
- ✓ **rc1 release notes are not current.** `docs/MMV_CORE_V0_1_RC1_RELEASE_NOTES.md`
  predates RC3 and predates the Phase 5* / Stage 0-* additions.
  Read it as evidence about what was true at rc1, not as a status.
- ✓ **rc1-era public-release readiness checklists** (e.g. earlier
  `PUBLIC_RELEASE_READINESS_CHECKLIST.md` if it still says rc1)
  must not be quoted as the current candidate.
- ✓ **Phase 4 module audit "open items"** were closed at Phase 4
  closure (commit `c94eee4`, tag `phase4_close_20260429_0056`)
  before RC3 was cut.

## What NOT to do now

- **Do not create another RC3 tag** unless T explicitly decides
  the current one needs to be re-cut for some specific reason
  recorded here.
- **Do not use the old RC3 tags** (ux_polish, project_log_review_preset)
  for any release artefact assembly.
- **Do not treat rc1 release notes as current.** If you find
  yourself writing "the candidate is v0.1-rc1", you have read the
  wrong document.
- **Do not public-push** until the four T-gated decisions above
  are individually cleared.
- **Do not edit MMV Core source files** (src/, tests/, data/,
  prompts/) for cosmetic version labels. Cosmetic updates belong
  in `pyproject.toml`-style metadata and release-notes wording,
  not in runtime code.

## Provenance

- This file is hand-maintained by the operator (T) and Secretary
  Stage 0-G. It is updated when the canonical release candidate
  changes.
- Live git authority: `git rev-list -n 1
  mmv_core_v0_1_rc3_release_candidate_20260430_2336` →
  `7f53fe1dbdf189f014b0cd2643a996148fc5dba7`. Anyone reading this
  file should sanity-check the tag→commit mapping with that command
  before relying on the values above.
