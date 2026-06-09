---
doc_status: current
authority: canonical
scope: documentation_authority_priority
last_verified_utc: 2026-05-16
---

# Documentation authority map

When OpenCode, the Secretary CLI, or any other agent needs to answer
**"what is the current state of the project?"**, it must consult
sources in this priority order. Higher numbers in this file are NOT
higher priority — number 1 is the highest.

## Authority priority (top → bottom)

1. **Live `git` state.** Run `git rev-list -n 1
   mmv_core_v0_1_rc3_release_candidate_20260430_2336`,
   `git rev-parse HEAD`, `git status --porcelain`, `git tag
   --points-at HEAD`. These commands are authoritative for "what
   the repo *is* right now". Older docs cannot override them.
2. **`docs/current/RELEASE_STATUS.md`** — the canonical answer to
   "what is the current release candidate, what blocks it, and
   what is T-gated".
3. **`docs/current/PUBLIC_RELEASE_READINESS.md`** — the canonical
   answer to "is the project ready to push publicly, and what
   T-gated items remain".
4. **`docs/current/SETUP_GAPS.md`** — the canonical answer to
   "what cosmetic / setup gaps still need T's attention before
   public push".
5. **Latest Secretary current-state overlay / brief.** A fresh
   run of `python addons/secretary/run_secretary_brief.py
   --use-explorer --explore-topic "rc3 release readiness"`
   produces a brief whose Appendix A includes the
   current-state overlay (live git facts) and the stale-item
   classification. The brief itself is evidence; the overlay
   block inside it is itself sourced from live git state.
6. **Latest RC3 readiness and module-integrity audits.**
   `docs/RC3_RELEASE_READINESS_FINAL_CHECK.md` and
   `docs/MODULE_INTEGRITY_AUDIT_RC3.md`. Read as **evidence**
   for what was true at the RC3 cut moment. They are NOT
   current authority on their own — they predate the post-RC3
   Stage 0-* work and the canonical docs/current/ files above.
7. **Phase evidence reports** under `docs/PHASE_5*.md` and
   `eval/phase5*/`, plus per-stage Secretary reports under
   `docs/SECRETARY_STAGE0*_*.md`. Cite for specific claims;
   do not treat as current state.
8. **Archived / older release notes and handoff docs.** Anything
   that names rc1 or rc2 as the current candidate is historical
   unless `docs/current/RELEASE_STATUS.md` re-lists it. Older
   readiness checklists are historical unless explicitly carried
   forward here.

## Document classification

### Canonical current docs

| Path | What it answers |
|---|---|
| `docs/current/RELEASE_STATUS.md` | what is the current RC, blockers, T-gated items, resolved/stale items |
| `docs/current/DOCS_AUTHORITY_MAP.md` (this file) | what is the priority of every doc class |
| `docs/current/PUBLIC_RELEASE_READINESS.md` | is the project public-push-ready and what T-gated items remain |
| `docs/current/SETUP_GAPS.md` | what cosmetic / setup gaps remain |

These four files are the only **canonical** docs. Everything else is
evidence or historical.

### Evidence docs (cite, do not override)

| Path | Role |
|---|---|
| `docs/RC3_RELEASE_READINESS_FINAL_CHECK.md` | RC3-cut readiness audit (evidence at rc3 cut moment) |
| `docs/MODULE_INTEGRITY_AUDIT_RC3.md` | RC3-cut module integrity audit |
| `docs/PHASE_5M_FOR_P9_NOTE.md` and `docs/PHASE_5*_*.md` | per-phase findings and reports |
| `docs/SECRETARY_STAGE0A_FEASIBILITY_REPORT.md` … `docs/SECRETARY_STAGE0F_OPENCODE_CONNECTION_REPORT.md` | per-stage Secretary reports |
| `docs/p9_conditional_armored_runtime_v1_2_final_with_phase5o_absolute_scores.md` | P9 v1.2 paper |
| `docs/SECRETARY_STAGE0G_CURRENT_DOCS_AUTHORITY_REPORT.md` (this stage) | this stage's report |
| `eval/secretary_stage0a/` … `eval/secretary_stage0f/` | per-stage smoke artefacts |
| `eval/phase5*/` | per-phase bench artefacts |

### Historical / superseded docs

These exist for `git` history. They MUST NOT be used as the answer
to "what is current".

| Path | Why historical |
|---|---|
| `docs/MMV_CORE_V0_1_RC1_RELEASE_NOTES.md` | rc1 release notes; predates rc3 |
| `docs/PHASE_5B_PUBLIC_RELEASE_PREP_REPORT.md` | rc1-era public-release prep |
| Any older readiness checklist that names rc1 / rc2 as the candidate | superseded |
| Old RC3 tags `mmv_core_v0_1_rc3_ux_polish_20260430_1827`, `mmv_core_v0_1_rc3_project_log_review_preset_20260430_1922` | snapshots, not release artefacts |

### Do NOT use as current state

- rc1 release notes
- rc2-era release notes (none currently in repo, but the rule
  applies)
- Any document that contradicts live `git` state without
  explicitly being re-listed in `docs/current/`

## Conflict-resolution rule

If older documents conflict with live `git` state OR with
`docs/current/`, the older docs are **stale/historical**. Do not
escalate them to current blockers. Stage 0-B's stale-item detector
(`addons/secretary/state/stale_item_detector.py`) automates this
classification for the Secretary CLI; OpenCode and humans should
apply the same rule.

A concrete example from the Stage 0-F smoke:

> Older docs (`PUBLIC_RELEASE_READINESS_CHECKLIST.md`,
> `PATENT_ATTORNEY_REVIEW_PHASE2.md`) name the candidate as **rc1**.
> Live `git tag` and `docs/current/RELEASE_STATUS.md` name it as
> **rc3** (`mmv_core_v0_1_rc3_release_candidate_20260430_2336` →
> `7f53fe1`). Therefore the rc1 wording in those older docs is
> **stale/historical**, NOT a current blocker. Anyone (OpenCode,
> Secretary, T) reading them must classify them accordingly.

## Maintenance

- When RC3 is superseded by a future RC4 (or v0.1.0 final), update
  `docs/current/RELEASE_STATUS.md`'s front matter (`current_release_candidate_tag`,
  `current_release_candidate_commit`, `last_verified_utc`,
  `supersedes:`) BEFORE updating any older doc. Older docs become
  historical at the moment the front matter is updated.
- Do NOT delete older docs. They remain `git`-tracked evidence.
- Do NOT mass-edit older docs to "synchronise" them with current
  state — that creates a second source of truth and re-introduces
  the drift problem this layer was built to solve.
