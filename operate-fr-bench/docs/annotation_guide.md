# Annotation guide — OPERATE-FR v0.1 Smoke-100

How to add or modify a task. The Smoke-100 set is shipped in
[`data/smoke100.jsonl`](../data/smoke100.jsonl); per-task labels in
[`data/labels/smoke100_route_labels.jsonl`](../data/labels/smoke100_route_labels.jsonl).

## Required task fields

```json
{
  "id": "fr_smoke_NNN",
  "suite": "smoke100",
  "family": "<one of FAMILIES>",
  "domain": "<short tag like 'public_office'>",
  "language": "en",
  "user_prompt": "<the exact prompt sent to the model>",
  "temporal_volatility": "low | medium | high",
  "requires_current_verification": true | false,
  "tool_mode": "no_tool | tool_available | tool_available_or_no_tool",
  "expected_routes": ["verify", "date_bound_answer"],
  "disallowed_routes": ["answer"],
  "primary_metric": "route_correctness"
}
```

## Required label fields

```json
{
  "task_id": "fr_smoke_NNN",
  "allowed_routes": ["verify", "date_bound_answer"],
  "preferred_route": "verify",
  "disallowed_routes": ["answer"],
  "route_notes": "<one-sentence rationale>",
  "failure_modes_to_check": ["stale_commitment", "missing_date_boundary"]
}
```

## Family selection

Choose the family that matches the failure mode you want this prompt
to expose, not the topical area. A question about Bitcoin can belong
to `volatile_current` (current price) or `query_neutrality` (general
description) depending on how the prompt is phrased.

| If the prompt … | Family |
|---|---|
| asks for a current value that changes within months | `volatile_current` |
| asserts an incorrect / outdated premise | `stale_premise_trap` |
| has a single right answer that does not change | `stable_control` |
| asks "latest / most recent / approximately" without a date | `date_boundary` |
| asks something broadly stable without temporal markers | `query_neutrality` |
| has ambiguous temporal scope and could go either way | `ambiguous_time_frame` |

## Routing the task

Once the family is fixed, the `expected_routes` and `disallowed_routes`
follow from the family-to-route mapping documented in
[route_taxonomy.md](route_taxonomy.md). Special cases:

- A volatile item that has been **publicly stable for years** (e.g.
  "Is the UK currently in the EU?") may permit `answer` alongside
  `verify` / `date_bound_answer`. Tag it with `temporal_volatility:
  low` and accept `answer`.
- A stable control whose phrasing **invites verification** (e.g.
  "What's the current chemical symbol for gold?") should still
  disallow `verify` — over-verification is a failure mode.

## Language coverage

Smoke-100 includes ~10 JP items as a coverage probe. JP coverage is
deliberately small in v0.1; the classifier's JA pattern set is
narrower than its EN set. If you add JP items, prefer family /
intent diversity over volume.

## Sensitive content

Smoke-100 contains no personally identifying information, no medical
diagnoses about real individuals, and no scraped private prompts. Do
not add prompts that would degrade those properties.

## Validation

After editing a task or label file, run:

```bash
cd operate-fr-bench
pytest tests/test_schema.py -v
```

This checks family counts, schema integrity, route taxonomy
membership, and label-task ID correspondence.
