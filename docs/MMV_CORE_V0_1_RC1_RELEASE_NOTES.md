# MMV Core v0.1-rc1 — Release Notes (Draft)

> Historical note (2026-05-21): this is an rc1-era release-note draft.
> It remains useful evidence for the Phase 5A / Phase 5B state, but it is
> not the current document authority when it conflicts with
> `docs/current/DOCS_AUTHORITY_MAP.md` or the L0 v8.4 documents.

**Status**: Release-candidate / working prototype.
**Date**: 2026-04-29 (Phase 5A freeze).
**Anchor**: Phase 4 closure HEAD `c94eee4` plus `68dc213` autodriver
closure handoff. Freeze tag `mmv_core_v0_1_rc1_freeze_<UTC>`.

This is a draft for review. Publication is gated on the
[Public Release Readiness Checklist](PUBLIC_RELEASE_READINESS_CHECKLIST.md)
and on the user's go-ahead.

---

## What MMV Core is

MMV (Minimum Mobius Viable) Core is a local-first conversational AI
runtime built around **Answer Entitlement Architecture**: a routing /
appraisal / governance layer that decides whether answering is justified
before a response is generated. The Core handles:

- Query appraisal (under-specified, context-dependent, freshness-sensitive,
  safety-relevant detection).
- A Pattern Library that recognises canonical request shapes across five
  topics (self-reference, conceptual_explain, factual_inquiry,
  correction, casual_engagement) at sub-topic granularity.
- ME5 cross-lingual (English / Japanese / Chinese) embedding-based
  pattern lookup at FAISS scale.
- Stage 1–4 retrieval pipelines (Local RAG → Kiwix fallback → Brave Web
  Search → Box B Wikipedia ME5 path).
- A Question Kernel catalogue (QK) for synthesis-mode selection.
- L0 Protocol v8.2 governance prompt as the system-prompt baseline.

It runs on a single local box with `qwen3.5:9b` via Ollama as the
reference inference backend. CPU is sufficient for ME5 embeddings; FAISS
index work prefers a single GPU slot.

## What this release includes

- `src/` runtime — kernel, adapters, memory, retrieval, services, app.
- `prompts/l0_integrated_v8_2.md` (canonical L0 Protocol v8.2) +
  historical `v8_1`.
- `config/pattern_library/` — 5 topic JSONLs + taxonomy + thresholds.
- `tests/` — full suite plus golden sets (200-entry
  `pattern_library_golden_set_v1.jsonl`, 505-entry `long_tail_v1.jsonl`).
- Phase 4 closure documentation
  (`docs/PATTERN_LIBRARY_PHASE4_RESULTS.md`,
  `docs/PHASE_4_FINDINGS_FOR_SPEC_v1_5.md`).
- This freeze package (`docs/MMV_CORE_FREEZE_POLICY.md`,
  `docs/PUBLIC_RELEASE_READINESS_CHECKLIST.md`,
  `docs/SECRETARY_ADDON_STRATEGY.md`, this file,
  `docs/PHASE_5A_CORE_FREEZE_REPORT.md`).

Excluded from the public package (see release readiness §h):

- Pre-built FAISS indices (large; rebuild on install).
- Wikipedia / Kiwix data (third-party).
- ISM corpus distribution model is not yet decided.
- Local secret material (`.env`, `~/.claude/`, etc.).
- Secretary addon (separate package; see addon strategy doc).

## Phase 4 empirical summary

Phase 4 completed on closure criteria **(a) ST1 diminishing returns**
AND **(e) spec v1.4.1 informational-pass framework — all primary metrics
✓ or INFO**.

| Surface | Measurement |
|---|---|
| Phase 4 status | **closed** |
| Closure criteria triggered | (a) AND (e) |
| Long-tail golden size (`long_tail_v1`) | **505** entries |
| Long-tail Cat A rate | **0/505** at thresholds 0.50–0.85 (single I-1 milestone; informational on stability) |
| Pattern Library active patterns | **139** (5 topics, ~30 sub-topics) |
| Pattern Library quarantined | **26** (audit trail preserved) |
| Pattern Library FAISS vectors | 1,252 |
| ISM corpus | **36,282** chunks (Phase 4 ST3 Op-1 +15 ja correction chunks, indices rebuilt) |
| `WITHIN_SUBTOPIC_STRICT` threshold | 0.92 (calibrated) |
| Phase 4 token consumption | ~1.0% of 80M Groq ceiling |
| `pattern_library_golden_set_v1` (200 entries) | 88.5% (177/200), all 6 topics ≥ 85% |

Phase 4 spent **~1% of its declared token budget**. The closure was not
budget-driven; it was driven by the diminishing-returns signal at the
0.92 within-sub-topic saturation point and by the fact that all primary
metrics passed (or attained informational-pass) under spec v1.4.1.

## Caveats — read these before drawing conclusions

1. **0/505 Cat A is one milestone, not deployment-wide validation.** It
   is a single point measurement on a researcher-curated long-tail
   surface (`tests/golden_set/long_tail_v1.jsonl`). Phase 4 closure
   criterion (b) requires *two* long-tail milestones for strict
   stability; this rc1 ships with informational-pass via criterion (a).
2. **Not a benchmark generality claim.** The long-tail golden set is
   constructed; it is not drawn from public benchmarks (TriviaQA,
   MMLU, KILT, etc.). Cross-benchmark generality is unmeasured at rc1.
3. **33-scenario harness baseline is N=5 mean 30.40 inherited from
   Phase 3 stab.** It was *not* re-measured at Phase 4 close. A
   lightweight smoke can be inferred from the freeze-line validation
   record but does not constitute statistical re-baseline.
4. **Long-tail Japanese ratio is 22.4% vs target 33.3%.** Carried
   forward as a Phase 5 candidate. rc1 ships with this skew known.
5. **Pattern Library ST1 saturated** around 4-of-5 sub-topics at the
   0.92 threshold during Phase 4 b14. Library growth past this point
   requires sub-topic taxonomy refinement (Phase 5).
6. **ME5 / FAISS indices** are large, gitignored, and not yet packaged
   for distribution. First-run rebuild path is not yet documented in
   a Quickstart.
7. **Patent attorney review remains DEFERRED** (Path C from earlier
   phases). Public push on AGPL is gated on the user resolving this
   externally.

## Intended audience

- **Small-LLM researchers** evaluating open governance layers for
  ≤10B-parameter models running locally.
- **Local-first AI developers** who want to keep inference on their
  own hardware and need a routing/appraisal substrate.
- **Runtime governance engineers** interested in
  Answer-Entitlement-style design patterns at the routing tier.
- **Edge / non-GPU AI experimenters** working with CPU-side ME5 and
  modest-size FAISS.

This is **not** for production-deployment teams looking for an
SLA-backed component, nor for benchmark-leaderboard chasing.

## Status

**Release candidate / working prototype.** No production-deployment
guarantees. Bug reports and ergonomic feedback welcome via the
project's issue channel (channel TBD before public push).

The next gate is the
[Public Release Readiness Checklist](PUBLIC_RELEASE_READINESS_CHECKLIST.md).
When the ✗ items there clear, MMV Core v0.1-rc1 is ready for public
publication.

## What ships in v0.2 / Phase 5+ (not in rc1)

Not in this release; see [SECRETARY_ADDON_STRATEGY.md](SECRETARY_ADDON_STRATEGY.md)
and the freeze report's "Deferred" section:

- Secretary autonomy layer (built as an addon, not Core).
- Codex bidirectional integration.
- Sub-topic taxonomy refinement; further Pattern Library growth.
- Long-tail golden set expansion to a second milestone (criterion (b)
  strict stability).
- Long-tail Japanese ratio correction.
- Spec v1.5 formal file (findings already recorded in
  `docs/PHASE_4_FINDINGS_FOR_SPEC_v1_5.md`).
- Phase 6 broad-evaluation sweeps.
- Commercial-license channel and trademark policy.
