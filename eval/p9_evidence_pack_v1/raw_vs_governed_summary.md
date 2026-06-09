# Test 2 — Raw vs Governed (P9 Evidence Pack v1)

- N (total): 60
- N (judged ok): 0
- Raw overall mean (1–5):      0.000
- Governed overall mean (1–5): 0.000
- Delta (governed − raw):      +0.000
- Signal: **INCONCLUSIVE_NO_JUDGE**

## Per-category

| Category | n | raw_mean | gov_mean | delta | wins (raw/gov/tie) |
|---|---|---|---|---|---|
| ambiguous_underspecified | 18 | 0.0 | 0.0 | 0.0 | 0/0/18 |
| continuation | 8 | 0.0 | 0.0 | 0.0 | 0/0/8 |
| specialized_terminology | 6 | 0.0 | 0.0 | 0.0 | 0/0/6 |
| conceptual_explanation | 8 | 0.0 | 0.0 | 0.0 | 0/0/8 |
| correction_rewrite | 8 | 0.0 | 0.0 | 0.0 | 0/0/8 |
| factual_inquiry | 10 | 0.0 | 0.0 | 0.0 | 0/0/10 |
| casual_smalltalk | 2 | 0.0 | 0.0 | 0.0 | 0/0/2 |

## Confounds

- Single-judge limitation: no inter-judge consensus.
- Judge vendor overlap with the project's auto-gen pipeline (Groq).
- Raw and Governed share the SAME base inference model (qwen3.5-abliterated:9b); the only intentional difference is the MMV governance layer (system prompt, routing, retrieval).
- Sampling skews toward ambiguous + factual to surface the governance-restraint signal; results are NOT representative of an evenly-weighted natural distribution.
- Judge sees outputs blinded as A/B with random per-query assignment; un-blinding key is recorded in per_query.jsonl.
