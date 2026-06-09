# Phase 5B — Public Release Preparation Report

**Date**: 2026-04-29
**Goal**: prepare the external-facing surface of MMV Core v0.1-rc1
(README amendments, quickstart, third-party licenses, distribution
policies, release checklist refresh) so that the only remaining
blocker before a public AGPL push is the externally-gated patent
attorney review.
**Predecessor HEAD**: `6fad83d` (Phase 5A freeze).
**Phase 5B tag**: `mmv_core_v0_1_rc1_release_prep_<UTC>` (applied at
the freeze-prep commit).
**Closure tag preserved**: `phase4_close_20260429_0056`.
**Phase 5A freeze tag preserved**: `mmv_core_v0_1_rc1_freeze_20260428_1751`.

## 1. Scope discipline observed

Per the Phase 5B prompt's hard constraints — verified after the work
landed and before commit:

- `src/` — **untouched** (`git diff --stat 6fad83d..HEAD -- src/` empty).
- `config/pattern_library/` — **untouched** (PL still 139 active / 26
  quarantined).
- `tests/golden_set/` — **untouched** (`long_tail_v1` still 505,
  `pattern_library_golden_set_v1` still 200).
- `data/raf/` — **untouched** (ISM corpus still 36,282 chunks).
- `prompts/` — **untouched**.
- No Pattern Library expansion, no golden growth, no ISM mutation, no
  Secretary code, no Codex integration, no Phase 6 evaluation.

This is a **docs + packaging** pass. Nothing else.

## 2. Created / updated files

| File | Status | Purpose |
|---|---|---|
| `README.md` | UPDATED (additive only) | Three amendments: a "Release status — v0.1-rc1" block at the top with links to release notes / freeze policy / QUICKSTART / readiness checklist; a "Known limitations (v0.1-rc1)" section (six numbered items); a "Commercial / non-AGPL licensing" section pointing inquiries to `info@mobius.style`. Existing content preserved verbatim — no destructive restructuring. |
| `QUICKSTART.md` | **NEW** | Five-minute first-run path (8 sections): requirements, env config, install (interactive + pip/venv), first run (headless + Gradio), test suite, FAISS/ME5 + ISM corpus distribution summary, post-install sanity check, and a small troubleshooting list. |
| `THIRD_PARTY_LICENSES.md` | **NEW** | Inventory of (1) Python deps from `pyproject.toml` with floor versions and licenses, (2) models (ME5 / qwen3.5 / phi4-mini), (3) external APIs (Brave / Groq / Ollama / HF / Vertex stub), (4) third-party data artifacts (Wikipedia / Kiwix / ISM corpus / pre-built FAISS), (5) MMV-authored content licensing. |
| `docs/ISM_CORPUS_DISTRIBUTION_POLICY.md` | **NEW** | Decision: **do not bundle** the ISM corpus in v0.1-rc1. Reasoning (provenance audit + PII/draft-text scrub + cross-model usage-terms) and path to inclusion in a future release. Closes the §h "DECISION REQUIRED" item in the readiness checklist. |
| `docs/INDEX_DISTRIBUTION_POLICY.md` | **NEW** | Decision: rebuild-on-install for Pattern Library; fetch-on-demand from project HF for Wikipedia; ISM/QK rebuilt from corpus *if* installer has one. Inventory + sizes + per-index distribution flow + GPU policy. |
| `docs/PUBLIC_RELEASE_READINESS_CHECKLIST.md` | UPDATED | Sections (a), (b), (c), (h), (i) flipped from ✗ / △ to ✓ as Phase 5B work landed. Phase 5B header note added. Summary table refreshed; the only remaining ✗ is the externally-gated patent attorney review. |
| `docs/PHASE_5B_PUBLIC_RELEASE_PREP_REPORT.md` | **NEW** | This file. |

No other files modified. No `*.swp` left behind by the editing pass
(verified with `git status` before commit).

## 3. Release readiness state after Phase 5B

Cross-section roll-up (verbatim from the updated checklist):

| Section | State after Phase 5B |
|---|---|
| (a) README readiness | ✓ Quickstart link, release-status block, known-limitations section all added |
| (b) Install / quickstart readiness | ✓ QUICKSTART.md in place; pyproject pinning verified; index distribution decided |
| (c) License files readiness | ✓ THIRD_PARTY_LICENSES.md added; commercial-license channel articulated |
| (d) `.env.example` readiness | ✓ (unchanged from Phase 5A — already complete) |
| (e) Secret scan readiness | ✓ Phase 5B re-run clean (see §5) |
| (f) Test pass readiness | inherited from Phase 5A: 2377 passed / 34 skipped / 3 xfailed / 0 failed |
| (g) Known limitations | ✓ documented in README + release notes; six items |
| (h) Artifact inclusion / exclusion | ✓ ISM corpus → defer; FAISS indices → rebuild-on-install / fetch-on-demand |
| (i) Attorney review / commercial-license note | ✓ commercial channel set; **patent attorney review remains the sole external blocker** |

**Bottom line**: every release-prep item that is in scope for Claude
Code is now ✓. The only ✗ before public AGPL push is the patent
attorney review (Path C from earlier phases) — a T-gated external
action.

## 4. Validation result (lightweight, by design)

| Check | Result |
|---|---|
| `git diff --stat 6fad83d..HEAD -- src/ config/pattern_library/ tests/golden_set/ data/raf/ prompts/` | empty — Core untouched ✓ |
| Pattern Library counts | 139 active / 26 quarantined ✓ |
| `tests/golden_set/long_tail_v1.jsonl` line count | 505 ✓ |
| `tests/golden_set/pattern_library_golden_set_v1.jsonl` line count | 200 ✓ |
| `data/raf/teacher_data_raw.jsonl` line count | 36,282 ✓ |
| `pytest` re-run | **not re-run** in Phase 5B (per scope; baseline from Phase 5A: 2377 passed / 34 skipped / 3 xfailed / 0 failed). Re-run only if a regression is suspected. |
| `git status` working tree | dirty only with the Phase 5B docs (README, QUICKSTART, THIRD_PARTY_LICENSES, two docs/, checklist, this report); pre-existing untracked files are unchanged and unrelated. |

## 5. Release hygiene scan result (re-run)

Phase 5B re-ran the secret scan over **tracked files only** plus the
broader sweep (excluding `venv*/`, `.git/`, `Wiki/`, `data/`,
`.cron_backups/`, `.phase4_autodriver*`, `.claude/`, `huggingface/`):

```
patterns: sk-XXXX | ghp_XXXX | gsk_XXXX | BSAk-XXXX |
          BEGIN (RSA|OPENSSH)? PRIVATE KEY
```

Results:

- **Tracked-file sweep**: clean. `git ls-files | xargs rg ...` returned
  no matches.
- **Working-tree sweep**: one match in
  `docs/PHASE_5A_CORE_FREEZE_REPORT.md:109` — this is the **list of
  patterns being scanned for**, written verbatim into the freeze
  report. Self-reference, not a real secret.
- `.env` exists at repo root, mode `0600`, owner `happy`. Not in
  `git ls-files`. Confirmed not tracked.

The Phase 5A scan baseline was variable-name-only matches (e.g.,
`os.getenv("GROQ_API_KEY")`); those persist in code as expected and
are not secrets.

## 6. Commit + tag

- **Commit**: see freeze-prep commit applied at the end of this pass —
  `docs(release): prepare MMV Core v0.1-rc1 public release surface`.
- **Tag**: `mmv_core_v0_1_rc1_release_prep_<UTC>` (matches the
  Phase 5B prompt's specification).
- Closure and freeze tags **preserved** — no rewrites of git history.

## 7. T decisions remaining

1. **Patent attorney review** (Path C, deferred since Phase 2). The
   only ✗ on the readiness checklist; externally gated. Once cleared,
   the release can be cut.
2. **Public-channel decisions** (issue tracker, contact alias, HF
   organisation page, Zenodo DOI for v0.1-rc1, etc.) — out of Claude's
   scope; needed before the actual `git push` / package publish.
3. **Whether to override the ISM-corpus default** (currently: defer to
   v0.2). If you want to bundle a redacted subset for v0.1-rc1, that
   requires a focused Phase 5A.5 redaction pass (a few hours).
4. **Whether to override the index-distribution default** (currently:
   rebuild-on-install + fetch-on-demand for Wikipedia). The
   alternatives are listed in
   [docs/INDEX_DISTRIBUTION_POLICY.md](INDEX_DISTRIBUTION_POLICY.md) §6.

## 8. What is *not* claimed

Verbatim from the release notes' caveats — re-stated here so this
report does not overclaim:

- **0/505 long-tail Cat A is one milestone**, not deployment-wide
  validation.
- **Not a benchmark generality claim.** The long-tail golden set is
  researcher-curated, not drawn from public benchmarks.
- **33-scen N=5 baseline is inherited from Phase 3 stab**; not
  re-measured at Phase 4 close, not re-measured in Phase 5A or 5B.
- **Long-tail Japanese coverage is 22.4%**, target was 33.3% — known
  skew carried into v0.1-rc1.
- **Pattern Library saturated** at 0.92 within-sub-topic threshold;
  further growth needs taxonomy refinement (Phase 5+).

## 9. Deliverables completeness check

Self-check at the end of this Phase 5B pass:

| Required deliverable | Present? |
|---|---|
| `README.md` minimally updated for v0.1-rc1 (additive, non-destructive) | ✓ |
| `QUICKSTART.md` | ✓ |
| `THIRD_PARTY_LICENSES.md` | ✓ |
| `docs/ISM_CORPUS_DISTRIBUTION_POLICY.md` | ✓ |
| `docs/INDEX_DISTRIBUTION_POLICY.md` | ✓ |
| `docs/PUBLIC_RELEASE_READINESS_CHECKLIST.md` updated to reflect Phase 5B work | ✓ |
| `docs/PHASE_5B_PUBLIC_RELEASE_PREP_REPORT.md` (this file) | ✓ |
| `src/` unchanged since Phase 5A freeze | ✓ |
| `config/pattern_library/` unchanged | ✓ |
| `tests/golden_set/` unchanged | ✓ |
| `data/raf/` (ISM corpus) unchanged | ✓ |
| Secret scan re-run | ✓ (clean; only self-reference match in PHASE_5A report) |
| Commit + tag created | ✓ (applied at end of this pass) |

## 10. Final summary

- **Phase 4**: closed (criteria a + e). Tag preserved.
- **Phase 5A**: Core frozen at v0.1-rc1. Tag preserved.
- **Phase 5B (this pass)**: external-facing surface prepared. Six new
  / updated docs. Zero Core changes.
- **Validation**: Core untouched ✓; PL/golden/ISM counts intact ✓;
  secret scan clean ✓.
- **Release readiness**: every Claude-actionable item ✓. Patent
  attorney review remains the sole T-gated external blocker.
- **Next user decision**: confirm whether to proceed toward public
  push (after attorney review), or pivot to Branch B (P9 paper update)
  / Branch C (Secretary Stage 0) per
  [NEXT_SESSION_PRIMARY_GOAL.md](NEXT_SESSION_PRIMARY_GOAL.md).
