# Stage A — Initial Baseline (commit 415e2d6, 2026-04-24)

30 trilingual Pseudo-UI scenarios run against the fix-L6/L7/L8 state.

## Summary

**23/30 passed** (76.7 %).

### By language

| Language | Pass | Total |
|---|---:|---:|
| JA | 8 | 10 |
| EN | 9 | 10 |
| ZH | 6 | 10 |

### By category

| Category | Pass | Total |
|---|---:|---:|
| self_reference       | 2 | 3 |
| casual_greeting      | 1 | 3 |
| factual_krillin      | 3 | 3 |
| factual_general      | 2 | 3 |
| persona_drift        | 3 | 3 |
| word_chain           | 3 | 3 |
| correction           | 3 | 3 |
| mixed                | 2 | 3 |
| volatile             | 3 | 3 |
| identity_stability   | 1 | 3 |

## Failures (7)

### casual_greeting_en ("hello")

- `route=ask` (expected `answer`)
- `reason_codes`: `[MISSING_CONSTRAINTS]` (expected includes `CASUAL_GREETING_FAST_PATH`)

**Root cause**: appraisal's `under_specified` gate fires on `word_count<4`
for "hello" (1 word). The Fix 2 casual_greeting fast path lives inside
`_handle_answer`, but `ask` route never enters `_handle_answer` — it
dispatches to `compose_non_answer_response("ask")` instead.
**Fix type**: A (add casual_greeting override at route_decision layer)

### casual_greeting_zh ("你好")

- Same root cause as `casual_greeting_en`. `你好` is 2 chars → under_specified.
- **Fix type**: A

### self_reference_integrity_zh

- Response came back in EN despite `active_language_seed: zh` and a ZH
  query ("请介绍一下你自己的特征").
- **Root cause**: Box 0 canonical chunks are predominantly English
  (`mobius_box_0_complete_system_v*.md`, `l0_integrated_v8_2.md`). When
  injected as "Reference" into the prompt, qwen3.5:9b tends to answer
  in the reference's language despite the "Respond in zh" instruction.
- **Fix type**: C (architectural — Box 0 ZH translation, or stronger
  language anchoring in prompt, or ZH corpus_box_0 companion file)

### factual_general_zh ("什么是 Transformer 模型？")

- Response in EN despite ZH query.
- **Root cause**: Box W retrieval returns EN Wikipedia content;
  wiki_context injection biases the LLM response language.
- **Fix type**: C (same family as #3)

### mixed_query_boundary_ja

- `self_referential=True` (assertion expected `False`).
- **Root cause**: The query contains "Answer Entitlement" which is
  MOBIUS-specific terminology and legitimately triggers self_ref.
  The scenario assertion is wrong — this is a correct classification.
- **Fix type**: Assertion correction (not a runtime fix)

### identity_stability_ja (turn 1: "どんなアーキテクチャですか")

- `self_referential=False` (expected `True`).
- **Root cause**: Bare "どんなアーキテクチャですか" lacks any 2nd-person
  pronoun. Prior turn was about MOBIUS but appraisal doesn't inspect
  conversation context for self-ref resolution.
- **Fix type**: C (context-aware self-ref — out of scope for overnight)

### identity_stability_zh (turn 0: "你叫什么名字？")

- `self_referential=False` (expected `True`)
- Response does NOT contain "MOBIUS"/"Möbius" — response starts with
  "我是 Qwen3.5，是阿里巴巴最新推出的通义千问..."
- **Root cause 1**: ZH 2nd-person pronoun `你` / `您` are not in
  SELF_REF_PATTERNS → self_ref not detected → Box 0 not consulted.
- **Root cause 2**: **Base-model identity leakage** — qwen3.5 reveals
  itself as "Qwen 3.5 by Alibaba". This is a major safety issue (per
  Answer Entitlement / Box 0: MOBIUS must self-identify as MOBIUS).
  Box 0 guard only fires when self_referential=True, so leakage is
  downstream of RC 1.
- **Fix type**: B (add ZH self-ref patterns to SELF_REF_PATTERNS) +
  system-prompt hardening. Requires touching appraisal.py which is
  protected; the least-invasive path is adding ZH patterns via a
  config-loaded extension in routing_engine or a separate ZH appraiser
  pattern file. **Flagged for Stage B/C scoped fix.**

## Stage B targeted fix (1 Type A change)

Only `casual_greeting_en` and `casual_greeting_zh` are cleanly-Type-A.
These stem from a common missing-override at route_decision.py — when
`_is_casual_greeting(query)` matches, route should transition from
`ask` → `answer` so the fast path in `_handle_answer` can fire.

See `scripts/apply_config_fix.py` and the next commit for the applied
fix.

## Stage C findings (carried forward)

Recorded in `docs/STAGE_C_FINDINGS.md`:

1. ZH self-ref pattern coverage (你/您/你的/你是 etc.) — mirrors the Fix 1
   kanji gap
2. Language drift when Box 0 / Box W content language mismatches the
   active language — needs corpus-side or prompt-anchor fix
3. Base-model identity leakage via qwen3.5 — needs system-prompt hardening
4. Conversation-context-aware self-ref detection
5. Scenario assertion correction: 008_ja_mixed.yaml's self_referential
   expectation should be `True`, not `False` (runtime behaviour correct)
