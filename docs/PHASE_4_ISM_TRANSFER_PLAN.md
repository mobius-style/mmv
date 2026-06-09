# Phase 4 v2.1 — ISM Transfer Scope Plan (Path B)

**Phase 4 v2.1 Commit 6** — plan doc only, no code change.

## Path selection: Path B (large-scale refinement)

Per Commit 5 investigation (`docs/PHASE_4_ISM_CURRENT_STATE_REPORT.md`):
existing `data/raf/ism_chunks.jsonl` is 36,267 chunks — already
above Path A's upper bound (15K). Path B refines + gap-fills the
existing corpus.

## Cat B suppression hypothesis (formal articulation)

**Premise**: Phase 3 stab Metric 5 RCA classified 100 % of
33-scenario default failures as Category B (qwen3.5 LLM synthesis
variance). The Pattern Library is provably not the bottleneck.

**Hypothesis (H_ISM_CatB)**: Improving ISM intent classification
precision suppresses Cat B variance via this causal chain:

```
under-represented intent query
  ↓ (current: KNN biased toward dominant factual_query class)
classified as factual_query
  ↓
factual_query cognitive zone applied
  ↓ (mismatch with true intent)
QK fires inappropriately or with wrong parameters
  ↓
synthesis prompt is misaligned with user intent
  ↓
LLM produces verbose / off-topic / wrong-length response
  ↓ (Cat B failure surfaces in 33-scenario evaluators)
response_length_max / response_must_not_semantically_contain /
stochastic_gate failures
```

**Falsifiability**: If ISM corpus refinement (Path B operations)
does not reduce Cat B rate across milestones I-1 → I-4, the
hypothesis is falsified. Phase 5 multi-judge synthesis embedding
becomes the primary Cat B suppression candidate.

**Milestone target trajectory** (informational, hypothesis-validating):
- Baseline: 100 % Cat B (Phase 3 stab Commit 42 N=5)
- I-1 (intent rebalance): ≤ 90 %
- I-2 (qk_entitlement gap): ≤ 80 %
- I-3 (formal + lang rebalance): ≤ 70 %
- I-4 (quality + conflict): ≤ 60 %

## Path B refinement operations (6 sub-scopes)

### Op-1: Intent rebalancing via gap fill (priority HIGH)

**Goal**: lift 6 under-represented intents (correction,
meta_question, game_move, clarification, creative_request,
translation_request) to ≥ 5 % each (currently ≤ 2.5 %).

**Method**: auto-gen via Pattern Library variants generator
(adapted for intent-class generation in Commit 7); seed examples
hand-picked from existing chunks with high intent confidence
(top-K cosine vote = unanimous on the rare intent).

**Volume**: ~5,000 new examples (~833 per under-represented intent).

**Token cost**: ~5 M (variants × 30 paraphrases × 5K examples /
batch budget per Phase 1-3 norms).

**Evaluation**: per-intent KNN classification accuracy on held-out
test set ≥ 85 %.

### Op-2: qk_entitlement abstain gap fill (priority HIGH — AE core)

**Goal**: lift `qk_entitlement="abstain"` from 0.2 % (77 chunks)
to ≥ 3 % (~1,100 chunks). Critical for Answer Entitlement
Architecture's defining behavior — ISM must surface
abstention-worthy queries to the routing layer.

**Method**:
- Source 1: Pattern Library `negative_examples` already labeled as
  out-of-scope for their pattern's intent (Phase 1-3 patterns'
  negative_examples often answer "this is not within the agent's
  competence to answer"); ~500 candidates exist.
- Source 2: Codex / Reflective Economics / Code of Conscience
  documents — extract queries that the documents explicitly
  identify as abstain-worthy (e.g. "questions that exceed the
  agent's evidence base").
- Source 3: synthetic auto-gen via Groq with the seed prompt
  "queries that should trigger abstention because they exceed an
  AI's competence (privacy, prediction beyond evidence,
  speculative judgment)".

**Volume**: ~1,000 new abstain examples.

**Token cost**: ~1 M.

**Evaluation**: KNN classification of held-out abstain queries
must agree with abstain in ≥ 70 % of cases (3-NN majority vote).

### Op-3: formal_type expansion (priority MEDIUM)

**Goal**: lift `why` / `selection` / `comparison` formal types
from < 1 % to 2-3 % each.

**Method**: auto-gen variants generator targeted at formal-type-
specific phrasings:
- `why` queries: "Why does X happen / Why is X needed / なぜ X か"
- `selection` queries: "Which X / X among Y, Z / Y と Z どちら"
- `comparison` queries: "X vs Y / Compare X and Y / X と Y の違い"

**Volume**: ~3,000 examples (~1,000 per formal type).

**Token cost**: ~3 M.

### Op-4: Language rebalancing — ZH expansion (priority MEDIUM)

**Goal**: lift ZH from 18.5 % to 25-30 % (matches Pattern Library
xling target balance).

**Method**: cross-lingual generation from existing high-quality
JA/EN chunks → ZH via xling_query_generator (Phase 1-3 Pattern
Library generator, already proven 0.62 cross-lingual cosine
threshold).

**Volume**: ~3,000 new ZH chunks (translations + ZH-native variants).

**Token cost**: ~3 M.

**Evaluation**: ZH KNN classification accuracy on held-out test
set ≥ 80 % (5pp tolerance below EN/JA which are at 85 %+).

### Op-5: Quality refinement (4/5+ filter) (priority LOW)

**Goal**: quarantine existing chunks below 4/5 median across the
quality grader's 5 axes (intent specificity, fluency,
representativeness, diversity contribution, label confidence).

**Method**: apply Pattern Library quality_grader.py to existing
36,267 chunks; chunks scoring < 4 median are moved to
`data/raf/ism_chunks_quarantine.jsonl` (separate file, no
deletion). Re-grade on appeal.

**Volume**: 36,267 chunks read + scored (no new chunks generated).

**Token cost**: ~3 M (5-axis grader × 36K reads).

### Op-6: Cross-intent conflict re-labeling (priority MEDIUM)

**Goal**: identify chunks currently labeled `factual_query` that
semantically belong to under-represented intents (cross-intent
near-duplicates). Re-label via majority cosine vote against
non-factual_query intent prototypes.

**Method**: for each under-represented intent (correction,
meta_question, game_move, clarification, creative_request),
build a prototype centroid from its existing chunks; for each
factual_query chunk, compute cosine similarity to all 5 prototypes;
if max similarity > similarity to factual_query centroid + 0.05,
re-label.

**Volume**: ~5,000 factual_query chunks cross-checked.

**Token cost**: ~2 M (cosine via existing FAISS index, mostly
embedding read; no new generation).

**Evaluation**: post-relabeling intent distribution should show
factual_query ≤ 55 % (down from 64.4 %).

## Total budget

| Op | Volume | Tokens (M) | Priority |
|---|---|---|---|
| Op-1 intent rebalance | 5,000 | 5.0 | HIGH |
| Op-2 abstain gap | 1,000 | 1.0 | HIGH |
| Op-3 formal type | 3,000 | 3.0 | MEDIUM |
| Op-4 ZH rebalance | 3,000 | 3.0 | MEDIUM |
| Op-5 quality filter | 0 | 3.0 | LOW |
| Op-6 conflict relabel | 0 | 2.0 | MEDIUM |
| **Total** | 12,000 (+0 retained) | **17.0** | — |

**ST3 budget gate**: ≤ 15 M tokens (Phase 4 v2.1 §HARD CONSTRAINTS).
Total estimate is 17 M; 2 M over.

**Reconciliation**: drop Op-3 (formal_type expansion, MEDIUM
priority) to land at 14 M, leaving 1 M reserve. If Op-1 + Op-2
deliver Cat B suppression at I-2 milestone, Op-3 is unnecessary
and the reduction is justified. Op-3 deferred to Phase 5 if needed.

## Milestones

### Milestone I-1: Intent rebalance (post Op-1, post Op-2)

- Corpus size: 36,267 → 42,267 (+ 6,000 from Op-1 + Op-2)
- factual_query share: 64.4 % → ≤ 55 %
- All 6 under-represented intents ≥ 5 %
- abstain share: 0.2 % → ≥ 3 %
- ISM index rebuild (GPU slot 1 only per HARD CONSTRAINT 5)
- Baseline 33-scenario N=5 measure for Cat B trajectory

### Milestone I-2: Language rebalance (post Op-4)

- Corpus size: 42,267 → 45,267 (+ 3,000 ZH)
- ZH share: 18.5 % → ≥ 25 %
- ISM index rebuild
- 33-scenario N=5 Cat B measure (target ≤ 80 %)

### Milestone I-3: Quality + conflict (post Op-5, post Op-6)

- Corpus size: 45,267 (with possible quarantine of low-quality
  chunks; effective size unchanged or slightly less)
- factual_query share post-relabeling: ≤ 50 %
- Quarantined chunks count documented
- ISM index rebuild
- 33-scenario N=5 Cat B measure (target ≤ 60 %)

### Milestone I-4 (deferred): Op-3 if budget remains

- formal_type expansion if Cat B not at target after I-3
- Otherwise Phase 5 deferred

## Index rebuild protocol (GPU slot 1 only — HARD CONSTRAINT 5)

Per Phase 4 v2.1 §HARD CONSTRAINTS 5:

```bash
# Pre-rebuild: verify slot 2 idle
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,power.draw --format=csv
# Confirm GPU 1 (slot 2) utilization ≈ 0%, memory.used minimal

# Pin to slot 1
export CUDA_VISIBLE_DEVICES=0

# Rebuild
python3 scripts/build_ism_index.py  # or equivalent

# Post-rebuild: unset env, sanity check
unset CUDA_VISIBLE_DEVICES
nvidia-smi
```

Rebuild required after each milestone Op completion. Rebuild
duration estimate: ~10 min for 36K → 45K corpus on slot 1 only.

## Authoring location

ISM-specific corpus modifications happen at the data layer:
- `data/raf/ism_chunks.jsonl` — main corpus, append + relabel
- `data/raf/ism_chunks_quarantine.jsonl` — quarantine of failed
  Op-5 entries (NEW file)
- `data/raf/ism_index.faiss` — rebuilt per milestone

`src/adapters/raf/profile.py` is **PROTECTED** per HARD CONSTRAINT
3 — the adapter contract is unchanged; only the data it reads
changes.

## Cat B measurement methodology

Per Phase 3 stab Commit 42 protocol (`scripts/classify_metric5_failures.py`):

1. Run `python3 scripts/run_33_scenarios.py --n-runs 5 --output /tmp/ism_milestone_<I>_default.json`
2. Run `python3 scripts/classify_metric5_failures.py --input <output>`
3. Record Cat B percentage in milestone report
4. Compare to prior milestone trajectory; flag regressions

## Risks

1. **Cat B does not decrease** (hypothesis falsified) — accept
   informational-pass on Phase 4 closure; Phase 5 multi-judge
   synthesis becomes Cat B suppression primary.
2. **Auto-gen acceptance < 50 %** for under-represented intents
   (their seeds may be too few for high-quality variant generation)
   — apply Phase 4 v2.1 per-batch acceptance protocol; halt if
   3 batches consecutive < 50 %.
3. **GPU saturation during index rebuild** — strict adherence to
   slot 1 only protocol prevents this; nvidia-smi pre-check
   mandatory.
4. **factual_query relabel collateral damage** (Op-6) — keep
   relabel threshold conservative (similarity margin > 0.05);
   manual review of first 100 relabel candidates before bulk apply.

## Out of scope (Phase 5 deferral)

- ISMProfile.retrieve() algorithm changes (KNN K tuning, weighted
  voting) — adapter is protected
- ISM-adaptive QK injection refinement at runtime (Phase 5 if
  H_ISM_CatB validated)
- Multi-judge synthesis embedding (Phase 5 if H_ISM_CatB falsified)
