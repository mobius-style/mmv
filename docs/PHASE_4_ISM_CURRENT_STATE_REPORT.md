# Phase 4 v2.1 — ISM Current State Investigation

**Phase 4 v2.1 Commit 5** — investigation report only, no code change.

## Subject

ISMProfile (Intent Stratification Model) is the KNN-based intent
classifier in `src/adapters/raf/profile.py`. Phase 4 Sub-thread 3
proposes ISM corpus expansion / refinement to suppress Category B
(qwen3.5 LLM synthesis) variance via better cognitive-zone judgment.
This investigation establishes the **scope and path** for that
work before any expansion is initiated.

## Findings

### Index size

- **`data/raf/ism_index.faiss`**: 36,267 vectors (FAISS IndexFlat)
- **`data/raf/ism_chunks.jsonl`**: 36,267 chunks, 1:1 with index
- Embedding: `intfloat/multilingual-e5-large`, "query: " prefix,
  device=cuda:0, normalized

This is already a **large** corpus — much larger than the 80
patterns of the Pattern Library, and significantly above the
Phase 4 v2.1 prompt's Path A "expansion to 数千-15,000 examples"
target. Path A is **not applicable**; existing corpus already at
2× the upper bound of Path A.

### Intent distribution (10 intent types)

| intent_type | count | % | over/under |
|---|---|---|---|
| factual_query | 23,373 | 64.4 % | severely over-represented |
| instruction_request | 6,287 | 17.3 % | over-represented |
| topic_continuation | 1,450 | 4.0 % | balanced |
| casual_greeting | 1,245 | 3.4 % | balanced |
| clarification | 895 | 2.5 % | under-represented |
| creative_request | 767 | 2.1 % | under-represented |
| translation_request | 757 | 2.1 % | under-represented |
| meta_question | 637 | 1.8 % | under-represented |
| correction | 436 | 1.2 % | severely under-represented |
| game_move | 420 | 1.2 % | severely under-represented |

**Skew analysis**: factual_query alone holds 64.4 % of mass; the
6 lowest intents combined (≤ 2.5 % each) hold only 12.9 %. KNN
voting is biased toward the dominant class.

### formal_type distribution (7 types)

| formal_type | count | % |
|---|---|---|
| how | 15,874 | 43.8 % |
| what | 14,935 | 41.2 % |
| other | 3,117 | 8.6 % |
| yesno | 1,844 | 5.1 % |
| why | 242 | 0.7 % |
| selection | 141 | 0.4 % |
| comparison | 114 | 0.3 % |

`how` + `what` together hold 85 %; `why`/`selection`/`comparison`
are essentially absent. This is a structural under-coverage.

### Language distribution

| language | count | % |
|---|---|---|
| en | 16,772 | 46.2 % |
| ja | 12,774 | 35.2 % |
| zh | 6,721 | 18.5 % |

ZH significantly under-represented. Ratio target should be closer
to 33/33/33 for Pattern Library coordination (Pattern Library aims
for balanced JA/ZH/EN).

### qk_entitlement near-monoculture

| qk_entitlement | count | % |
|---|---|---|
| answerable | 36,190 | 99.8 % |
| abstain | 77 | 0.2 % |

**Critical coverage gap**: `abstain` (the value that drives Answer
Entitlement Architecture's defining behavior — refusing to answer
when not justified) appears in only 0.2 % of the corpus. This
weakens KNN's ability to identify abstain-worthy queries via
neighbor vote.

### qk_tvs_estimate compression

| qk_tvs_estimate | count | % |
|---|---|---|
| medium | 27,837 | 76.8 % |
| low | 7,215 | 19.9 % |
| high | 1,215 | 3.4 % |

`medium` dominates; `high` (high TVS — significant correction
needed) is rare. Lacks the signal needed to differentiate
high-TVS routing.

### Heuristic fallback (routing_engine `_infer_intent_type`)

`src/kernel/routing_engine.py:564-617` defines a 5-branch fallback
heuristic for when ISMProfile is unavailable or low-confidence:
1. self_referential → meta_question (Fix 1 priority)
2. casual greeting fast-path → casual_greeting
3. ISMProfile.intent_type if confident
4. Creative regex → creative_request
5. Default → factual_query

The fallback default = `factual_query`, the dominant class. This
hides ISM under-representation issues at runtime — when ISM is
inconclusive, queries get classified as factual_query, reinforcing
the dominance.

## Cat B suppression strategic value (Phase 3 stab finding)

Per Phase 3 stab Metric 5 RCA: 100 % of harness failures were
Category B (qwen3.5 synthesis variance). The **hypothesis** is
that ISM precision improvements suppress Cat B via:

1. Better intent classification → correct cognitive zone
   (per spec, intent → cognitive zone mapping drives QK firing)
2. Correct cognitive zone → appropriate QK injection
3. Appropriate QK → synthesis stability (response length /
   semantic content variability reduced)

For this hypothesis to hold, the ISM must classify with high
confidence on the **rare-intent** queries that currently default
to factual_query and inappropriately route through Box W. The
under-represented intents (correction, meta_question, game_move,
clarification) are the most-likely Cat B contributors — their
queries today are drowned by factual_query KNN voting and end up
in factual synthesis paths regardless of intent.

## Path A vs Path B decision

Per Phase 4 v2.1 prompt §STEP 2 Commit 6:

- **Path A (small-scale expansion 80 → 数千-15,000 via
  Pattern-Library-style auto-gen)**: NOT APPLICABLE. Existing
  corpus is already 36,267 — well above Path A's upper bound. A
  Path A approach would only add 4-15 K to a 36 K base, marginally
  improving distribution.

- **Path B (large-scale refinement of existing 36 K corpus +
  targeted gap fill)**: APPLICABLE. The corpus has clear quality
  issues (intent skew, language skew, qk_entitlement near-mono,
  formal_type skew) that refinement-class operations can address.

**Recommendation: Path B.**

## Path B sub-scope (Commit 6 will articulate)

Three concrete refinement operations Path B should cover:

1. **Intent rebalancing via gap fill**: auto-gen ~3-5 K examples
   for the 6 under-represented intents (correction, meta_question,
   game_move, clarification, creative_request, translation_request)
   to lift each toward 5-8 % share. Generators reuse Pattern Library
   pipeline (Phase 4 v2.1 Commit 7).

2. **qk_entitlement abstain gap**: gap fill ~500-1,000 examples
   labeled `qk_entitlement="abstain"` to surface refusal-worthy
   queries to KNN. Source: Phase 1 Pattern Library negative_examples
   already labeled as out-of-scope; Codex/RE/CoC content with
   abstain-relevant queries.

3. **formal_type expansion**: gap fill `why`/`selection`/`comparison`
   to ~2-3 % each (currently < 1 %).

4. **Language rebalancing**: ZH expansion via Pattern Library xling
   generator output (currently 18 % → target 25-30 %).

5. **Quality refinement (4/5+ filter)**: apply Pattern Library
   quality_grader to existing 36 K corpus; quarantine entries
   below 4/5 median across the 5 axes.

6. **Cross-intent conflict checker**: identify near-duplicate
   chunks across intents (e.g. queries currently labeled
   `factual_query` that semantically belong in `meta_question`)
   and re-label via majority cosine vote. This addresses the
   factual_query over-dominance directly.

## Token budget for Path B (Sub-thread 3)

Per Phase 4 v2.1 prompt: ST3 ≤ 15M Groq tokens.

Estimated Path B sub-scope cost:
- Intent gap fill (~5 K examples × 3-axis grader): ~5 M tokens
- abstain gap fill (~1 K examples): ~1 M tokens
- formal_type / language rebalance (~3 K examples): ~3 M tokens
- Quality refinement (5-axis filter): ~3 M tokens (read-only of
  existing corpus + grader inference)
- Conflict re-labeling (~5 K queries cross-checked): ~2 M tokens
- **Total estimate: ~14 M tokens**

Within budget; ~1 M reserve for retries / batch failures.

## Cat B suppression measurement plan (Phase 4 ST3 milestones)

Per Phase 4 v2.1 prompt §STEP 5: at each ISM milestone, measure
Cat B rate on 33-scenario default to validate the suppression
hypothesis. Baseline (Phase 3 stab Commit 42 N=5):

| Cat | Count | % |
|---|---|---|
| A | 0 | 0 % |
| B | 13 | 100 % |
| C | 0 | 0 % |

Target trajectory (informational, hypothesis-validating):
- Milestone I-1 (intent rebalance): Cat B 100 % → ≤ 90 %
- Milestone I-2 (qk_entitlement gap fill): ≤ 80 %
- Milestone I-3 (formal + lang rebalance): ≤ 70 %
- Milestone I-4 (quality + conflict): ≤ 60 %

If Cat B does NOT decrease across milestones, the hypothesis is
falsified — Phase 5 multi-judge synthesis embedding becomes the
primary Cat B suppression path.

## Phase 4 ST3 deliverable summary

- **Path: B (refinement)**
- **Scope: 5 refinement operations** above
- **Budget: ~14 M Groq tokens**
- **Milestones: I-1 to I-4**
- **Closure metric**: Cat B trajectory + per-intent accuracy on
  test set ≥ 85 %
- **HARD CONSTRAINT**: this work must NOT touch
  `src/adapters/raf/profile.py` (per Phase 4 v2.1 §HARD CONSTRAINTS
  3 — `src/adapters/*` protected). Corpus modifications happen at
  the data layer (`data/raf/ism_chunks.jsonl` → new corpus file),
  not the adapter. Index rebuild via existing build script with
  GPU slot 1-only constraint per Phase 4 v2.1 §HARD CONSTRAINTS 5.
