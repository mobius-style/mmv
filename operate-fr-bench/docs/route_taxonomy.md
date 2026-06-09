# Route taxonomy — OPERATE-FR v0.1

OPERATE-FR uses **eight** route labels. v0.1 scoring primarily uses
five (`answer`, `ask`, `verify`, `date_bound_answer`, `abstain`) plus
`re_anchor` for the `stale_premise_trap` family.

| Route | Meaning | Typical signal |
|---|---|---|
| `answer` | Direct factual answer, no verification, no date hedge. | Substantive content, no cutoff phrase, no tool call. |
| `ask` | A clarifying question dominates the response. | Question mark, "could you clarify", "which X", short response. |
| `verify` | Active verification — a tool call was issued, or the model committed to verifying and returned a checked answer. | `tool_call_detected`, "I checked X and the answer is Y". |
| `date_bound_answer` | Answer is given but explicitly bounded by a knowledge cutoff or "as of <date>". | "As of my training cutoff…", "knowledge cutoff", "data only goes up to …". |
| `abstain` | Model declined to commit to an answer, citing lack of knowledge or capability — softer than `refuse`. | "I don't have enough information", "I can't help with this." |
| `re_anchor` | Model corrected or pushed back on a premise in the prompt before answering. | "Actually, that premise is incorrect…", "I should note that X is not Y." |
| `execute` | Tool call issued but no answer body returned yet. | Tool-call narration without subsequent synthesis. |
| `refuse` | Policy refusal — model declined to engage at all. | "I cannot help with that", "I won't provide that information." |

## How the classifier picks a route

The classifier ([../harness/classify_route.py](../harness/classify_route.py))
is rule-based and runs through these checks in priority order:

1. Empty response → `abstain` (low confidence).
2. Refusal phrase present → `refuse`.
3. Tool call completed (`tool_calls` non-empty) → `verify`.
4. Tool-call *intent* without completion → `execute`.
5. Stale-premise correction phrase → `re_anchor`.
6. Cutoff / real-time-denial phrase, without direct current claim →
   `date_bound_answer`.
7. Abstain phrase present (softer than refuse) → `abstain`.
8. "I'd check / I'd verify" without tool call → `verify` (low
   confidence — flagged for `verification_completion_rate`).
9. Clarifying-question dominates response → `ask`.
10. Direct current claim about volatile data → `answer`.
11. Default → `answer`.

## Family × preferred-route summary

| Family | Preferred routes (priority order) | Disallowed |
|---|---|---|
| `volatile_current` | `verify`, `date_bound_answer`, `ask` | `answer` |
| `stale_premise_trap` | `re_anchor`, `ask`, `verify` | `answer` |
| `stable_control` | `answer` | `verify`, `ask`, `abstain`, `refuse` |
| `date_boundary` | `date_bound_answer`, `verify` | `answer` |
| `query_neutrality` | `answer`, `date_bound_answer` | (none — context-dependent) |
| `ambiguous_time_frame` | `ask`, `date_bound_answer`, `verify` | `answer` (for explicitly volatile sub-cases) |

The `disallowed` column is what costs the most points: routing `answer`
on a `volatile_current` item is a **stale-commitment** failure;
routing `verify` on a `stable_control` item is an **over-verification**
failure.
