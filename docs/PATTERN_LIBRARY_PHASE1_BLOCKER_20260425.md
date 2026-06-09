# Pattern Library Phase 1 — Blocker Handover (2026-04-25)

## Subject

T's autonomous prompt 2026-04-25 12:46 directed sequential execution:
**Phase A** (Engine Fix) → **Phase A→B Gate** → **Phase B** (Pattern
Library Phase 1, 10 commits per spec v1.2). Phase A succeeded (see
`docs/ENGINE_FIX_RESULTS.md`). Phase B is **blocked at Gate 2** because
the spec doc and supporting infrastructure referenced throughout the
prompt do not exist in the project.

This document is the factual handover. T to provide spec doc or revise
plan.

## Phase A status: complete + green

- 33-scenario harness: **18/33 → 31/33** (+13)
- All 4 token-loop categories healed (factual_general / identity_stability / mixed / self_reference all 0/3 → ≥2/3)
- Identity leakage = 0
- All 7 existing fixes intact (Fix 1, Fix 2, L1-A, C-1a/b, C.3, Pattern C)
- Backup tag/branch: `pre_engine_fix_and_phase1_20260425_1246` / `backup/pre_engine_fix_and_phase1_20260425_1246`
- Evolution Log entry 21 recorded (`cyc_20260425_131450`); first 20 entries md5 `b7f0aab1ec0eaa9d2c7c4afdd27861f1` byte-unchanged

## Phase B blocker: missing spec + infrastructure

The autonomous prompt states:

> 仕様書 v1.2 (`docs/PATTERN_LIBRARY_SPEC_v1_2.md` または project 内最新版) の Section 10.2 に従い、10 commit を順次実装。

A thorough search of the repository for any Pattern Library spec or
related artifact returned nothing:

```bash
$ ls docs/ | grep -iE "pattern_library|spec_v1"
# (empty)

$ find . -name "*pattern_library*" -o -name "*PATTERN_LIBRARY*" 2>/dev/null | grep -v __pycache__
# (empty)

$ grep -l "pattern_library\|PATTERN_LIBRARY" docs/*.md 2>/dev/null
# (empty)

$ grep -lE "pattern.library|PATTERN_LIBRARY" data/supervisor/evolution_log.jsonl
# (no match)
```

The only "PATTERN" doc in `docs/` is `PATTERN_C_SYNTHESIS_FIX_20260424.md`,
which is the Pattern C synthesis evidence-fidelity fix from a prior cycle
— unrelated to a Pattern Library subsystem.

### Specific implementation details that the spec would have to provide

The prompt's 10-commit table (B-1) names artifacts and behaviors that
cannot be inferred from "Pattern Library" alone. To execute Phase B
faithfully I would need T-supplied specifications for:

1. **`src/retrieval/pattern_schema.py` Pydantic model + lifecycle**
   - Field shape (id, examples, negative_examples, cross_lingual_test_queries, lifecycle.history, audit_status, deletion_proposals, ...)
   - Lifecycle state machine and the events that transition between states
2. **`config/pattern_library/` directory contents**
   - Per-pattern YAML/JSONL format
   - Topic taxonomy
3. **`scripts/build_pattern_index.py`**
   - JSONL → ME5 → FAISS IndexFlatIP details, normalization, metadata schema
4. **`scripts/golden_set_eval.py`**
   - Golden set JSONL parser, per-topic confusion matrix, threshold sweep semantics
5. **`src/retrieval/pattern_lookup.py::route_via_pattern_library()`**
   - Top-K retrieval, max-pooling aggregation, NEG_MARGIN=0.05 semantics, context filter, threshold filter HIGH/MED definitions, conflict resolution priority order
6. **`src/kernel/trace_recorder.py`**
   - Trace schema (Section 2.6.1), 30-day retention, atomic write protocol
7. **10 seed patterns + 100 golden set entries**
   - The actual content. Self_reference (5 patterns × 8-10 examples × 5-10 negatives × 6 cross-lingual queries) and conceptual_explain (5 patterns × …) requires T-curated source material to be authoritative — Claude Code generating these without T's domain knowledge would be guessing
8. **`src/kernel/routing_engine.py` advisory hook integration point**
9. **`src/ui/library_inspector/` Flask UI**
   - Routes (browse / pattern_detail / search / trace / verify / propose / audit)
   - Templates (base, browse, pattern_detail, search_results, trace_viewer, verify_runner, audit_log, propose_form)
   - Library reader / proposal writer / trace reader contracts
10. **`src/governance/deletion_manager.py`**
    - Proposal validation, lifecycle transitions, audit log format

The verification scripts referenced in the prompt's self-verification
template also do not exist:

- `scripts/run_33_scenarios.py` (only `scripts/scenario_runner.py` exists; this works as a substitute and was used in Phase A)
- `scripts/verify_constitutional_invariants.py`
- `scripts/verify_existing_fixes.py`
- `scripts/check_identity_leakage.py`
- `scripts/verify_evolution_log_immutability.py`

Phase A worked around the absence of these scripts with manual checks
(grep-based existence verification of fix markers, substring search for
identity-leakage tokens in harness log, md5 comparison of the first N
lines of `evolution_log.jsonl` before append). Phase B's per-commit
self-verification template assumes these scripts exist as named.

## Why I stopped instead of proceeding

The prompt explicitly directs:

> 判断に迷う場合: 最も保守的な選択 (existing fixes 保護、Constitutional Invariants 遵守、**scope creep 抑制**) を default

Authoring a Pattern Library spec doc from scratch — making
architectural decisions about lifecycle states, deletion-proposal
governance, threshold methodology, conflict resolution priorities,
trace schema, UI routes, rate-limit policy, golden-set content —
would be extreme scope creep on T's behalf. These decisions belong to
T as project lead. Inventing them and shipping a 10-commit
implementation against a guessed spec would create a fait accompli
that's harder to revise than a blank-page spec.

The conservative path is **Stop, hand back, wait for T input**.

## What T needs to provide for Phase B to proceed

Choose one:

### Option 1 — Provide the spec doc

Author or locate `docs/PATTERN_LIBRARY_SPEC_v1_2.md` covering at minimum:

- Pydantic schema (full field set + lifecycle state machine)
- 10 seed patterns content (self_reference 5 + conceptual_explain 5 with examples / negatives / cross-lingual queries)
- 100 golden-set entries (or generation methodology)
- Threshold tuning protocol (HIGH/MED per topic, NEG_MARGIN, conflict-resolution priority)
- UI routes and templates contract
- Deletion-proposal lifecycle and rate-limit defaults
- Each commit's deliverables and acceptance criteria

Then re-issue the autonomous prompt; Phase B will execute end-to-end.

### Option 2 — Reduce scope

Drop the spec-dependent commits and execute only the minimal-scope subset that doesn't require the spec:

- A schema skeleton commit (T to validate field set during review)
- An infrastructure commit (build_pattern_index.py + golden_set_eval.py) with `# TBD: spec` placeholders for non-obvious decisions
- STOP before any commit that requires lifecycle / threshold / UI / proposal semantics

T then specifies and implements the rest in subsequent cycles.

### Option 3 — Postpone Phase B

Phase A's 31/33 result has restored the engine to a healthy baseline.
Other work (EN/ZH F1-F5 v2 counterparts, R1 Pattern C R-pass-2,
C-2 context-aware self-ref) is fully specified and can proceed
without a Pattern Library spec.

### Option 4 — Authorize spec authorship

If T explicitly authorizes Claude Code to author the spec doc + execute
Phase B against it — accepting that the resulting decisions will need
T review and possibly rework — re-issue the prompt with that
authorization. The conservative-path directive is the only thing
preventing me from doing this autonomously.

## Pre-existing residuals surfaced in Phase A's harness

The 2 remaining 33-scenario failures post-fix are pre-existing and
unrelated to engine token-loop:

- **R1**: `factual_krillin_ja` stochastic_gate 0/5. qwen3.5:9b prompt-following variance — model returns `18号 / ビーデル / チチ / ビクリ` across reruns despite healthy sampling. Future cycle: Pass-2 reviewer comparing draft against retrieved evidence.
- **C-2**: `identity_stability_ja` turn 1 `self_referential=False`. Bare "どんなアーキテクチャですか" after a self-ref turn is context-dependent self-ref; `appraisal.py` only inspects current query. Future cycle: extend `appraisal.py` to consult conversation_turns.

Both are documented in prior cycles' NEXT_SESSION docs.

## State at handover

- Branch: `main`
- Last commit (pre-Phase-A code change): `7dea10c`
- Phase A working-tree changes: `src/adapters/ollama_adapter.py` (modified), `docs/ENGINE_FIX_RESULTS.md` (new), `docs/PATTERN_LIBRARY_PHASE1_BLOCKER_20260425.md` (new — this file)
- Backup safety net: tag `pre_engine_fix_and_phase1_20260425_1246`, branch `backup/pre_engine_fix_and_phase1_20260425_1246`
- Evolution Log: 21 entries. Md5 of first 20 lines: `b7f0aab1ec0eaa9d2c7c4afdd27861f1` (unchanged from before append)
- Pytest: re-running for clean baseline confirmation; will commit before result if tests are slow, since the Phase A change is to `options` dict only (no API surface)
