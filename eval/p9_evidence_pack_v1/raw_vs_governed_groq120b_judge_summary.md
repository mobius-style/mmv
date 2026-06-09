# Test 2 Groq 120B Judge Pass — summary

- N total: 60
- N judged ok: 57
- N judge fail: 3
- Judge: `openai/gpt-oss-120b` via Groq (User-Agent fix applied)
- Raw mean (0–20):      **15.68**
- Governed mean (0–20): **15.25**
- Δ (governed − raw):   **-0.44**
- P9 thesis signal:     **WEAKLY_WEAKENS**
- Token usage (Groq):   prompt=55234, completion=27350, total=82584

## Per-axis means (0–4)

| Axis | raw | governed | Δ |
|---|---|---|---|
| route_accuracy | 3.26 | 2.98 | -0.28 |
| answer_correctness | 3.47 | 3.09 | -0.38 |
| restraint_quality | 3.09 | 2.98 | -0.11 |
| conciseness | 2.67 | 3.35 | +0.68 |
| overall_usefulness | 3.19 | 2.84 | -0.35 |

## Per-category (mean total 0–20)

| category | n | raw | governed | Δ | wins (raw/gov/tie) |
|---|---|---|---|---|---|
| ambiguous_underspecified | 18 | 14.39 | 17.67 | 3.28 | 6/12/0 |
| continuation | 8 | 12.0 | 19.75 | 7.75 | 1/7/0 |
| specialized_terminology | 6 | 18.5 | 9.0 | -9.5 | 4/2/0 |
| conceptual_explanation | 8 | 19.0 | 10.38 | -8.62 | 7/0/1 |
| correction_rewrite | 8 | 14.0 | 13.0 | -1.0 | 5/2/1 |
| factual_inquiry | 10 | 12.6 | 13.1 | 0.5 | 3/3/4 |
| casual_smalltalk | 2 | 19.0 | 10.5 | -8.5 | 1/1/0 |

## Caveats

- Post-hoc judge-only pass. Raw and governed responses were generated before the judge access repair; they were NOT regenerated. The original Phase 5C Test 2 generation conditions are unchanged.
- The User-Agent fix changes only the HTTP header on judge requests. It does not affect generated responses or any other code path.
- Single-judge limitation remains: no inter-judge consensus.
- Groq 120B judge is stronger than the local 20B fallback but is still not a multi-judge consensus.
- Length-bias guard explicitly included in the judge prompt.
- Same base model on both raw and governed sides; the intentional variable is the MMV governance layer.
- Sampling oversamples ambiguous + factual; not representative of an evenly-weighted natural distribution.
- NOT Phase 6 full evaluation. NOT deployment-wide validation. NOT real UI performance validation.
