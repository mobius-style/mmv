---
doc_status: current
authority: canonical
scope: public_release_readiness
last_verified_utc: 2026-05-03
overall_verdict: YELLOW (technically ready; T-gated external items remain)
current_release_candidate_tag: mmv_core_v0_1_rc3_release_candidate_20260430_2336
current_release_candidate_commit: 7f53fe1dbdf189f014b0cd2643a996148fc5dba7
---

# Public release readiness — current

This file answers two questions:

1. Is the project technically ready to be public-pushed?
2. If not, what is the operator (T) waiting on?

## Headline

**Verdict: YELLOW.** The candidate is technically ready — there are
no known runtime / build / test / import blockers — but four
T-gated external items remain (see below). Public push is gated on
T's decision on each.

## Technical readiness checklist

| Item | Status |
|---|---|
| Import integrity (M-1 micro-fix landed) | ✓ |
| Unit tests pass at the RC3 commit | ✓ |
| Stage 0-A through 0-F regression smokes | ✓ (each stage's smoke battery green) |
| Pattern Library / Golden set / ISM corpus stable | ✓ (Stage 0-A through 0-F made zero changes to these) |
| FAISS / ME5 / Wiki indexes built | ✓ (no rebuild needed for RC3) |
| Secret scan (`.env`, `*.pem`, `*.key`, `secrets/`, `credentials/`) | ✓ (Stage 0-D Python explorer + Stage 0-F OpenCode plan agent both honour blacklists) |
| Forbidden-pattern scan in repo | ✓ (every Stage 0-* report regex-scans for `gsk_…`, `sk-…`, `Bearer …`, `*_API_KEY=…`; 0 matches found in any stage's outputs) |
| Backup + clean-package staging | ✓ (Phase 5 backup commit referenced in MMV_BACKUPS) |
| Release tarball assembly script working | n/a in Stage 0-G (no assembly attempted; technical readiness, not packaging) |

No remaining technical blockers known.

## T-gated items remaining (NOT technical blockers)

| # | Item | Where the decision lives |
|---|---|---|
| 1 | Patent attorney review (Path C) — required for AGPL public distribution | T external; reference in older `PATENT_ATTORNEY_REVIEW_PHASE2.md` plus Secretary briefs |
| 2 | RC3 release notes / version-label cosmetic polish | `docs/current/SETUP_GAPS.md` |
| 3 | Push channel order — GitHub / Zenodo / Hugging Face / mirror — and whether any are skipped | T external |
| 4 | Optional tracking sweep of ~150 untracked working-tree paths (tests/, scripts/, eval/, docs/, prompts/, corpus/) — recommended **defer to v0.2** | `eval/secretary_stage0c/t_decision_brief_untracked_files.md` |

These are **release-window approvals**, not engineering work. The
build itself does not change while these are open.

## What "READY" would look like

When all four items above are cleared by T, this file's
`overall_verdict:` line in the front matter would change to GREEN
and the public push could proceed. T should update this file (and
`docs/current/RELEASE_STATUS.md`) at the moment of clearance.

## What NOT to overclaim

- Do not claim "deployment-wide validation". MMV-Eval v0.1 (Phase
  5M, n=373) is the primary empirical evidence; Phase 5N–5P are
  bridge measurements (n ≤ 50). None of these is a Phase 6 / full
  benchmark / production-traffic study.
- Do not claim "MMV beats raw on standard benchmarks". Phase 5O's
  release-brief absolute scores show format-strict tasks lose,
  factual MC stays close, truthfulness preference rises slightly.
  The framing is *failure-profile shift*, not superiority.
- Do not claim the public-release-ready state until the four T-gated
  items above are cleared.

## Out of scope for "ready to public-push"

- Stage 0-G's docs/current authority layer is operator tooling. It
  does NOT need to be in the public release tarball, but committing
  it to the source tree is fine (this stage does so).
- OpenCode integration (Stage 0-F) is operator tooling. The
  installed binary lives in `~/.opencode/`, OUTSIDE the repo, and
  does NOT enter the public release tarball.

## See also

- `docs/current/RELEASE_STATUS.md` — canonical RC pointer + blockers + T-gated list
- `docs/current/DOCS_AUTHORITY_MAP.md` — priority order of all docs
- `docs/current/SETUP_GAPS.md` — cosmetic / setup details
- `docs/RC3_RELEASE_READINESS_FINAL_CHECK.md` — evidence (rc3-cut audit)
- `docs/SECRETARY_STAGE0F_OPENCODE_CONNECTION_REPORT.md` — most recent stage's safety report
