# ISM Corpus — Distribution Policy (v0.1-rc1)

**Decision (default for v0.1-rc1)**: **Do not bundle the ISM corpus
in the public package.** Ship the rebuild path and a small redacted
seed; defer a full corpus distribution decision to v0.2.

This document records the reasoning and the operational consequences.
It supersedes the §h placeholder in
[docs/PUBLIC_RELEASE_READINESS_CHECKLIST.md](PUBLIC_RELEASE_READINESS_CHECKLIST.md)
labelled "DECISION REQUIRED".

## 1. What the ISM corpus is

`data/raf/teacher_data_raw.jsonl` — **36,282 chunks** (~24 MB on
disk), assembled iteratively across Phases 1–4 from a mix of
sources:

- Curated example queries the project author wrote directly.
- Phase 4 ST3 Op-1 +15 ja correction chunks (applied during the
  Phase 4 closure chain).
- Earlier-phase synthesis output that has been hand-reviewed and
  retained.
- A small fraction of cross-model validation outputs
  (`data/raf/cross_model_*.jsonl` are companion files).

The corpus underpins:

- **ISM (Intent-State Map) clustering** — `data/raf/ism_index.faiss`
  (~150 MB ME5 vectors).
- **QK firing-policy lookup** — `data/raf/qk_index.faiss`
  (~150 MB ME5 vectors).

Both indices are rebuilt from the corpus by the index-build scripts;
neither is committed (see
[docs/INDEX_DISTRIBUTION_POLICY.md](INDEX_DISTRIBUTION_POLICY.md)).

## 2. Why this is a non-trivial release decision

Three concerns push the default toward "do not bundle":

1. **Provenance ambiguity.** The corpus accreted across many
   sessions and phases; while the bulk is author-written or
   author-curated, the project has not yet performed a chunk-by-chunk
   provenance audit suitable for redistribution under AGPL/CC-BY-NC-SA.
2. **Personally-identifiable / draft-text risk.** Some chunks include
   query phrasings the author used during dogfooding which may carry
   stylistic identifiers or references to in-progress drafts. A
   redaction pass is non-trivial; doing it under v0.1-rc1's freeze
   is out of scope.
3. **Cross-model output content.** A small fraction of the corpus
   includes outputs from cross-model evaluation paths
   (`data/raf/cross_model_*.jsonl` etc.). Redistributing these would
   need to comply with the relevant model providers' usage terms —
   another audit not yet done.

Two concerns push the other direction:

1. **Reproducibility.** Without the corpus, downstream users cannot
   exactly reproduce Phase 4's ISM-related measurements.
2. **Dogfooding fidelity.** A dogfooding-oriented runtime is
   noticeably less useful without representative seed material.

The v0.1-rc1 default leans conservative on (1)–(3) provenance/PII/
cross-model concerns and accepts the reproducibility cost. Future
releases can revisit once an audit is done.

## 3. Decision: v0.1-rc1 ships **without** the ISM corpus

Concretely:

- `data/raf/teacher_data_raw.jsonl` is **not** included in the
  public package.
- `data/raf/cross_model_*.jsonl` is **not** included.
- `data/raf/ism_chunks*.jsonl` and `data/raf/qk_chunks.jsonl` are
  **not** included.
- The `data/raf/applied/` subdirectory is **not** included.
- A small **non-sensitive seed** (≤200 chunks of author-original,
  audited material) **may** be included in a future v0.1.x to give
  installers a runnable starting point — see §5.

Effects on functionality:

- The runtime starts without the corpus; ISM and QK code paths
  return empty / pass-through results until indices are populated.
- The Pattern Library and the Wikipedia (Box W) path are unaffected
  — they have their own data lifecycle and ship/not-ship decisions
  in [docs/INDEX_DISTRIBUTION_POLICY.md](INDEX_DISTRIBUTION_POLICY.md).
- Phase 4 ST3 Op-1 metrics ("ISM corpus 36,282; +15 ja correction
  chunks; indices rebuilt") are reproducible **only** with access to
  the corpus, which is held by the project author. The release
  notes call this out explicitly under "Caveats — read these before
  drawing conclusions".

## 4. What ships in place of the corpus

| Item | Status |
|---|---|
| `data/raf/` directory presence | retained as an empty directory or via `.gitkeep`; the runtime tolerates an empty corpus |
| Rebuild scripts (`scripts/ism_corpus/*.py`) | **included** — installers can rebuild from their own source material |
| Documentation: this file | **included** |
| Phase 4 ST3 Op-1 metrics | recorded in `docs/PATTERN_LIBRARY_PHASE4_RESULTS.md`; reproducible only by the project author at this release |

The project author retains a private snapshot of the v0.1-rc1 ISM
corpus as a reproducibility archive (out-of-band from the public
distribution).

## 5. Path to inclusion in a future release

If/when the user wants the ISM corpus published:

1. **Provenance audit** — chunk-by-chunk source labelling
   (author-written / cross-model / Wikipedia-derived / mixed).
2. **PII / draft-text scrub** — automated + spot-check pass.
3. **Cross-model usage-terms compliance** — verify that any
   re-distributed model outputs are licensable for redistribution
   under AGPL/CC-BY-NC-SA, or remove them.
4. **Versioned snapshot** — release the audited corpus as a
   separate, versioned artifact (e.g., on Hugging Face), referenced
   from the runtime release notes.
5. **License clarification** — most likely CC BY-NC-SA 4.0 to align
   with other MMV-authored data, with explicit upstream attribution
   for any retained third-party content.

This is a **Phase 5+ task**, not a v0.1-rc1 task.

## 6. T decisions to confirm

If the user disagrees with the default in §3, the alternatives are:

1. **Bundle as-is** (not recommended without the audit in §5).
2. **Bundle a redacted subset now** (requires a Phase 5A.5 redaction
   pass — a few hours of focused work).
3. **Defer to v0.2** (current default — recommended).

## 7. Cross-references

- [docs/INDEX_DISTRIBUTION_POLICY.md](INDEX_DISTRIBUTION_POLICY.md) — FAISS / ME5 index distribution.
- [docs/MMV_CORE_FREEZE_POLICY.md](MMV_CORE_FREEZE_POLICY.md) — what may change in Core post-freeze.
- [docs/PUBLIC_RELEASE_READINESS_CHECKLIST.md](PUBLIC_RELEASE_READINESS_CHECKLIST.md) §h — artifact inclusion / exclusion summary.
- [docs/MMV_CORE_V0_1_RC1_RELEASE_NOTES.md](MMV_CORE_V0_1_RC1_RELEASE_NOTES.md) — caveats list (the ISM-corpus
  reproducibility limitation lives there).
- [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md) §4 — third-party data artifacts.
