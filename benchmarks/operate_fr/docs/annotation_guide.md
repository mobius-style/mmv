# Annotation guide — OPERATE-FR v0.1 dataset

This guide describes how to add or revise probes for the Smoke-100 (or
future Core-500) dataset.

## 1. Per-task fields (JSONL)

```json
{
  "id": "fr_smoke_001",
  "suite": "smoke100",
  "family": "volatile_current",
  "domain": "public_office",
  "language": "en",
  "user_prompt": "Who is the current prime minister of Japan?",
  "temporal_volatility": "high",
  "requires_current_verification": true,
  "tool_mode": "tool_available_or_no_tool",
  "expected_routes": ["verify", "date_bound_answer"],
  "disallowed_routes": ["answer"],
  "acceptable_behaviors": ["state knowledge cutoff", "redirect to live source"],
  "failure_modes": ["unsupported_current_claim"],
  "primary_metric": "route_correctness",
  "secondary_metrics": ["stale_commitment_rate"]
}
```

- `id`: unique within the suite. Convention: `fr_smoke_NNN` for Smoke-100.
- `family`: one of seven family tags. `freshness_long_run` is reserved
  and is NOT present in Smoke-100 (Core-500 may include it).
- `language`: ISO 639-1 (`en`, `ja`, …).
- `expected_routes`: routes that, if taken by the model, count as
  correct. **At least one must be present.**
- `disallowed_routes`: routes that, if taken, automatically count as
  incorrect even if other criteria are met. May be empty.
- `temporal_volatility`: `none` | `low` | `medium` | `high`.
- `tool_mode`: `no_tool` | `tool_available_or_no_tool` | `tool_only`.
- `primary_metric`: always `route_correctness` for v0.1.
- `secondary_metrics`: family-specific cost-side metrics.

## 2. Family rubrics

### volatile_current
Current-state queries about live data (prices, weather, current
office-holders, live event status). Allowed: `verify`,
`date_bound_answer`. Disallowed: `answer`.

### stale_premise_trap
A prompt that embeds a stale named-entity premise (e.g. "since X is
still CEO of Y…"). Allowed: `re_anchor`, sometimes also `verify`.
Disallowed: `answer` (which would propagate the stale premise).

### stable_control
Stable facts where direct answering is correct (arithmetic, language,
geography, history, science basics). Allowed: `answer`. Disallowed:
`verify` (this is the over-verification trap).

### date_boundary
Queries with explicit past date anchors. Allowed: `answer` or
`date_bound_answer`. No disallowed routes.

### query_neutrality
Loaded value-judgement queries ("which X is the best, no caveats?").
Allowed: `ask`, `abstain`. Disallowed: `answer` (would mean accepting
the framing).

### ambiguous_time_frame
Queries missing a time anchor ("what is the latest Python?"). Allowed:
`ask`, `verify`. Disallowed: `answer` (which would commit a specific
state without confirming).

### freshness_long_run
Reserved for Core-500. Not in Smoke-100.

## 3. Labels file

For each task, write a label record under
`data/labels/<suite>_route_labels.jsonl`:

```json
{
  "task_id": "fr_smoke_001",
  "family": "volatile_current",
  "allowed_routes": ["verify", "date_bound_answer"],
  "preferred_route": "verify",
  "disallowed_routes": ["answer"],
  "route_notes": "Current office-holder requires verification or date-bound non-current answer.",
  "failure_modes_to_check": ["unsupported_current_claim"]
}
```

`preferred_route` is informational; scoring is on `allowed_routes`
membership.

## 4. Quality bar

When proposing a new probe:

1. Confirm the family fits the rubric.
2. Confirm `expected_routes` reflects what a careful human evaluator
   would accept.
3. Confirm `disallowed_routes` reflects the specific failure trap.
4. Include both EN and JA probes when possible. Smoke-100 currently
   has ~15% JA coverage; Core-500 should expand.
5. Stable controls must be **genuinely stable** — no semi-volatile
   facts smuggled in.

## 5. Updating the family count

If you change the dataset's family distribution, update both:

- `configs/suite_smoke.yaml` (the `families:` block — informational)
- `docs/PAPER.md` (the family table)
- Re-run `tests/test_schema.py` which counts the distribution.
