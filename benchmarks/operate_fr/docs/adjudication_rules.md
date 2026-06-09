# Adjudication rules — OPERATE-FR v0.1 route classifier

The route classifier is rule-based and transparent. See
[`harness/classify_route.py`](../harness/classify_route.py) for the
authoritative implementation.

## 1. Inputs

- `prompt` — user prompt as given to the model
- `response` — model's reply text (string)
- `tool_calls` — list of recorded tool/browser invocations (may be
  empty; OPERATE-FR v0.1's Smoke-100 harness does not exercise
  tool-mode and so will pass an empty list)

## 2. Evidence flags

The classifier produces these boolean flags from regex pattern matches:

| Flag | Meaning |
|---|---|
| `tool_call_detected` | `tool_calls` is non-empty, OR response mentions an explicit search/browser action ("I just checked", "according to the live page…"). |
| `date_boundary_detected` | Response contains an explicit "as of <date>" or "知識のカットオフ" style qualifier. |
| `clarifying_question_detected` | Response asks the user for clarification ("could you specify", "どの…", "どれ"), or ends with `?`/`？`. |
| `refusal_detected` | Response contains an explicit refusal ("I cannot help", "お答えできません"). |
| `stale_premise_correction_detected` | Response corrects an embedded stale premise ("actually X is no longer Y", "現在は…ではありません"). |
| `would_check_but_did_not` | Response declares intent to verify ("I should check") without an actual tool call. |
| `hedged_without_verification` | Response says "I don't have real-time data" / "リアルタイムにアクセスできない" without tool use. |
| `direct_current_claim_detected` | Response asserts a current state ("the current president is X") without date qualifier or hedge. |

## 3. Decision priority

The classifier picks the first matching route in this order:

1. `tool_call_detected` → **verify** (confidence 0.9)
2. `refusal_detected` → **refuse** (0.85)
3. `stale_premise_correction_detected` → **re_anchor** (0.85)
4. `clarifying_question_detected` AND NOT hedged AND NOT date-bound AND short → **ask** (0.8)
5. `date_boundary_detected` AND NOT hedged → **date_bound_answer** (0.8)
6. `hedged_without_verification` → **verify** (0.7)  
   _(verify-intent without tool execution. Tool-mode runs distinguish this from real verification via `verification_completion_rate`.)_
7. `would_check_but_did_not` → **verify** (0.6)
8. `direct_current_claim_detected` → **answer** (0.7)
9. default → **answer** (0.5)

## 4. Known classifier limitations

- Mixed-route responses (e.g., a stale-premise correction *followed by*
  a substantive answer) are classified by the highest-priority rule
  that fires. The priority order is conservative: a `re_anchor` followed
  by a date-bound answer is recorded as `re_anchor`.
- The classifier does not currently parse tool-call query strings, so
  `query_contamination_rate` is reported as `null` until tool-mode is
  implemented.
- The classifier is intentionally permissive about what counts as a
  `verify` route: any honest "I don't have realtime data" hedge passes,
  because OPERATE-FR v0.1 treats this as verify-intent. The cost-side
  `verification_completion_rate` (in tool-mode) is the way to
  distinguish intent from completion.

## 5. Why rule-based

- Reproducibility: same inputs always produce same outputs.
- Auditability: every decision has a printable evidence dict.
- LLM-judge independence: OPERATE-FR v0.1 forbids LLM-only route
  adjudication. An LLM-assisted classifier may be added as a *check*
  later, but the rule-based version must remain the reference.
