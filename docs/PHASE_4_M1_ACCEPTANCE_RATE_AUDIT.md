# Phase 4 v2.1 M1 Acceptance Rate Audit

**Date**: 2026-04-27
**Triggered by**: T audit request — investigate whether the 100 % acceptance
rate reported across M1 B1 + B2 (24 patterns) reflected the full Phase 2
QA pipeline (multi-judge + 5-axis grader + conflict checker) or only schema
validation.

## Verdict

**The 100 % acceptance was schema-only. The full QA pipeline (5-axis quality
grader + cross-pattern conflict checker) was NOT invoked. Real combined-filter
acceptance rate: 0 / 39 (0.0 %).** All 39 patterns (24 committed B1+B2 + 15
uncommitted B3+B4) have been removed from the active library:

- Uncommitted B3+B4 (15 patterns): discarded via `git checkout config/pattern_library/*.jsonl`
- Committed B1+B2 (24 patterns): flagged with `lifecycle.audit_status="deprecation_candidate"`
- FAISS index rebuilt with new `audit_status` filter — back to 80 active
  patterns / 725 vectors (Phase 3 stab close baseline)

## Investigation findings

### 1. Quality grader (5-axis multi-judge consensus)

**Status**: NOT INVOKED by `create_seed_patterns.py`.

The driver (`scripts/pattern_autogen/create_seed_patterns.py`, Phase 2
Commit 19) does invoke `AutogenGroqClient.consensus()` which makes
3 calls at T=0.3 / 0.7 / 1.0 — but it consumes only the **first parseable
call's content** (line 144-149) and never invokes the separate
`scripts/pattern_autogen/quality_grader.py` module which performs the
formal 5-axis grading (intent_clarity / example_coverage /
negative_discrimination / xling_consistency / overall) with threshold
≥ 4.

**Audit result on 39 patterns when grader IS invoked retroactively**: 39/39 pass.

The patterns are individually well-formed (Pydantic schema valid + LLM
self-consistent on each axis). The miss was at the cross-pattern level.

### 2. Conflict checker (cross-pattern cosine ≥ 0.85)

**Status**: NOT INVOKED by `create_seed_patterns.py`.

`scripts/pattern_autogen/conflict_checker.py` exists with cosine threshold
0.85 against the existing library. The driver never calls
`ConflictChecker.check()`.

**Audit result on 39 patterns when checker IS invoked retroactively**: 0/39 pass.

Top conflicts (cosine ≥ 0.97 — true semantic duplicates):

| Pattern A | Pattern B | Cosine |
|---|---|---|
| pat_self_reference_020 (ask_who_you_are) | pat_self_reference_021 (ask_name) | 0.997 |
| pat_factual_inquiry_030 (ask_capital_city) | pat_factual_inquiry_031 (ask_country_location) | 0.995 |
| pat_casual_engagement_017 (agreement_polite) | pat_casual_engagement_009 (existing agreement) | 0.994 |
| pat_self_reference_023 (ask_help_offer) | pat_self_ref_identity_002 (existing describe_capabilities) | 0.987 |
| pat_casual_engagement_015 (small_talk_progress_check) | pat_casual_engagement_003 (existing small_talk) | 0.982 |
| pat_casual_engagement_010 (farewell_with_followup) | pat_casual_engagement_005 (existing farewell) | 0.980 |
| pat_concept_explain_034 (ask_what_is_generic) | pat_concept_explain_035 (ask_define_term) | 0.976 |
| pat_casual_engagement_018 (agreement_emphatic) | pat_casual_engagement_017 | 0.972 |
| pat_concept_explain_027 (explain_biology_concept) | pat_factual_inquiry_011 (existing) | 0.961 |

The conflicts span both **within-batch duplicates** (e.g. ask_who_you_are vs
ask_name — same intent at the embedding level) and **vs-existing-library
overlaps** (e.g. ask_help_offer overlapping describe_capabilities).

### 3. Token consumption discrepancy

| Phase | Per-pattern Groq tokens | Pipeline stages |
|---|---|---|
| Phase 2 baseline | ~15K | seed + variants (30) + negatives (12) + xling (8) + 5-axis grader + conflict checker |
| **Phase 4 M1 (audited)** | **~1.2K** | **seed only (3-call consensus, first parseable consumed)** |

The 12.5× lower per-pattern cost reflects the missing pipeline stages, not
better prompt engineering.

### 4. 33-scenario default 29/33 single-run interpretation

Re-evaluated post-quarantine with FAISS rebuilt at 80 active patterns: **30/33**
(within Phase 3 stab N=5 mean 30.40 ± σ 0.55, informational).

The 29/33 reported in M1 B1 commit was a single-run measurement that
**included** the 24 quarantine_candidate patterns in the active index. With
those removed, the score returns to the σ floor band. The 24 patterns DID
introduce noise into the harness measurement, but the variance was within
the spec 7.8.6 informational band (Δ ≤ 1 single-run = stochastic floor not
regression).

## Remediation actions taken

1. **Discard B3+B4 uncommitted** (`git checkout config/pattern_library/*.jsonl`):
   15 patterns removed from JSONL files. Not committed; no git history impact.

2. **Quarantine B1+B2 24 committed patterns**: `audit_status` set to
   `deprecation_candidate` + lifecycle history event recorded
   (event=`audit_flag`, actor=`claude_code_audit`, detail explains the
   audit). Patterns remain in JSONL for audit trail per HARD CONSTRAINT.

3. **Index builder filter**: `scripts/build_pattern_index.py` updated to
   skip patterns with `audit_status` in
   `{deprecation_candidate, deprecated, under_review}`. The 24 quarantined
   patterns are no longer visible to `route_via_pattern_library`.

4. **FAISS index rebuilt** under GPU slot 1 isolation
   (`CUDA_VISIBLE_DEVICES=0`, `nvidia-smi` confirmed slot 2 idle):
   80 active patterns / 725 vectors — exact Phase 3 stab close state.

## Verification post-remediation

| | |
|---|---|
| pytest | 203 passed / 0 failed |
| Constitutional Invariants | ALL PASS |
| Existing fixes 7/7 + engine + C-2 + ME5 + Phase 3 stab Commit 44 | INTACT |
| 33-scen default single-run | 30/33 (within σ floor) |
| Identity leakage | 0 |
| Golden 200 per-topic | ALL 6 ≥ 85 % (overall 90.0 % / 180 of 200) |
| Library active size | 80 (matches Phase 3 stab close) |
| Library quarantined | 24 (preserved in JSONL with `deprecation_candidate`) |
| FAISS index | 725 vectors (Phase 3 stab match) |

## Root cause

`scripts/pattern_autogen/create_seed_patterns.py` is the **Phase 2 Commit 19
seed driver**, designed for the initial pattern bootstrap when the library
was small (≤55 patterns) and conflicts within the small set were rare. It
was reused for Phase 4 M1 expansion without adding the missing pipeline
stages. The reuse was wrong: at 80+ patterns and beyond, conflict rates
rise sharply, and quality-grader filtering becomes load-bearing.

## Remediation plan for M1 retry (deferred to next session)

A new driver — `scripts/pattern_autogen/expand_library_p4_full_pipeline.py`
(or equivalent) — must implement the **full Phase 4 v2.1 §STEP 3 per-batch
protocol**:

1. Generate seed (5-10 examples) — current `create_seed_patterns.py` step
2. Auto-gen variants (30 paraphrases via `variants_generator.py`)
3. Auto-gen negatives (12 per pattern via `negatives_generator.py`,
   NEG_MARGIN gating)
4. Auto-gen xling (8 per pattern via `xling_query_generator.py`,
   JA/ZH/EN balanced)
5. **Quality grade** (5-axis median ≥ 4 via `quality_grader.py`) — REJECT
   below threshold
6. **Conflict check** (cosine ≥ 0.85 via `conflict_checker.py`) — REJECT
   any conflict
7. Schema validation
8. Append + origin tagging
9. FAISS incremental rebuild (GPU slot 1 only)
10. Acceptance rate computed (accepted / generated)

Per-pattern token cost expected: ~15K (Phase 2 baseline). For M1 1,000
target this is ~15M tokens — within ST1 budget (≤ 50M).

Acceptance gate per Phase 4 v2.1: ≥ 50 % batch sustained; halt sub-topic
on 3 consecutive < 50 %; immediate halt on single batch < 30 %.

## Lessons + behavioural change

- "Acceptance rate" as a metric means **post-full-filter** acceptance,
  not schema validation. Reporting must specify which filter the rate
  refers to.
- Reusing Phase-2 drivers in Phase 4 requires explicit verification that
  the driver's pipeline matches Phase 4's tighter requirements.
- Conflict checker is load-bearing past 80 patterns; auto-generation
  without it produces silent semantic-duplicate proliferation.
- T's audit instinct ("100 % acceptance from a 0 % baseline is suspicious")
  is the right instrument; the prompt's per-batch acceptance protocol
  exists precisely to surface this kind of pipeline drift.

## Quarantine reactivation policy

The 24 quarantined patterns can be reactivated individually if:
1. Their conflict pairs are reviewed and either (a) the conflicting
   existing pattern is itself deprecated, or (b) the cosine is determined
   to be a within-topic informational adjacency (per spec 7.2.1) rather
   than a true duplicate.
2. They pass the full pipeline (quality grader + conflict checker against
   the post-Phase-4 expanded library, where the threshold's strictness
   may be re-evaluated).

Until reactivated: `audit_status="deprecation_candidate"` blocks them
from FAISS and routing.
