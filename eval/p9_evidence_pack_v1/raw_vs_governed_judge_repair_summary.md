# Test 2 Judge Repair Pass — summary

- N total: 60
- N judged ok: 60
- N judge fail: 0
- Judge: `gpt-oss:20b` via Ollama (local)
- Originally intended: Groq `openai/gpt-oss-120b` (unavailable: HTTP 403)
- Raw mean (0–20):      **15.45**
- Governed mean (0–20): **15.55**
- Δ (governed − raw):   **+0.10**
- P9 thesis signal:     **INCONCLUSIVE**

## Per-axis means (0–4)

| Axis | raw | governed | Δ |
|---|---|---|---|
| route_accuracy | 3.12 | 2.93 | -0.19 |
| answer_correctness | 3.4 | 3.13 | -0.27 |
| restraint_quality | 3.0 | 3.32 | +0.32 |
| conciseness | 2.78 | 3.45 | +0.67 |
| overall_usefulness | 3.15 | 2.72 | -0.43 |

## Per-category (mean total 0–20)

| category | n | raw | governed | Δ | wins (raw/gov/tie) |
|---|---|---|---|---|---|
| ambiguous_underspecified | 18 | 14.22 | 17.39 | 3.17 | 9/8/1 |
| continuation | 8 | 12.62 | 19.38 | 6.75 | 3/5/0 |
| specialized_terminology | 6 | 17.83 | 9.67 | -8.17 | 4/2/0 |
| conceptual_explanation | 8 | 18.88 | 11.88 | -7.0 | 8/0/0 |
| correction_rewrite | 8 | 16.12 | 16.25 | 0.12 | 6/2/0 |
| factual_inquiry | 10 | 14.3 | 16.2 | 1.9 | 5/4/1 |
| casual_smalltalk | 2 | 20.0 | 10.0 | -10.0 | 1/0/1 |

## Caveats

- Post-hoc judge-only pass. Raw and governed responses were captured during the original Phase 5C Test 2 run and are not regenerated here.
- The judge generation conditions in the original Phase 5C Test 2 are not changed by this pass.
- Single-judge limitation: no inter-judge consensus.
- Vendor / model-family overlap: the judge (gpt-oss:20b) is the openai/gpt-oss family; the originally intended Groq judge was openai/gpt-oss-120b. The locally-hosted judge runs on different infrastructure (Ollama, no Groq dependency) but shares the upstream weights family.
- Length-bias guard explicitly included in the judge prompt, but residual length bias cannot be fully ruled out without a multi-judge sweep.
- Same base model (huihui_ai/qwen3.5-abliterated:9b) on both raw and governed sides; the intentional variable is the MMV governance layer.
- Sampling oversamples ambiguous + factual; not representative of an evenly-weighted natural distribution.
- This is NOT Phase 6 full evaluation. NOT deployment-wide validation. NOT real UI performance validation.
