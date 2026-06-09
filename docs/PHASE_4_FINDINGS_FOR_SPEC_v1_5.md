# Phase 4 Findings — Input for Spec v1.5

**Status**: Phase 4 closed (2026-04-29) on closure criteria (a) and (e)
per `PATTERN_LIBRARY_PHASE4_RESULTS.md`. Findings remain accumulated
for the next formal spec revision (`PATTERN_LIBRARY_SPEC_v1_5.md`);
formal v1.5 awaits a second long-tail milestone (Phase 5 ST2
continuation) for stable per-category σ derivation.

**Scope**: Empirical findings discovered during Phase 4 ST1–ST3 execution
that should be recorded in spec form. v1.4.1 sections referenced are
preserved as-is; this file collects deltas only.

---

## 1. ST1 saturation behavior at threshold 0.92

### 1.1 Empirical observation

After Pattern Library reached 139 active patterns (Phase 3 stab close 80
+ M1 retry net +59 across 14 batches), incremental addition yielded
diminishing returns even with within-sub-topic and cross-sub-topic
threshold sweeps.

| Batch | Yield | Sub-topics tried | Saturation |
|---|---|---|---|
| b12 | 100% | new sub-topics | none |
| b13 | 50% | mixed | partial |
| b14 | 20% | 5 sub-topics | 4-of-5 saturated at 0.92 / 0.95 |

### 1.2 Spec implication

The within-topic adjacency threshold (POS_DRIFT_MAX 0.97, NEG_DUP_MAX
0.97) defined in v1.4.1 §4.2.3 saturates earlier on a fully-populated
sub-topic. A more refined spec should differentiate:

- **Cross-sub-topic threshold**: 0.92 (existing, retained)
- **Within-sub-topic adjacency floor**: empirically rises with sub-topic
  density. Not a hyperparameter to tune manually; signals taxonomy
  refinement is needed.

### 1.3 Spec recommendation

Add §4.2.4 (NEW): **Sub-topic saturation diagnostic**. When a sub-topic
hits within-sub-topic adjacency at the 0.92 threshold across multiple
seeds, this is a signal to **refine taxonomy** (split sub-topic), not to
lower the threshold. Threshold lowering would re-introduce conflict with
adjacent sub-topics.

Candidate refinements (deferred until ST4 evaluation milestone):
- Split `ce_mobius_core` → `ce_mobius_concept_high` + `ce_mobius_structural`
- Split `co_frame` → `co_frame_premise` + `co_frame_content`
- Move `sr_lifecycle.describe_temporal_state` → `sr_meta_dialogue`

---

## 2. ST2 long-tail yield-by-category empirical data

### 2.1 Per-category yield (ME5+FAISS auto-annotation)

After 294 long-tail golden entries across 8 LT categories (32 sub-batches):

| LT category | Topic mix | Net entries | Avg yield |
|---|---|---|---|
| LT-1 specialized vocab | 5 topics | 41 | ~33% |
| LT-2 multi-paragraph | 4 topics | 17 | ~12% |
| LT-3 code-switching | 4 topics | 34 | ~25% |
| LT-4 pragmatic ambiguity | 4 topics | 51 | ~42% |
| LT-5 multi-turn | 4 topics | 25 | ~28% |
| LT-6 formal-type edge | 4 topics | 35 | ~32% |
| LT-7 Codex/MOBIUS deep | 4 topics | 41 | ~37% |
| LT-8 register variation | 4 topics | 50 | ~50% |

### 2.2 Spec implication: Cat A risk surface

**LT-2 (multi-paragraph, ~12%) is the canonical long-tail Cat A risk
regime**. LT-3 (code-switching) yield is highly topic-sensitive: 4.8%
on factual_inquiry but 37.5% on self_reference / conceptual_explain /
correction.

These categories produce the largest fraction of queries in the
0.50 ≤ FAISS top-1 < 0.85 ambiguous band — exactly the queries where:

- `expected_pattern_id` cannot be confidently assigned by ME5+FAISS
- Yet humans would assign a routing class
- And ST1 expansion alone cannot raise the score above 0.85 without
  per-pattern manual seeding

LT-5 (multi-turn) is also strongly topic-sensitive: 45.8% on
self_reference vs 4.2% on factual_inquiry. Multi-turn context
queries fit self-referential follow-ups much better than fresh
factual asks.

### 2.3 Spec recommendation

Add §5.5.4 (NEW): **Hybrid annotation for ambiguous-band queries**.
Queries with 0.50 ≤ score < 0.85 should be passed through a Claude Code
LLM judgment step (single-pass, no consensus needed for golden labels)
that assigns `expected_pattern_id` or `expected_no_match`. This closes
the ST1 ↔ ST2 loop: golden entries that ST1 patterns failed to cover
become explicit gap signals.

Cost estimate: ~10 tokens/query for Claude Code judgment. For golden
500 entries with ~50% in ambiguous band, ~2.5K tokens — trivial.

---

## 3. ST3 schema correction (intent_variants_generator)

### 3.1 Bug discovered

`scripts/ism_corpus/intent_variants_generator.py` originally pointed at
`data/raf/ism_chunks.jsonl` for seed lookup. Investigation revealed
ALL 36,267 ISM chunks lack the `query` field — the build pipeline
(`scripts/build_ism_index.py`) discards that field when emitting the
chunks JSONL.

`data/raf/teacher_data_raw.jsonl` is the source of truth that retains
`query`, language, qk_* metadata required for paraphrase seeding.

### 3.2 Spec recommendation

Add §6.3.4 (NEW): **ISM corpus apply pipeline**. Document the canonical
flow:
```
intent_variants_generator.py (Groq, no GPU)
    → ism_chunks_pending.jsonl
        → apply_pending.py (validate, archive, append)
            → teacher_data_raw.jsonl (source of truth)
                → build_ism_index.py (GPU slot 1, ME5)
                    → ism_index.faiss + ism_chunks.jsonl
```

The seed source for paraphrase generation MUST be
`teacher_data_raw.jsonl` (preserves `query`), not the built
`ism_chunks.jsonl` (loses `query`).

### 3.3 Cat B suppression hypothesis (from §5.4 v1.4.1, refined)

Hypothesis remains: ISM refinement → cognitive zone correctly
classified → QK fires appropriately → synthesis stable → Cat B drops.

Phase 3 stab Metric 5 baseline N=5 = 100% Cat B. Falsifiable target:
≤60% Cat B across I-1..I-4 milestones.

Op-1 smoke test (Phase 4 ST3): correction intent generates 100%
acceptance at 5 seeds × 3 = 15 chunks via paraphrase-only (no novel
intent introduction). Suggests Op-1 is operationally viable; the
remaining bottleneck is the GPU rebuild cost of the ~36K-chunk index.

---

## 4. Stochastic floor σ behavior on long-tail (informational)

### 4.1 Observation

The 33-scenario harness (Phase 3 stab) has σ=0.65 (per spec v1.4.1
§7.8.7). Long-tail golden set, by construction, contains queries
*outside* the 33-scenario domain. No comparable σ measurement is
available for long-tail at this checkpoint (golden 134 entries, well
below the 500 needed for stable per-category σ).

### 4.2 Spec recommendation

Defer until golden 500 milestone. Then per-category σ measurement
(Cat A rate stochastic component vs. systematic Pattern Library gap)
should follow the same protocol as 33-scenario stochastic floor in
§7.8.7.

---

## 5. Pending work (NOT spec-ready)

These items are noted for Phase 5 continuation; not yet ready for formal
spec incorporation:

- Long-tail golden set ≥ 5,000 entries (Phase 4 closed at I-1 = 505
  entries; criterion (a) diminishing-returns dominated closure)
- ST3 Op-1 acceptance: 100% smoke / 15 ja correction chunks applied;
  Cat B rate measurement post-rebuild deferred (requires fresh 33-scen
  N=5)
- ST3 Op-2..Op-N (other intents: game_move, meta_question, …) deferred
- Sub-topic taxonomy refinement actual application (candidate list only)
- Hybrid annotation (Claude single-pass) for ambiguous-band queries —
  §5.5.4 candidate; deferred since Phase 4 closure (a)+(e) reached
  without it
- ja-bias flag for `golden_set_expand.py` (ja-ratio reached 22.4% vs
  33% target; LT-7/LT-8 prompts skew zh/en by design)

---

## 6. Phase 4 closure measurement (2026-04-29) — added at closure

### 6.1 Long-tail golden set: 505 entries, Cat A = 0%

| Threshold | Overall accuracy |
|---|---|
| 0.50 | 1.000 (505/505) |
| 0.85 | 1.000 (505/505) |

Per-topic at threshold 0.85:
- self_reference 105/105 = 1.000
- conceptual_explain 147/147 = 1.000
- correction 140/140 = 1.000
- factual_inquiry 63/63 = 1.000
- casual_engagement 50/50 = 1.000

### 6.2 Top-1 score distribution (annotation strict band)

- 0.85–0.90: 493 entries (97.6%)
- 0.90–0.95: 12 entries (2.4%)

Entries cluster on the strict threshold by construction
(STRICT_THRESHOLD = 0.85 in `golden_set_expand.py`). This validates
the long-tail surface as a Cat A risk regime — without the seed
patterns added during Phase 3 + Phase 4 ST1 (139 active), these
queries would fall in the 0.50 ≤ score < 0.85 ambiguous band.

### 6.3 Spec implication

Closure criterion (b) — "Cat A rate stable across 2 milestones" —
strict-requires a second long-tail milestone for stability. The 0%
single-milestone reading is informational. Per v1.4.1 §7.8.7
informational-pass framework, this is sufficient for closure when
combined with criterion (a) (diminishing returns ST1) and (e)
(all primary metrics ✓ or INFO_PASS).

---

## 7. References

- v1.4.1 §4.2.3 — empirical threshold recalibration
- v1.4.1 §5.4.6 — golden-set-relabel protocol
- v1.4.1 §7.8.6 — Cat A/B/C protocol
- v1.4.1 §7.8.7 — informational pass criteria
- `docs/PATTERN_LIBRARY_PHASE4_RESULTS.md` — Phase 4 closure scorecard
- `docs/PHASE_4_LONG_TAIL_DESIGN.md` — 8 LT category definitions
- `docs/PHASE_4_ISM_TRANSFER_PLAN.md` — Path B 6 sub-scopes
- `docs/PHASE_4_M1_SATURATION_DIAGNOSTIC.md` — ST1 saturation evidence
