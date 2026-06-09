# Phase 4 Long-tail Query Type Design

**Phase 4 v2 Commit 2** — design doc only, no code change.

## Motivation (Phase 3 stab finding reflection)

Phase 3 stab Metric 5 RCA conclusively showed:
- 100% Category B (qwen3.5 LLM synthesis variance)
- 0% Category A (Pattern Library routing decision)

Within the 33-scenario domain, the Pattern Library is already
functional (Cat A = 0). Phase 4 物量 (volume) effect on routing
accuracy is therefore expected to manifest in **long-tail queries**
— query types the 33-scenario harness does not cover.

This document identifies those long-tail query types so that:
- **Sub-thread 1 (Pattern Library)** can target sub-topic
  expansion at long-tail-relevant sub-topics
- **Sub-thread 2 (Golden set)** can populate primary evaluation
  surface with long-tail entries (60%→70%→80% long-tail ratio
  across milestones)
- **Closure judgment criterion (b)** (long-tail Cat A rate at low
  water mark) has a measurable target

## 33-scenario domain — what's already covered

Reference: `tests/scenarios/*.yaml` (33 scenarios across 11
categories × 3 languages):

- self_reference / identity_stability / persona_drift
- factual_general / factual_hard / factual_krillin
- correction
- mixed
- casual_greeting
- volatile
- word_chain

These exercise short, well-formed, monolingual queries with clear
intent. The Pattern Library covers them already (Cat A = 0).

## Long-tail categories (out-of-33-scenario domain)

### LT-1: 専門用語混入 query (specialized-vocabulary contamination)

Queries that mix everyday phrasing with domain-specific terminology
that may confuse the appraiser or routing.

Sample queries:
- "Phase 3 で Cat A は 0 でしたよね、私の理解は正しい？"
- "MOBIUS の box_w は wikipedia へ FAISS で IVFPQ retrieval する"
  "という認識で合ってますか"
- "RAFT corpus を fine-tune に使うのが ISM transfer の path B"
  "でいいですか"
- "Spec v1.4.1 の 7.8.7 は informational pass の formal criteria"
  "ですよね"
- "あなたの Constitutional Invariants の 4 番目って何でしたっけ"

Sub-thread mapping:
- Sub-thread 1: ce_mobius_core, ce_mobius_components,
  ce_mobius_methodology, sr_architecture
- Sub-thread 2: 60-70% of MOBIUS-specific golden entries

### LT-2: Multi-paragraph query (multi-paragraph context-bearing)

Queries that span multiple paragraphs, with the actual question
buried in or following extensive context-setting.

Sample queries:
- (3-paragraph technical setup) ... "では、この場合の最適 routing は？"
- (long narrative about a project) ... "次のステップとしてどう進める"
  "べきか教えて"
- "Yesterday I was reviewing X. Today I tried Y. Yesterday Z worked"
  "but today it doesn't. What should I check first?"

Challenge: appraiser must extract intent from late-position
question; the prefix may activate Box W retrieval inappropriately.

Sub-thread mapping:
- Sub-thread 2: 5-10% of golden set (multi-paragraph variants)

### LT-3: Mixed-language code-switching

Queries that intra-sententially mix JA/ZH/EN.

Sample queries:
- "Box 0 についてもう少し explain してくれる？"
- "MOBIUS の query routing は essentially regex-first だよね"
- "What is the 役割 of this function"
- "FAISS index の rebuild かかる時間 about how long"
- "这个 endpoint 返回的 JSON 中 status field 是什么意思"

Sub-thread mapping:
- Sub-thread 1: cross-lingual coverage in all sub-topics
  (concentrated in fi_definition / ce_mobius_components /
  sr_capabilities)
- Sub-thread 2: 8-12% of golden set (code-switching variants)

### LT-4: Pragmatically ambiguous query (literal vs intent)

Queries where literal interpretation differs from speaker intent.
Common pattern: rhetorical questions, indirect requests,
conventionalized politeness.

Sample queries:
- "Can you tell me what time it is" (literal yes/no vs implicit time request)
- "I wonder if it would be possible to check this" (indirect request)
- "Don't you think this is wrong" (rhetorical/seeking agreement vs
  genuine question)
- "なんか変じゃない？" (ambiguous: question / observation / complaint)
- "ちょっと聞いてもいい？" (politeness frame, not an actual permission request)

Sub-thread mapping:
- Sub-thread 1: cg_small_talk, cg_thanks, co_polite
- Sub-thread 2: 5-8% of golden set (ambiguity test entries)

### LT-5: Multi-turn context-dependent query

Queries whose meaning depends on prior turns (anaphora, ellipsis,
"that one"/"the other" references, vague continuation).

Sample queries (require prior turn context):
- (turn N: "What's the routing engine") (turn N+1: "And what about
  the box selector")
- ("Tell me about Box 0") ("もっと教えて")
- ("Show me the schema") ("And the validator?")
- ("What's the difference") ("ja で") — language-switch
- ("Code reviewed yesterday") ("How was today's?")

Challenge: bare aspect questions, language switches, vague
continuations need prior-turn-aware appraisal.

Sub-thread mapping:
- Sub-thread 2: 5-10% of golden set (require multi-turn context
  fields in jsonl entries)

### LT-6: Edge-case formal types

Queries that span the boundary between formal types (mathematical
notation, code snippets, structured queries, list-only inputs).

Sample queries:
- "f(x) = 2x+1, x=3 のとき f(x) は？"
- "```python\\ndef hello(): return 'world'\\n```\\n これ正しい？"
- "List 3 differences: A, B, C"
- "1) X 2) Y 3) Z はどれが該当する"
- "{key: value} の意味は"

Sub-thread mapping:
- Sub-thread 1: ce_programming, fi_specialized
- Sub-thread 2: 3-5% of golden set (formal-type edge cases)

### LT-7: Domain-specific (Codex / Reflective Economics / Code of Conscience)

T-specific domain content from `corpus/Codex_v1.txt` and related
documents. These are MOBIUS-internal but deeper than the 33-scenario
ce_mobius_components level.

Sample queries:
- "Reflective Economics の三層構造を説明して"
- "Code of Conscience の七つの公理は"
- "L1-L8 の階層理論はどこに記述されている"
- "Codex v1 で言う sustained reflection とは"
- "Box Σ の存在意義について"

Sub-thread mapping:
- Sub-thread 1: ce_mobius_methodology, ce_humanities (some)
- Sub-thread 2: 8-12% of golden set (Codex-derived content)

### LT-8: Linguistic register variations

Same intent expressed across linguistic registers (formal /
casual / dialectal / honorific / archaic).

Sample queries:
- 敬語: "教えていただけますでしょうか"
- 普通体: "教えて"
- タメ口: "教えてくれや"
- 関西弁: "教えてくれへん？"
- Old-formal: "ご教示願いたく存じます"
- Internet/SNS: "教えて w"
- Honorific ZH: "请告知"
- Casual ZH: "告诉我"
- Archaic EN: "Pray tell"

Sub-thread mapping:
- Sub-thread 1: covers all 6 topics with register variants
- Sub-thread 2: 5-8% of golden set (register tests)

## Long-tail ratio milestones (Sub-thread 2)

Per Phase 4 v2 prompt §STEP 4:

| Pattern Library milestone | Golden set size | Long-tail ratio |
|---|---|---|
| 1,000 patterns | 500 entries | 60% |
| 3,000 patterns | 1,500 entries | 65% |
| 5,000 patterns | 2,500 entries | 70% |
| 10,000 patterns | 5,000 entries | 80% |

The ratio rises across milestones because the Pattern Library at
80 → 1,000 still benefits from saturating "standard" coverage; once
above 5,000 the marginal value is in long-tail.

## Distribution targets within long-tail (5,000-entry endpoint)

| Long-tail category | Target % | Approx entries |
|---|---|---|
| LT-1 specialized vocabulary | 25% | 1,250 |
| LT-2 multi-paragraph | 7% | 350 |
| LT-3 code-switching | 12% | 600 |
| LT-4 pragmatic ambiguity | 7% | 350 |
| LT-5 multi-turn context | 8% | 400 |
| LT-6 formal-type edge | 4% | 200 |
| LT-7 Codex/RE/CoC domain | 12% | 600 |
| LT-8 register variation | 7% | 350 |
| (residual: standard) | 18% | 900 |

## Cat A measurement protocol (per milestone)

For each long-tail category:

1. Sample 50 queries
2. Run via `route_via_pattern_library` (or end-to-end engine
   simulation) at the milestone's library state
3. Classify each result:
   - Cat A: Pattern Library routing decision wrong (library
     intercepts when it shouldn't, library matches wrong sub-topic,
     library misses when it should match)
   - Cat B: routing correct + downstream LLM synthesis variance
   - Cat C: env / infra / classification ambiguity
4. Per-category Cat A rate
5. Aggregate Cat A rate across all 8 categories

Closure criterion (b): aggregate long-tail Cat A rate < 5%
maintained for 2 consecutive milestones.

## Authoring sources (Sub-thread 2 generation method)

- 50% auto-gen via Pattern Library generators with category-specific
  prompts (e.g. "generate 30 queries that mix JA/ZH/EN code-switching
  for the topic factual_inquiry sub-topic fi_definition")
- 30% reverse-engineering from Phase 1-3 patterns + sub-topic
  expansion: take a pattern's `examples`, transform with category
  generator (multi-paragraph wrapper, code-switching insertion,
  register shift)
- 20% Claude Code authored edge cases + Codex/RE/CoC content
  extraction

Quality 4/5+ filter, label desync prevention (Phase 2 Cycle 1
protocol continues).

## Phase 4 closure judgment alignment

Long-tail design surfaces three primary metrics for closure:

| Metric | Closure relevance |
|---|---|
| Long-tail golden set size ≥ 5,000 | Phase 4 closure metric 11 |
| Long-tail Cat A rate < 5% (2 consecutive milestones) | Closure criterion (b) |
| Per-sub-topic accuracy ≥ 80% on long-tail entries | Closure metric 14 |
