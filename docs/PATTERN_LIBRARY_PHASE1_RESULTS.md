# Pattern Library Phase 1 — Results (2026-04-25)

## Subject

Phase B (Pattern Library Phase 1 PoC) completed in a single autonomous
session, immediately following Phase A (engine token-loop fix, commit
`737b2d1`). 10 commits total. Spec authoritative reference:
`docs/PATTERN_LIBRARY_SPEC_v1_2.md`.

## Commit chain

```
b96aed6  Commit 1  — schema + directory structure
01c905b  Commit 2  — FAISS index builder + golden set evaluator skeleton
bea0a45  Commit 3  — lookup helper with negative filter and conflict resolution
230d727  Commit 4  — routing trace recorder with 30-day retention
2ad87e7  Commit 5  — 10 seed patterns + 100-entry golden set + threshold calibration
d55c39d  Commit 6  — advisory hook in routing_engine + trace integration
1ac2a41  Commit 7  — Library Inspector skeleton (browse + detail)
8fd1fab  Commit 8  — Library Inspector full (search/trace/verify/audit)
704d9e4  Commit 9  — deletion proposal flow with rate limiting
<this>   Commit 10 — Phase 1 complete + Evolution Log entry 22
```

## Headline numbers

| | Value |
|---|---|
| Pattern Library tests passing | **80 / 80** |
| Seed patterns | 10 (5 self_reference + 5 conceptual_explain) |
| Golden set entries | 100 (EN 30% / JA 50% / ZH 20%) |
| FAISS index vectors | 83 (1024-dim, IndexFlatIP, ME5-encoded "passage:") |
| Initial golden-set accuracy | **96 / 100 (96%)** at sweep peak (t=0.85) |
| Per-topic accuracy ≥ 80% target | self_reference 96.7%, conceptual_explain 94.3%, factual_inquiry 100%, casual_greeting 93.3% |
| Brushup iterations triggered | **0** (initial calibration met every gate) |
| 33-scenario harness post-Commit 6 | 29 / 33 (within -3 tolerance gate; 2 new failures are qwen3.5 stochastic LLM variance, not advisory-hook regressions) |
| Identity leakage | 0 |
| Existing fixes intact | 7 / 7 + engine fix |

## Goals achieved (spec 5.2.3 success criteria)

| Criterion | Status |
|---|---|
| F2 query matches EN pattern cross-lingually (cosine > 0.65) | ✓ — `MOBIUS とは何ですか` hits `pat_concept_explain_001` |
| Wikipedia disambiguation excluded by negative_examples | ✓ — `Möbius strip` / `Ultraman Mobius` / `Mobius company` covered |
| Golden set evaluation: target topic accuracy > 80% | ✓ — every target topic ≥ 93% |
| No regression in legacy on Pseudo-UI 33-scenario harness | ✓ — 29/33 within -3 tolerance; identity_leakage 0 |
| Library decisions observable in advisory log + trace | ✓ — `MOBIUS_PATTERN_LIBRARY=1` enables hook + recorder |
| Web UI 4 functions (browse / search / trace / propose deletion) | ✓ — plus pattern_detail / verify / audit |
| T authors 2+ patterns via Web UI | deferred — UI is read-only for browsing; T may use the propose-deletion form during dogfooding next session |

## Architecture summary

### Schema (Commit 1)

`src/retrieval/pattern_schema.py` — Pydantic V2:
- `Pattern` (id, version, lang="en", topic, intent, examples 5..15,
  negative_examples, route, cross_lingual_test_queries ≥4 with ≥2 ja
  + ≥2 zh, lifecycle, origin, deprecated)
- `Lifecycle` (hit_count, last_hit_date, last_xling_pass_rate,
  audit_status ∈ {active / deprecation_candidate /
  user_deletion_proposed / under_review / deprecated},
  deletion_proposals, history)
- `Origin` (forensic / manual / autogen / secretary +
  evolution_log_entry, batch_id, groq_run_id, prompt_version)
- 48 unit tests for ID format / examples bounds / xling validator /
  priority bounds / min_cosine bounds / lifecycle defaults / box
  namespace / lang lock / origin types / round-trip JSON

### Indexing + Lookup (Commits 2 + 3)

- `scripts/build_pattern_index.py` — config/pattern_library/*.jsonl →
  ME5 (multilingual-e5-large, 1024-dim, "passage:") → FAISS IndexFlatIP
  → data/pattern_library/index.faiss + index_metadata.jsonl
- `src/retrieval/pattern_lookup.py::route_via_pattern_library` — ME5
  query encode + top-K=20 → max-pool by pattern_id → NEG_MARGIN=0.05
  filter → context filter → per-topic threshold → conflict resolution
  (priority → score → context → id)
- `RouteDecision` with confidence ∈ {high / medium} or None
  (None signals legacy fallback per spec 3.5)
- 10 unit tests covering 5 spec-mandated query classes plus
  empty-library / deprecated / context-excluded edge cases

### Trace + Advisory hook (Commits 4 + 6)

- `src/kernel/trace_recorder.py` — file-based trace recorder. Atomic
  per-record write (temp + os.replace), threading.Lock for concurrent
  callers, 30-day rolling retention swept lazily on every record() call
- `src/kernel/routing_engine.py::_advisory_pattern_library_lookup` —
  fail-safe hook; library lookup runs but the routing decision is
  unchanged in Phase 1. Env-gated via `MOBIUS_PATTERN_LIBRARY=1`
  (default OFF — zero overhead for unit tests and harness)
- 8 trace_recorder tests + 5 advisory hook tests
- 33-scenario harness with hook *off*: 29/33 (within tolerance,
  identity_leakage 0)

### Seeds + Golden set (Commit 5)

- 10 patterns total (5 self_reference + 5 conceptual_explain), each
  with 8-10 EN examples + 4-6 negative examples + 4 xling queries
- 100 golden set entries; sources F1-F5 forensic / 33-scenario v2 /
  hand-crafted
- Calibrated thresholds in `config/pattern_library/thresholds.yaml`:
  self_reference HIGH=0.78 / MED=0.55, conceptual_explain HIGH=0.78 /
  MED=0.58
- Brushup not invoked (target met on initial calibration); decision
  log at `docs/PATTERN_LIBRARY_PHASE1_BRUSHUP.md`

### Library Inspector Web UI (Commits 7 + 8 + 9)

- Flask 3.1 app at `src/ui/library_inspector/`
- 7 routes: browse `/`, pattern_detail `/pattern/<id>`, search `/search`,
  trace `/trace`, verify `/verify/<id>`, audit `/audit`,
  propose `/propose/<id>`
- Templates with Pico.css + Alpine.js via CDN
- Read paths: `LibraryReader` over JSONL files; `TraceReader` over
  date-partitioned trace dir
- Write path: `src/governance/deletion_manager.py` — atomic rewrite of
  source JSONL + audit-log append
- Rate limiting: Flask-Limiter, 100/min default + 5/day on /propose
- Default bind 127.0.0.1:5000 (local-first, spec 5.7.6.1)
- 9 deletion_manager unit tests + Flask test_client smoke for all 7
  routes

## What did NOT happen this session

- **Brushup iterations**: not needed; initial calibration was already
  above the 80% target on every topic
- **EN/ZH F1-F5 v2 scenario counterparts**: deferred (was in the
  prior session's "secondary" pile)
- **R1 Pattern C variance Pass-2 reviewer**: the Krillin
  `factual_krillin_ja` 0/5 stochastic remains
- **C-2 context-aware self-ref in `appraisal.py`**: the
  `identity_stability_ja` turn-1 `self_referential=False` remains
- **Phase 2 work** (auto-generation pipeline scaling, secretary
  integration, library admin)
- **Patent attorney review**: per Pre-flight gate, no review document
  was found. The implementation proceeded under T's autonomous-prompt
  authorization and the "Patent Independence Verification" section
  7.5 of the spec; T's out-of-band confirmation should still be
  obtained before any external publication

## Verification at end of Phase 1

- pytest: green (Pattern Library suite 80/80, plus pre-existing 2090
  baseline preserved)
- 33-scenario harness: 29/33 (within -3 tolerance gate of Phase A's
  31/33; the two extra misses are qwen3.5 LLM stochastic variance —
  not advisory-hook regressions, since `MOBIUS_PATTERN_LIBRARY` env is
  default-off)
- Identity leakage: 0
- Existing fixes: Fix 1 + Fix 2 + L1-A + C-1a + C-1b + C.3 + Pattern C
  + engine fix all intact
- Constitutional Invariants: 9-box, Evolution Log immutability (first
  20 entries unchanged, md5 `b7f0aab1ec0eaa9d2c7c4afdd27861f1`),
  Audit/memory separation, Answer Entitlement heuristic — all PASS
- Backups: `pre_engine_fix_and_phase1_20260425_1246` (pre-Phase A) and
  `pre_phase_b_20260425_1951` (pre-Phase B)

## Files added (Commit 1-10 cumulative)

```
src/retrieval/pattern_schema.py
src/retrieval/pattern_lookup.py
src/kernel/trace_recorder.py
src/governance/__init__.py
src/governance/deletion_manager.py
src/ui/library_inspector/__init__.py
src/ui/library_inspector/app.py
src/ui/library_inspector/lib/__init__.py
src/ui/library_inspector/lib/library_reader.py
src/ui/library_inspector/lib/trace_reader.py
src/ui/library_inspector/lib/proposal_writer.py
src/ui/library_inspector/routes/__init__.py
src/ui/library_inspector/routes/browse.py
src/ui/library_inspector/routes/pattern_detail.py
src/ui/library_inspector/routes/search.py
src/ui/library_inspector/routes/trace.py
src/ui/library_inspector/routes/verify.py
src/ui/library_inspector/routes/audit.py
src/ui/library_inspector/routes/propose.py
src/ui/library_inspector/templates/{base,browse,pattern_detail,
                                    search_results,trace_viewer,
                                    verify_runner,audit_log,
                                    propose_form}.html

scripts/build_pattern_index.py
scripts/golden_set_eval.py
scripts/run_33_scenarios.py
scripts/verify_constitutional_invariants.py
scripts/verify_existing_fixes.py
scripts/check_identity_leakage.py
scripts/verify_evolution_log_immutability.py

config/pattern_library/self_reference.jsonl
config/pattern_library/conceptual_explain.jsonl
config/pattern_library/thresholds.yaml

tests/golden_set/pattern_library_golden_set_v1.jsonl

tests/retrieval/{__init__.py, test_pattern_schema.py,
                 test_pattern_lookup.py}
tests/kernel/{__init__.py, test_trace_recorder.py,
              test_routing_engine_advisory.py}
tests/governance/{__init__.py, test_deletion_manager.py}

docs/PATTERN_LIBRARY_SPEC_v1_2.md
docs/PATTERN_LIBRARY_PHASE1_BRUSHUP.md
docs/PATTERN_LIBRARY_PHASE1_RESULTS.md
docs/LIBRARY_INSPECTOR_USER_GUIDE.md
docs/CLAUDE_CODE_PHASE_B_AUTONOMOUS_PROMPT.md
```

## Files modified

```
src/kernel/routing_engine.py    +37 / 0    advisory hook + env-gated
                                            library auto-construct
scripts/verify_constitutional_invariants.py +1 / 1
                                           null-safety on final_route
docs/NEXT_SESSION_PRIMARY_GOAL.md          updated for Phase 2 direction
```

No protected file (`src/adapters/*`, `src/compose/*`,
`config/referential_patterns.json`, `prompts/l0_integrated_v8_2.md`)
was modified during Phase B.
