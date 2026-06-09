# Phase 4 Module Existence + Import Report

**Phase 4 audit Commit 2** — existence + import smoke check across all
inventory modules (Tier 1-4).

## Summary

| | |
|---|---|
| Total modules audited | 34 |
| Healthy (importable Python module) | 22 |
| Exists (script, no import test) | 12 |
| Missing | **0** |
| Import errors | **0** |

**Verdict**: All inventory modules exist on disk and Python modules import
cleanly without runtime errors. No file-level breakage detected. The
Tier 2-3 audit will dig deeper into wiring + functional behavior.

## Tier 1 — Auto-gen pipeline (7 modules)

| Module | Path | Status |
|---|---|---|
| variants_generator | `scripts/pattern_autogen/variants_generator.py` | ✓ HEALTHY |
| negatives_generator | `scripts/pattern_autogen/negatives_generator.py` | ✓ HEALTHY |
| xling_query_generator | `scripts/pattern_autogen/xling_query_generator.py` | ✓ HEALTHY |
| quality_grader | `scripts/pattern_autogen/quality_grader.py` | ✓ HEALTHY |
| conflict_checker | `scripts/pattern_autogen/conflict_checker.py` | ✓ HEALTHY |
| groq_client | `scripts/pattern_autogen/groq_client.py` | ✓ HEALTHY |
| create_seed_patterns | `scripts/pattern_autogen/create_seed_patterns.py` | ✓ HEALTHY (imports OK; M1 incident is **wiring** issue, not file-level) |

**Important nuance**: `create_seed_patterns.py` imports cleanly, but the
M1 audit found it does NOT invoke `quality_grader` nor `conflict_checker`.
Existence + import is necessary but not sufficient — the actual call graph
must be verified in Tier 1 audit (Commits 3-8).

## Tier 2 — Library Inspector (10 modules)

| Module | Path | Status |
|---|---|---|
| inspector_app | `src/ui/library_inspector/app.py` | ✓ HEALTHY |
| browse_route | `routes/browse.py` | ✓ HEALTHY |
| pattern_detail_route | `routes/pattern_detail.py` | ✓ HEALTHY |
| search_route | `routes/search.py` | ✓ HEALTHY |
| trace_route | `routes/trace.py` | ✓ HEALTHY |
| verify_route | `routes/verify.py` | ✓ HEALTHY |
| audit_route | `routes/audit.py` | ✓ HEALTHY |
| propose_route | `routes/propose.py` | ✓ HEALTHY |
| author_route | `routes/author.py` | ✓ HEALTHY |
| secretary_route | `routes/secretary.py` | ✓ HEALTHY |

## Tier 2 — Secretary + Hit-count (2 modules)

| Module | Path | Status |
|---|---|---|
| secretary_core | `src/secretary/secretary_core.py` | ✓ HEALTHY |
| hit_count_tracker | `src/retrieval/hit_count_tracker.py` | ✓ HEALTHY |

## Tier 3 — ISM auto-gen + ISMProfile (3 modules)

| Module | Path | Status |
|---|---|---|
| intent_variants_generator | `scripts/ism_corpus/intent_variants_generator.py` | ✓ HEALTHY |
| abstain_gap_filler | `scripts/ism_corpus/abstain_gap_filler.py` | ✓ HEALTHY |
| ism_profile | `src/adapters/raf/profile.py` | ✓ HEALTHY |

## Tier 4 — Infrastructure (12 modules)

| Module | Path | Status |
|---|---|---|
| me5_singleton | `src/services/me5_singleton.py` | ✓ HEALTHY |
| pseudo_ui_runner | `scripts/pseudo_ui_runner.py` | ✓ EXISTS (script) |
| routing_engine | `src/kernel/routing_engine.py` | ✓ HEALTHY |
| pattern_lookup | `src/retrieval/pattern_lookup.py` | ✓ HEALTHY |
| pattern_schema | `src/retrieval/pattern_schema.py` | ✓ HEALTHY |
| build_pattern_index | `scripts/build_pattern_index.py` | ✓ EXISTS (script) |
| audit_pattern_library | `scripts/audit_pattern_library.py` | ✓ EXISTS (script) |
| run_33_scenarios | `scripts/run_33_scenarios.py` | ✓ EXISTS (script) |
| verify_constitutional | `scripts/verify_constitutional_invariants.py` | ✓ EXISTS (script) |
| verify_existing_fixes | `scripts/verify_existing_fixes.py` | ✓ EXISTS (script) |
| check_identity_leakage | `scripts/check_identity_leakage.py` | ✓ EXISTS (script) |
| verify_evolution_log | `scripts/verify_evolution_log_immutability.py` | ✓ EXISTS (script) |

## Methodology

For Python modules: `importlib.import_module(<dotted_path>)` — confirms file
exists, syntax-parses, all top-level imports resolve, no module-level
exceptions raised.

For CLI scripts: file existence + executability check; import test deferred
to Tier 4 audit which invokes them with `--help` or synthetic inputs.

## Next steps

Tier 1 functional audit (Commits 3-8):
- Synthetic-input smoke test per generator
- Multi-judge consensus invocation verification
- Per-pattern token cost actual measure
- M1 incident root-cause: `create_seed_patterns.py` does NOT invoke
  `quality_grader` + `conflict_checker` — to be replaced by new
  full-pipeline driver in Commit 8

Tier 2-3 wiring audit (Commits 9-13):
- Library Inspector synthetic submissions
- Secretary HARD CONSTRAINT 7 re-verification
- Hit-count concurrent test
- ISM auto-gen smoke

Tier 4 infrastructure audit (Commits 14-17):
- ME5 singleton + harness time
- Routing engine 3-mode baseline
- Sub-topic-aware infra 32-sub-topic routing
- Verification scripts under Phase 4 state
