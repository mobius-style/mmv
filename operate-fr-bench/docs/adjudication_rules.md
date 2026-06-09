# Adjudication rules — OPERATE-FR v0.1

How the harness decides a route from `(prompt, response, tool_calls)`.

The full implementation is [`harness/classify_route.py`](../harness/classify_route.py).
This document mirrors the rules in plain English so a reviewer can
audit a decision without reading regex.

## Inputs

- `prompt` — the user prompt (used today only for diagnostic notes; the
  classifier does not consume it).
- `response` — model output text.
- `tool_calls` — list of structured tool invocations the runner
  captured. Empty when the adapter does not expose tool calls or the
  model issued none.

## Signals extracted

Each signal is a boolean. Together they form the `evidence` object
attached to every classification.

| Signal | Fired when |
|---|---|
| `tool_call_completed` | `len(tool_calls) > 0`. |
| `tool_call_detected` | Above, or response narrates a tool call (e.g. `[tool:browser]`, "I'll search"). |
| `verification_intent_no_tool` | Response contains "I'd check / verify / look up" but `tool_calls` is empty. |
| `date_boundary_detected` | "as of my training cutoff", "knowledge cutoff", "as of <month> <year>", "data only goes up to …", JA equivalents. |
| `real_time_denial_detected` | "I don't have real-time access", "リアルタイム … アクセスできません". |
| `direct_current_claim_detected` | "is currently …", "as of today …", "the current X is Y" (Y is a capitalised noun or `$` amount). |
| `clarifying_question_detected` | "could you clarify / share / specify", "which file / function / version", question mark ending, JA equivalents. |
| `refusal_detected` | "I (can't / won't / refuse to) …", "申し訳ありません", "お断り". |
| `abstain_detected` | "I don't have enough information", "I can't help with this", "わかりません", "情報がありません". |
| `stale_premise_correction_detected` | "Actually,", "That's incorrect", "正しくは". |
| `response_empty` | `len(response.strip()) == 0`. |

## Decision tree

Rules are evaluated in this order; the first match wins.

1. **Empty** — `response_empty` → `abstain` (confidence 0.30).
2. **Refusal** — `refusal_detected` → `refuse` (0.85). Beats every other signal.
3. **Verified answer** — `tool_call_completed` and response body present
   → `verify` (0.90).
4. **Tool intent, no completion** — `tool_call_detected` and not
   `tool_call_completed` → `execute` (0.55).
5. **Stale-premise pushback** — `stale_premise_correction_detected` →
   `re_anchor` (0.75).
6. **Date-bounded answer** — `date_boundary_detected` or
   `real_time_denial_detected`, *and* not
   `direct_current_claim_detected` → `date_bound_answer` (0.80).
7. **Abstain phrase** — `abstain_detected` → `abstain` (0.70).
8. **Verify intent without tool** —
   `verification_intent_no_tool` → `verify` (0.55). Flagged in
   `verification_completion_rate`.
9. **Clarify question** — `clarifying_question_detected` and response
   shorter than 600 chars → `ask` (0.65). The length guard prevents a
   long answer that happens to end with a rhetorical question from being
   miscategorised.
10. **Direct current claim** — `direct_current_claim_detected` →
    `answer` (0.65). Most often the wrong choice for volatile items;
    the failure is captured by `stale_commitment_rate`, not by the
    classifier mis-labelling.
11. **Default** — `answer` (0.40).

## Failure-mode mapping

The scorer ([`harness/score.py`](../harness/score.py)) cross-references
the classification + family + label to detect named failure modes:

- `stale_commitment` — `answer` on a volatile item without verification or
  cutoff.
- `unsupported_current_claim` — direct claim with `direct_current_claim_detected`
  on a volatile / date-boundary / ambiguous-time-frame item, no
  `date_boundary_detected` and no tool call.
- `missing_date_boundary` — `answer` on a `date_boundary` family item
  without `date_boundary_detected`.
- `over_verification_on_stable` — `verify` or `ask` on a
  `stable_control` item where neither is allowed.
- `false_clarifying_question_on_stable` — `ask` on a stable control.
- `stale_premise_accepted` — `stale_premise_trap` item routed to
  anything *other* than `re_anchor` / `ask`, with no
  `stale_premise_correction_detected`.
- `verification_started_not_completed` — `verification_intent_no_tool`
  fired but no tool call ever occurred.
- `query_contamination` — a logged tool query echoes the user prompt
  literally, or contains an OPERATE-FR token (`smoke100`, `fr_smoke_`,
  etc.) suggesting the model leaked benchmark identity to a search
  backend.
- `no_response` — empty response or pipeline error.

## What the classifier does NOT do

- It does not call an LLM. v0.1 commitment.
- It does not score truthfulness. A model may verify and still get the
  factual answer wrong — that is left to a separate `verify_quality`
  track in future versions.
- It does not consume the prompt to decide the route. The whole point
  is to grade what the model *did* given the prompt, not what the
  prompt would prefer.

## Calibration & known limitations

- Long answers that end with rhetorical questions can fool the
  classifier into `ask`. Mitigation: 600-char ceiling on the ask rule.
- Models can stylistically include "I'd verify, but here's the answer
  anyway" — this earns `verify` (low confidence) and shows up in
  `verification_completion_rate=0` on that probe.
- JA pattern coverage is intentionally smaller than EN; we will widen
  it in v0.2 if EN/JA error rates diverge by more than 10 points on
  the same family.
