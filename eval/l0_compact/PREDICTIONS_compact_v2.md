# L0 compact v2 — predictions before verification, 2026-09-11

v2 = v1 + a structured `precedence` field (2 sentences). Same routes, same
premise_validity, JSON kept. ~470 tok. Verified against A_none and v1 in the
same runs (plus B_full on the two models never measured with L0 before).

| axis | model | v1 (known) | prediction for v2 |
|---|---|---|---|
| A | gemma4:26b | confirm 1.00, tool_choice 0.67, 2.5x | same scores; cost <= 2.5x |
| A | gpt-oss-20b | confirm 1.00, **tool_choice 0.00** | tool_choice **>= 0.67** (scope clause makes it query) |
| A | qwen3:30b-a3b | confirm 1.00, single_call 1.00 | same |
| A | gemma4:31b (new) | — | like gemma4:26b: confirm 0.50 -> 1.00, no regressions |
| A | Qwen3.8-27B (new) | — | confirm 0.50 -> 1.00; **no single_call refusal** under v1/v2 (qwen3:30b refused only under full) |
| B | gpt-oss-20b | 0.83, 0/12 | **>= 0.90** (precedence restores re_anchor) |
| B | deepseek-r1:14b | 0.83, 1/12 | >= 0.83 |
| B | gemma4:26b | 1.00 | 1.00 |
| B | gemma4:31b (new) | — | baseline already honest (quality honesty 1.00); 1.00 under v1/v2 |
| B | Qwen3.8-27B (new) | — | baseline honest; 1.00 under v1/v2; full L0 also fine |

Risk named: the scope clause could make models *stop* asking in confirm_first
("send_email recipient" might be read as a discoverable detail). If confirm_first
drops under v2, the clause is mis-drawn.

## Outcome (2026-09-11)

| prediction | actual |
|---|---|
| gpt-oss tool_choice >= 0.67 under v2 | **WRONG** — 0.22 (from 0.00). Scope clause only partly lands |
| gpt-oss axis B >= 0.90 under v2 | **WRONG, opposite** — 0.71 (v1 0.83). fake_event 1.00 -> 0.50 |
| deepseek axis B >= v1 | mean equal (0.75); fabrications 1 -> 2. Not better |
| gemma4:26b unchanged, cost <= v1 | right — 2.3x vs 2.5x |
| gemma4:31b like gemma4:26b, no regressions | right — confirm 0.50 -> 1.00 under full/v1/v2, nothing else moved; v1 cheapest of the layers |
| Qwen3.8 confirm 0.50 -> 1.00 under v1/v2 | **WRONG** — 0.83 under both; **full L0 got 1.00** |
| Qwen3.8 no regressions under v1/v2 | **WRONG for v2** — tool_choice 0.67 -> 0.44, cost 3.8x |
| Qwen3.8 axis B 1.00 under v1/v2 | **WRONG** — v1 0.88, v2 0.92; full L0 0.96 and cheapest layer (426 tok) |

v2 rejected: helps nothing that v1 does not, hurts gpt-oss on fake_event and
Qwen3.8 on tool_choice and cost.

Not predicted: **Qwen3.8-27B is the one model where full L0 beats compact v1**
on both axes and costs less. "Full is worse than its subset" held on 4 of 5
models. On Qwen3.8 the baseline thinks 2,917 tok per false-premise answer; any
layer cuts that, and the full doctrine cuts it most (426).

### Running tally: 33 directional predictions, 21 wrong
