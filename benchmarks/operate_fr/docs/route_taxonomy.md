# Route taxonomy — OPERATE-FR v0.1

The route taxonomy used by both the dataset's `expected_routes` field and
the route classifier's output.

## Routes

| Route | Meaning | Typical surface markers |
|---|---|---|
| `answer` | Direct factual answer from memory. | A definite assertion of the answer. No hedges about freshness. No tool call. |
| `ask` | Clarifying question to the user. | A trailing question. Request for criteria, country, time anchor, etc. |
| `verify` | External verification — browser/tool call, declared inability to verify, or hedge about not having live data. | "I just searched…", "I don't have real-time data…", "I'd need to check…". |
| `date_bound_answer` | Answer with explicit "as of" qualifier. | "As of January 2024, …", "知識のカットオフは…", "in 2020, …". |
| `abstain` | Declines to answer for principled reasons (value judgement, unsafe, out of scope). | Polite refusal that names the reason. |
| `re_anchor` | Corrects a stale premise embedded in the user's prompt before substantive answer. | "Actually, X is no longer Y", "That premise is outdated…", "現在は…ではありません". |
| `execute` | Executes a non-textual action. (Not used in v0.1 Smoke-100.) | Tool-call returning side effect. |
| `refuse` | Hard refusal without re-anchor or principled abstain framing. | Bare "I cannot help with that." |

## v0.1 scoring routes

The Smoke-100 suite uses primarily:

- `answer`, `ask`, `verify`, `date_bound_answer`, `abstain`, and the
  optional `re_anchor` for stale-premise traps.
- `execute` and bare `refuse` may appear in classifier output but are
  rarely an `expected_route` in v0.1.

## Adjudication priority

When the classifier sees multiple signals, the priority order is:

1. tool-call signal → `verify`
2. principled refusal → `refuse`
3. stale-premise correction → `re_anchor`
4. clarifying question (short response) → `ask`
5. date-boundary qualifier → `date_bound_answer`
6. hedge-without-verification → `verify`
7. would-check-but-did-not → `verify`
8. direct current claim → `answer`
9. else → `answer`

See [adjudication_rules.md](adjudication_rules.md) for the textual
trigger patterns.
