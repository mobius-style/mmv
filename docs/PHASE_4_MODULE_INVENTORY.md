# Phase 4 Module Inventory

**Generated**: 2026-04-27 (Phase 4 audit Commit 1)
**Trigger**: M1 incident — `create_seed_patterns.py` silent fail
discovered, audit sweep initiated to detect systemic module health
issues before Phase 4 mass Groq expansion.

## Tier 1 — Auto-gen pipeline (M1 retry core dependency, HIGHEST priority)

| # | Module | Path | Phase | Status (entering audit) |
|---|---|---|---|---|
| 1 | variants_generator | `scripts/pattern_autogen/variants_generator.py` | Phase 2 Commit 14 | UNKNOWN |
| 2 | negatives_generator | `scripts/pattern_autogen/negatives_generator.py` | Phase 2 Commit 15 | UNKNOWN |
| 3 | xling_query_generator | `scripts/pattern_autogen/xling_query_generator.py` | Phase 2 Commit 16 | UNKNOWN |
| 4 | quality_grader | `scripts/pattern_autogen/quality_grader.py` | Phase 2 Commit 17 | **CONFIRMED NOT INVOKED in M1 by `create_seed_patterns.py`** |
| 5 | conflict_checker | `scripts/pattern_autogen/conflict_checker.py` | Phase 2 Commit 17 | **CONFIRMED NOT INVOKED in M1 by `create_seed_patterns.py`** |
| 6 | groq_client | `scripts/pattern_autogen/groq_client.py` | Phase 2 Session 1 | UNKNOWN |
| 7 | create_seed_patterns | `scripts/pattern_autogen/create_seed_patterns.py` | Phase 2 Commit 19 | **DEPRECATED — schema-only validation** (M1 incident root cause) |
| extra | run_variants / run_negatives / run_xling | `scripts/pattern_autogen/run_*.py` | Phase 2 | UNKNOWN — CLI wrappers |
| extra | expand_library_p3c32 | `scripts/pattern_autogen/expand_library_p3c32.py` | Phase 3 Commit 32 | one-shot — out of scope |

## Tier 2 — Production wiring (medium priority)

### Library Inspector (Phase 2 Commits 21-22)

| # | Module | Path | Phase | Status |
|---|---|---|---|---|
| 10 | Browse route | `src/ui/library_inspector/routes/browse.py` | Phase 2 C21 | UNKNOWN |
| 10 | Pattern detail route | `src/ui/library_inspector/routes/pattern_detail.py` | Phase 2 C21 | UNKNOWN |
| 10 | Search route | `src/ui/library_inspector/routes/search.py` | Phase 2 C21 | UNKNOWN |
| 10 | Trace route | `src/ui/library_inspector/routes/trace.py` | Phase 2 C21 | UNKNOWN |
| 10 | Verify route | `src/ui/library_inspector/routes/verify.py` | Phase 2 C21 | UNKNOWN |
| 10 | Audit route | `src/ui/library_inspector/routes/audit.py` | Phase 2 C22 | UNKNOWN |
| 10 | Propose route | `src/ui/library_inspector/routes/propose.py` | Phase 2 C22 | UNKNOWN |
| 11 | Author form (POST `/pattern/new`) | `src/ui/library_inspector/routes/author.py` | Phase 2 C21 | UNKNOWN |
| 12 | Audit dashboard 6 sections | `src/ui/library_inspector/routes/audit.py` | Phase 2 C22 | UNKNOWN |
| - | Secretary route | `src/ui/library_inspector/routes/secretary.py` | Phase 3 C38 | UNKNOWN (audit covers in #15) |

### Secretary (Phase 3 Commits 36-38)

| # | Module | Path | Phase | Status |
|---|---|---|---|---|
| 13 | Secretary core (proposal-only) | `src/secretary/secretary_core.py` | Phase 3 C36 | UNKNOWN |
| 14 | Trigger conditions | `src/secretary/secretary_core.py` (5 triggers) | Phase 3 C37 | UNKNOWN |
| 15 | Library Inspector `/secretary` integration | `src/ui/library_inspector/routes/secretary.py` | Phase 3 C38 | UNKNOWN |

### Hit-count instrumentation (Phase 3 Commits 33-34)

| # | Module | Path | Phase | Status |
|---|---|---|---|---|
| 16 | Atomic increment | `src/retrieval/hit_count_tracker.py` | Phase 3 C33 | UNKNOWN |
| 17 | 5-min aggregation | `src/retrieval/hit_count_tracker.py` (.flush()) | Phase 3 C33 | UNKNOWN |
| 18 | last_hit_date update | `src/retrieval/hit_count_tracker.py` | Phase 3 C33 | UNKNOWN |
| - | Library Inspector hot/cold filter | `src/ui/library_inspector/routes/browse.py` | Phase 3 C34 | UNKNOWN (audit covers in #10) |

## Tier 3 — ISM auto-gen + ISMProfile (Phase 4 STEP 5 본격 사용)

| # | Module | Path | Phase | Status |
|---|---|---|---|---|
| 8 | intent_variants_generator | `scripts/ism_corpus/intent_variants_generator.py` | Phase 4 Foundation C7 | UNKNOWN — never invoked |
| 9 | abstain_gap_filler | `scripts/ism_corpus/abstain_gap_filler.py` | Phase 4 Foundation C7 | UNKNOWN — never invoked |
| 32 | ISMProfile (KNN classifier) | `src/adapters/raf/profile.py` | pre-Phase-1 | PROTECTED (no touch); audit reads only |
| 32 | Heuristic fallback | `src/kernel/routing_engine.py:564-617` | pre-Phase-1 | PROTECTED |
| - | ISM corpus 36K | `data/raf/ism_chunks.jsonl` | pre-Phase-1 | DATA LAYER (Phase 4 STEP 5 refines) |

## Tier 4 — Lower priority (信頼度高い、念のため)

| # | Module | Path | Phase | Status |
|---|---|---|---|---|
| 19 | ME5 singleton | `src/services/me5_singleton.py` | Phase 3 C27 | Phase 3 stab measured 5:34 — likely healthy |
| 20 | Module-level engine cache | `scripts/pseudo_ui_runner.py` | Phase 3 C28 | likely healthy |
| 21 | Routing engine downstream consumer | `src/kernel/routing_engine.py` (Phase 3 stab C44 wire) | Phase 3 stab C44 | Phase 3 stab verified — likely healthy |
| 22 | Routing engine extension | `src/kernel/routing_engine.py` | Phase 3 stab | likely healthy |
| 23 | Sub-topic FAISS metadata | `data/pattern_library/index_metadata.jsonl` | Phase 4 Foundation C3 | rebuilt at audit_status filter; likely healthy |
| 24 | Sub-topic-aware lookup | `src/retrieval/pattern_lookup.py` | Phase 4 Foundation C3 | 10 tests pass — likely healthy |
| 25 | Per-sub-topic threshold | `config/pattern_library/thresholds.yaml` | Phase 4 Foundation C4 | 32 entries — likely healthy |
| 26 | Pattern lifecycle audit script | `scripts/audit_pattern_library.py` | Phase 3 C35 | UNKNOWN (synthetic test only at landing) |
| 27 | run_33_scenarios harness | `scripts/run_33_scenarios.py` | Phase B | continuous invoke — likely healthy |
| 28 | verify_constitutional_invariants | `scripts/verify_constitutional_invariants.py` | Phase B | continuous invoke |
| 29 | verify_existing_fixes | `scripts/verify_existing_fixes.py` | Phase B | continuous invoke |
| 30 | check_identity_leakage | `scripts/check_identity_leakage.py` | Phase B | continuous invoke |
| 31 | verify_evolution_log_immutability | `scripts/verify_evolution_log_immutability.py` | Phase B | continuous invoke |

## Out of audit scope (Phase 4 で touch しない)

- L0 / EAL / QK / RAF / VRAMBroker / TVS / MKR (MOBIUS framework adjacent)
- Box W (Wikipedia + Kiwix adapters; legacy label Box B) — `src/adapters/wiki_adapter.py` etc.
- Box 0 (custom RAG adapter) — `src/adapters/custom_rag_adapter.py`
- Phase 1 of Pattern Library schema, FAISS builder — used continuously, signal already strong

## Dependency graph (key edges)

```
M1 retry full-pipeline driver (Step 2 Commit 8 — to be designed)
  ├─→ groq_client (#6)
  ├─→ variants_generator (#1)
  ├─→ negatives_generator (#2)
  ├─→ xling_query_generator (#3)
  ├─→ quality_grader (#4)         [skipped in M1 incident]
  ├─→ conflict_checker (#5)       [skipped in M1 incident]
  ├─→ pattern_schema (Pattern.model_validate)
  └─→ build_pattern_index (FAISS rebuild after batch)

ISM corpus expansion (Phase 4 STEP 5)
  ├─→ intent_variants_generator (#8)
  ├─→ abstain_gap_filler (#9)
  ├─→ pattern_autogen.groq_client (reused, #6)
  └─→ ISMProfile read-only (#32)

Routing engine evaluate path
  ├─→ ISMProfile (#32) or heuristic fallback
  ├─→ pattern_lookup (#24, sub-topic-aware)
  ├─→ ME5 singleton (#19)
  ├─→ hit_count_tracker (#16-18)
  └─→ trace recorder

Library Inspector (Flask app)
  ├─→ Library Reader (data layer)
  ├─→ author / propose / audit / secretary routes
  └─→ Hot/cold filter (Phase 3 C34)
```

## Recent commits touching each module (last 10 commits)

```
7f5a3e0 (HEAD)  audit prompt
a1d386d         M1 audit + quarantine + build_pattern_index audit_status filter
bcc0551         M1 in-progress handover
99034a2         M1 B2 (now quarantined)
be60623         M1 B1 (now quarantined)
4082e69         Phase 4 foundation handover
93dc6b3         ISM auto-gen pipeline (Foundation C7)
c756cb1         ISM transfer plan
576f8da         ISM investigation
e2d3beb         per-sub-topic threshold init
```

## Phase 4 audit per-module priority

The audit will proceed in tier order (1 → 4) with the goal of
establishing the M1 retry core dependency first (Tier 1, Commits
3-8) before assessing wiring (Tier 2-3) and infrastructure (Tier 4).

Repair scope is module-local: a broken module is repaired without
touching others. If 5-cycle iteration cannot fix a module, it is
flagged deprecated and the M1 retry driver is designed to avoid
its dependency.
