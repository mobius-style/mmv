# Phase 4 M1 retry — Within-Sub-Topic Saturation Diagnostic

**Phase 4 v2.1 STEP 3 M1 retry batch 2 immediate halt** (acceptance 0/8 < 30%
floor).

## Findings

The new full-pipeline driver `phase4_seed_driver.py` (audit Commit 8) is
working correctly. The 0% acceptance is the **within-sub-topic 0.85
threshold firing on legitimate semantic overlap** between sibling
patterns within the same sub-topic, NOT a wiring gap or silent fail.

### Batch 2 rejection details

| Pattern | sub_topic | Top conflict | Cosine | Threshold | Verdict |
|---|---|---|---|---|---|
| pat_self_reference_019 (ask_message_clarification) | sr_meta_dialogue | pat_self_reference_018 (ask_topic_drift_meta) | 0.924 | within-sub 0.85 | rejected |
| pat_self_reference_020 (ask_message_repeat) | sr_meta_dialogue | pat_self_reference_018 | 0.894 | within-sub 0.85 | rejected |
| pat_concept_explain_027 (explain_math_concept) | ce_science | pat_concept_explain_031 (ask_define_term_strict, ce_meta_concept) | 0.949 | cross-sub same-topic 0.92 | rejected |
| pat_concept_explain_033 (explain_astronomy) | ce_science | pat_concept_explain_026 (explain_physics) | 0.887 | within-sub 0.85 | rejected |
| pat_concept_explain_034 (explain_linguistics) | ce_humanities | pat_concept_explain_029 (explain_philosophy) | 0.887 | within-sub 0.85 | rejected |
| pat_concept_explain_035 (explain_art_history) | ce_humanities | pat_concept_explain_030 (explain_history) | 0.929 | within-sub 0.85 | rejected |
| pat_concept_explain_036 (explain_literary_theory) | ce_humanities | pat_concept_explain_029 (explain_philosophy) | 0.893 | within-sub 0.85 | rejected |
| pat_concept_explain_037 (ask_etymology_meta) | ce_meta_concept | pat_factual_inquiry_012 (ask_meaning, fi_specialized) | 0.981 | cross-topic 0.95 | rejected |

7 of 8 rejections are within-sub-topic (threshold 0.85). 1 is cross-topic
0.981 — true semantic duplicate of fi_specialized (correct rejection).

### Saturation curve

After batch 1 added 4 sub-topics × 2-3 patterns each, the M1 retry
batch 2 attempted the *next* siblings in the same sub-topics:

```
sr_meta_dialogue: 3 patterns (batch 1) → 4th, 5th rejected (cosine 0.89-0.92 against batch 1)
ce_science:       2 patterns (batch 1) → 3rd, 4th rejected (cosine 0.89 against batch 1)
ce_humanities:    2 patterns (batch 1) → 3rd, 4th, 5th rejected (cosine 0.89-0.93 against batch 1)
ce_meta_concept:  2 patterns (batch 1) → 3rd rejected (cosine 0.98 cross-topic vs fi_specialized)
```

The pattern: **at the 0.85 within-sub-topic threshold, sub-topics
saturate around 3-4 patterns** before the auto-gen output (one
"explain X concept" template) starts colliding with itself.

## Root cause

The within-sub-topic threshold (0.85) was designed for a small library
where 3-5 patterns per sub-topic was the target. **Phase 4 v2.1 targets
100-500 patterns per sub-topic** — at that scale, the 0.85 threshold
will reject ~95% of new candidates because LLM-generated "explain X" /
"ask Y" examples for the same sub-topic share structural embedding
features at cosine ≥ 0.85.

### Threshold scaling estimate (informal)

| Within-sub-topic threshold | Approx max patterns per sub-topic before saturation |
|---|---|
| 0.85 (current) | ~3-5 |
| 0.88 | ~10-15 |
| 0.92 (= cross-sub same-topic) | ~50-100 |
| 0.95 (= cross-topic) | ~200-500 |

To reach the Phase 4 target of 100-500 patterns per sub-topic, the
within-sub-topic threshold needs to reach **~0.95**, effectively
removing the within/cross distinction.

## Strategic options

### Option A — Raise within-sub-topic threshold

Modify `phase4_seed_driver.WITHIN_SUBTOPIC_STRICT` from 0.85 to 0.92
or 0.95. Allows more patterns per sub-topic. Trade-off: less
protection against true duplicates within a sub-topic; relies on
quality_grader (5-axis ≥ 4) as the primary discriminator.

### Option B — Lexical diversity prompt engineering

Modify the seed prompt to demand greater lexical diversity in the
examples (e.g., "your examples must use entirely different verbs and
sentence structures from any prior pattern in the same sub-topic").
Trade-off: hard to enforce empirically; doesn't fundamentally change
the embedding clustering.

### Option C — Token-level conflict gate

Replace cosine-based conflict checking with token-overlap detection
(e.g., reject only when ≥ 80% of bi-grams shared). Avoids the
"explain X concept" template collision while catching literal copies.
Trade-off: significant implementation work, untested.

### Option D — Sub-topic re-architecture

Restructure the 32-sub-topic taxonomy to be more granular (e.g.,
ce_science → ce_physics, ce_biology, ce_chemistry, ce_astronomy as
separate sub-topics). Trade-off: invalidates existing sub-topic
threshold tuning; requires golden set re-mapping.

## Recommendation

**Option A with empirical validation**: raise within-sub-topic
threshold from 0.85 to 0.92 in a separate commit, then validate
against golden 200 evaluation that no per-topic accuracy regression
appears. The change is reversible (single constant in driver), and
the golden 200 evaluation is the authoritative test of whether the
relaxed gate produces meaningful disambiguation.

If golden 200 per-topic ≥ 85% holds: continue M1 with relaxed
threshold. Otherwise revert and consider Options B-D.

## Decision: defer to next conversation

The threshold calibration is a Phase 4 design decision that
deserves fresh context, not a within-conversation patch. Per Phase 4
v2.1 prompt §STEP 3 protocol:

> If acceptance < 30% in single batch:
>   - Immediate halt
>   - Diagnostic + adjustment
>   - Resume only after acceptance ≥ 50% in test batch

The diagnostic is complete (this document). The adjustment + retry
should happen with fresh context. Next conversation should:

1. Read this diagnostic
2. Apply Option A (raise WITHIN_SUBTOPIC_STRICT 0.85 → 0.92)
3. Test on a small batch (re-run batch 2 specs) — expect ~50-80%
   acceptance
4. If acceptance recovers: validate golden 200 per-topic ≥ 85%
5. If validation passes: continue M1 expansion
6. If golden regresses: revert, try Option C or D

## State at this checkpoint

| | |
|---|---|
| HEAD | d1b98f1 (M1 retry batch 1, before saturation diagnostic) |
| Active patterns | 89 (Phase 3 stab close 80 + batch 1 9) |
| Quarantined | 24 (preserved) |
| FAISS vectors | 803 |
| Golden 200 per-topic | ALL 6 ≥ 85% (overall 90.0%) |
| 33-scen default | 30 single-run (within Phase 3 stab σ floor) |
| pytest | 278 passed |
| Constitutional Invariants | ALL PASS |
| Existing fixes | 7/7 + engine + C-2 + ME5 + Phase 3 stab C44 INTACT |
| Token cumul this run | ~110K Groq (10 specs × ~6K + 8 rejections × ~6K) |

## Verification before this commit

Driver halted on batch 2 0% acceptance — JSONL files unchanged
(verified by `git status` returning empty config/pattern_library
diff). The driver's halt-required → skip-write contract is functional.

Phase 4 v2.1 STEP 3 acceptance protocol firing exactly as designed.
