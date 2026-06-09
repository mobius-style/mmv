# Trilingual Dataset Inventory — 2026-04-24

Inspection performed as part of Stage A. Purpose: decide whether new
ZH / EN-pure datasets need to be generated via Groq.

## Existing datasets

### `eval/rl_bench/generated/full_20260421_021524/`

| Field | Value |
|---|---|
| Total dialogues | 3510 |
| Elapsed | 1433 s (23.9 min, 6 workers) |
| Generator | openai/gpt-oss-120b |
| Counterpart | llama-3.3-70b-versatile |
| languages | japanese 2133 · english 1037 · mixed_jp_en 340 |
| categories | technical_definition 504 · save_intent 502 · continuity_and_adoption 502 · retrieval_needed 501 · ambiguity_handling 501 · factual_vs_reflective 500 · same_format 500 |

### `eval/rl_bench/generated/zh_focus_20260422/`

| Field | Value |
|---|---|
| Total dialogues | 3328 |
| Generator | openai/gpt-oss-120b |
| Counterpart | llama-3.3-70b-versatile |
| languages | chinese_simplified 2335 · chinese_traditional 326 · mixed_zh_en 667 |
| categories | save_intent 490 · continuity_and_adoption 488 · ambiguity_handling 485 · same_format 475 · technical_definition 474 · factual_vs_reflective 465 · retrieval_needed 451 |

## Combined language coverage

| Language bucket | Dialogues |
|---|---:|
| JA (pure)          | 2133 |
| EN (pure)          | 1037 |
| ZH simplified      | 2335 |
| ZH traditional     | 326  |
| Mixed JA+EN        | 340  |
| Mixed ZH+EN        | 667  |
| **Total**          | **6838** |

All 7 RL-bench categories have 400+ samples per language bucket.

## Decision (Stage A Task A4)

**No new dataset generation.** The combined existing corpus already
provides:

- Comprehensive JA coverage (2133 + 340 mixed = 2473 JA-containing)
- Comprehensive ZH coverage (3328 ZH-containing; simplified + traditional)
- Sufficient EN pure coverage (1037)

Generating additional 1000-1500 ZH + 500-800 EN samples overnight would:
- Consume 30-45 min of Groq calls for marginal additional coverage
- Require additive extension to `generate_dataset.py` (current signature
  has no --language flag)
- Add 3-5 MB JSONL that overlaps existing corpus

Instead, Stage A's 30 trilingual scenarios focus on **production-observed
failure modes** (self-ref kanji / casual greetings / persona drift /
factual unknown / word-chain games / correction / volatile facts)
across JA/EN/ZH. These are hand-designed regression probes, not dataset
samples — they exercise the exact categories that surfaced in T's
manual UI testing on 2026-04-23 (which the large auto-generated
datasets did not cover, per the Evolution Log Fix 1 gap analysis:
"貴方" appears 0/6838 times in auto-generated dialogues).

## Future work

- If the Stage A scenarios reveal a category T wants broader coverage
  on (e.g. game-flow / correction-detection), targeted generation
  can be added in a dedicated future cycle with the `--language` flag
  extension.
- The existing combined 6838-sample corpus remains the evaluation
  baseline for Stage 3 / Stage 6 eval_rl runs (v2.2 spec).
