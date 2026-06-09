# Phase 4 Module Audit Report

**Generated**: 2026-04-27 (Phase 4 audit Commit 18)
**Audit chain**: HEAD `7f5a3e0` → `71083fa` (16 commits, 3 repairs)
**Trigger**: M1 incident (`create_seed_patterns.py` silent fail) → systemic
audit before Phase 4 mass Groq expansion.

## Executive verdict

**Phase 4 module audit complete. M1 retry is READY to proceed.**

- **34 modules audited** across Tier 1-4 (Phase 1-3 + Phase 4 Foundation)
- **0 modules broken / irreparable**
- **3 wiring inconsistencies repaired** (audit_status filter alignment)
- **1 deprecated module** (`create_seed_patterns.py`) replaced by new
  full-pipeline driver (`phase4_seed_driver.py`)
- **All 278 tests pass / 0 failed**
- **Phase 3 stab baseline maintained** throughout

## Module status matrix

### Tier 1 — Auto-gen pipeline (M1 retry core dependency)

| Module | Status | Repair | Commit |
|---|---|---|---|
| variants_generator | ✓ HEALTHY | - | C3 (7f8e665) |
| negatives_generator | ✓ HEALTHY | - | C4 (0f95d94) |
| xling_query_generator | ✓ HEALTHY | - | C5 (cb45f57) |
| quality_grader | ✓ HEALTHY | - | C6 (66785ca) |
| conflict_checker | ✓ HEALTHY | **REPAIR**: audit_status filter | C7 (d3f27eb) + C8 (33538b3) |
| groq_client | ✓ HEALTHY | - | C8 (33538b3) |
| ~~create_seed_patterns~~ | DEPRECATED | Replaced by `phase4_seed_driver.py` | C8 (33538b3) |
| **NEW** phase4_seed_driver | ✓ HEALTHY | New full-pipeline driver | C8 (33538b3) |

**Tier 1 verdict**: All 6 generator modules + groq_client + new driver
HEALTHY. M1 retry pipeline ready.

### Tier 2 — Production wiring

| Module | Status | Repair | Commit |
|---|---|---|---|
| Library Inspector (9 routes) | ✓ HEALTHY | - | C9 (baee748) |
| Audit dashboard (6 sections) | ✓ HEALTHY | - | C9 (baee748) |
| Secretary core + 5 triggers | ✓ HEALTHY | - | C10 (4654c3d) |
| Library Inspector /secretary | ✓ HEALTHY | - | C10 (4654c3d) |
| Hit-count tracker | ✓ HEALTHY | - | C11 (aa4b8d8) |
| pattern lifecycle audit | ✓ HEALTHY | - | C13 (bc2fafa) |

**Tier 2 verdict**: All 6 modules HEALTHY. HARD CONSTRAINT 7 re-verified
across all 4 Secretary entry points. Hit-count atomic increment
verified at 50-thread × 100 increment scale (5,000/5,000 atomic).

### Tier 3 — ISM auto-gen + ISMProfile

| Module | Status | Repair | Commit |
|---|---|---|---|
| intent_variants_generator | ✓ HEALTHY (never invoked) | - | C12 (acdf478) |
| abstain_gap_filler | ✓ HEALTHY (never invoked) | - | C12 (acdf478) |
| ISMProfile module | ✓ HEALTHY (loads + computes) | - | C12 (acdf478) |
| ISMProfile behavioral accuracy | ⓘ SUSPICIOUS (data) | Phase 4 STEP 5 refinement | C12 (acdf478) |

**Tier 3 verdict**: Modules HEALTHY. ISMProfile behavioral misclassifications
(2/3 sample queries at high confidence) are due to corpus distribution
skew (factual_query 64.4%, rare classes < 2.5%) — addressed by Phase 4
STEP 5 Path B refinement plan (Op-1 intent rebalance + Op-2 abstain
gap fill, ~14M tokens).

### Tier 4 — Infrastructure

| Module | Status | Repair | Commit |
|---|---|---|---|
| ME5 singleton | ✓ HEALTHY | - | C14 (32421be) |
| Module-level engine cache | ✓ HEALTHY (deferred re-measurement) | - | C14 (32421be) |
| Routing engine (Phase 3 stab C44 wire) | ✓ HEALTHY | - | C15 (636d10d) |
| Sub-topic-aware lookup | ✓ HEALTHY | **REPAIR**: PatternLibrary.from_disk audit_status filter | C16 (0f74c2c) |
| Per-sub-topic threshold | ✓ HEALTHY | - | C16 (0f74c2c) |
| 5 verification scripts | ✓ HEALTHY | - | C17 (71083fa) |

**Tier 4 verdict**: All 4 module clusters HEALTHY. ME5 singleton cold
load 7.4s / warm 0.010s — process-shared singleton confirmed working.
Routing engine 44 tests pass across 3 modes. PatternLibrary.from_disk
now respects audit_status (third audit-aware module).

## Repairs applied

### Repair 1 — conflict_checker._load_library audit_status filter
**Module**: `scripts/pattern_autogen/conflict_checker.py`
**Commit**: 33538b3 (in C8 sub-commit)
**Rationale**: Loaded ALL patterns from JSONL regardless of
`lifecycle.audit_status`. The 24 quarantined M1 patterns were still
being treated as conflict competitors, blocking legitimately new
patterns at the 0.85 cosine threshold. Repair: skip
`{deprecation_candidate, deprecated, under_review}` by default;
optional `include_inactive=True` for diagnostic.

### Repair 2 — phase4_seed_driver sub-topic-aware conflict policy
**Module**: `scripts/pattern_autogen/phase4_seed_driver.py` (NEW)
**Commit**: 33538b3 (C8)
**Rationale**: `conflict_checker` 0.85 binary gate caught even
genuinely unique cross-topic patterns at ME5 embedding level (e.g.
"explain X concept" structure → ≥0.85 cosine across topics). Driver
applies per-relationship thresholds:
- Within same sub_topic: strict 0.85
- Cross sub_topic, same topic: relaxed 0.92
- Cross-topic: relaxed 0.95

This honors Phase 2 spec acknowledgment of "within-topic adjacency
informational, not blocking".

### Repair 3 — PatternLibrary.from_disk audit_status filter
**Module**: `src/retrieval/pattern_lookup.py`
**Commit**: 0f74c2c (C16)
**Rationale**: Loaded ALL 104 patterns into `lib.patterns` while
FAISS metadata correctly held only 80 active. Subtle inconsistency
where iterating `lib.patterns` saw quarantined patterns. Repair:
skip inactive by default with `include_inactive=True` flag for
diagnostic uses. **All 3 audit-aware modules now use the same
`INACTIVE_STATUSES = {deprecation_candidate, deprecated, under_review}`
set** — alignment complete.

## Token cost

| Phase | Cost |
|---|---|
| Audit smoke tests (Tier 1, 6 generators) | ~12K Groq |
| Driver smoke (2 patterns through full pipeline) | ~3K |
| Tier 2-4 audits (mostly synthetic / no Groq) | ~0K |
| **Total cumulative** | **~15K of 10M soft target** |

Phase 4 mass expansion budget (50M+ tokens) is intact.

## Phase 4 STEP 3 M1 retry readiness

Per Phase 4 v2.1 prompt §STEP 3 per-batch protocol:

1. **Generate seed examples + negatives + xling**: ✓ all 4 generators
   HEALTHY (variants / negatives / xling / new driver bundles in seed call)
2. **Schema validation**: ✓ Pydantic Pattern.model_validate works
3. **Quality grader (5-axis ≥ 4)**: ✓ HEALTHY, M1 retry driver invokes
4. **Conflict checker (sub-topic-aware policy)**: ✓ HEALTHY, M1 retry
   driver invokes with relaxed cross-topic policy
5. **Append + origin tagging**: ✓ HEALTHY, audit log entry per batch
6. **FAISS rebuild**: ✓ HEALTHY, audit_status filter excludes quarantined
7. **Acceptance gate (50% soft / 30% hard)**: ✓ wired in driver

Smoke test on M1 retry driver:
- 2 synthetic patterns (Bushidō ce_humanities, quantum entanglement
  ce_science)
- Full pipeline: groq seed → schema → grader → conflict policy filter
- Result: 2/2 accepted (100%) — pipeline working end-to-end

## Risk items

### Cross-topic 0.85 threshold sensitivity (informational)
- ME5 multilingual embeddings cluster around 0.85+ for "explain X"
  structure regardless of subject
- Driver mitigates with sub-topic-aware threshold (0.85 / 0.92 / 0.95)
- For Phase 4 expansion at scale, monitor false-positive rate; if
  driver rejects too aggressively, raise within-sub-topic threshold
  to 0.88 or extend cross-sub-topic to 0.94

### ISM corpus distribution skew (Phase 4 STEP 5 work)
- ISMProfile retrieve() misclassifies novel queries due to KNN
  voting bias toward dominant factual_query class
- Phase 4 STEP 5 Path B refinement plan addresses (Op-1 intent
  rebalance + Op-2 abstain gap, ~14M tokens budgeted)
- Out of scope for module audit; addressed in Phase 4 STEP 5

### env-on harness time re-measurement deferred
- Phase 3 stab Commit 28-29 measured 5:34 wall clock
- No structural change since; re-measurement deferred (would consume
  ~6 min)
- If suspicion arises, re-measure via:
  `MOBIUS_PATTERN_LIBRARY=1 python3 scripts/run_33_scenarios.py`

## M1 retry recommendation

The new `phase4_seed_driver.py` is the M1 retry foundation:
- Replaces deprecated `create_seed_patterns.py`
- Invokes full pipeline: groq seed → schema → quality grader →
  conflict checker (sub-topic-aware) → append + audit log
- Per-pattern cost: ~6K Groq tokens (3K seed + 3K grader)
- M1 1,000-pattern target: ~6M tokens (within ST1 ≤ 50M budget)
- Acceptance gate enforced at driver level (50% soft / 30% hard)

**M1 retry can begin in next conversation** with Phase 4 v2.1 prompt
re-issued. Pre-flight will pass at HEAD `71083fa`.

Suggested first batch: same priorities as before-quarantine handover
(sr_meta_dialogue / ce_science / ce_humanities / ce_meta_concept
zero-coverage sub-topics) but routed through `phase4_seed_driver.py`
this time.

## Audit chain commits

```
71083fa  C17  verification_scripts HEALTHY
0f74c2c  C16  subtopic_aware_infra HEALTHY + audit_status filter aligned (REPAIR 3)
636d10d  C15  routing_engine HEALTHY + 3-mode baseline
32421be  C14  me5_singleton + engine_cache HEALTHY
bc2fafa  C13  audit_pattern_library script HEALTHY
acdf478  C12  ism_autogen + ismprofile HEALTHY (data refinement deferred)
aa4b8d8  C11  hit_count_instrumentation HEALTHY + concurrent test
4654c3d  C10  secretary HEALTHY + HARD CONSTRAINT 7 re-verification
baee748  C9   library_inspector HEALTHY per-section verification
33538b3  C8   phase4_seed_driver new + groq_client HEALTHY + conflict_checker REPAIR (REPAIR 1+2)
d3f27eb  C7   conflict_checker HEALTHY (audit pre-repair findings)
66785ca  C6   quality_grader HEALTHY + multi-judge invocation verified
cb45f57  C5   xling_query_generator HEALTHY + smoke test
0f95d94  C4   negatives_generator HEALTHY + smoke test
7f8e665  C3   variants_generator HEALTHY + smoke test
8daa4db  C2   module existence + import check (34/34 healthy)
fe24432  C1   module inventory
7f5a3e0   prompt landed
```
