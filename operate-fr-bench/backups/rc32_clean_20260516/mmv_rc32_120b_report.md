# OPERATE-FR v0.1 — component-vector report

_Generated: 2026-05-16T01:33:34Z_

> OPERATE-FR is a **candidate operational benchmark track**, not a standard benchmark. No external validation. **No official composite score.** All numbers below are component metrics; cost-side measurements (length, latency, over-verification on stable controls) are reported alongside reliability metrics.

_Scorer note: OPERATE-FR v0.1 reports a component vector, not a composite score. Do not aggregate without disclosing weights._

## Component vector

| Metric | Value |
|---|---:|
| route_correctness_overall | 0.460 |
| preferred_route_match_rate | 0.370 |
| stale_commitment_rate | 0.015 |
| unsupported_current_claim_rate | 0.015 |
| over_verification_rate_on_stable_controls | 0.000 |
| date_boundary_clarity_rate | 0.400 |
| verification_completion_rate | 0.000 |
| query_contamination_rate | — |
| average_response_length (chars) | 689 |
| average_latency_ms | 1029 |

## Route correctness by family

| Family | n | correct | rate | preferred-match rate | errored |
|---|---:|---:|---:|---:|---:|
| `ambiguous_time_frame` | 5 | 1 | 0.200 | 0.000 | 0 |
| `date_boundary` | 10 | 4 | 0.400 | 0.300 | 0 |
| `query_neutrality` | 10 | 10 | 1.000 | 0.900 | 0 |
| `stable_control` | 25 | 25 | 1.000 | 1.000 | 0 |
| `stale_premise_trap` | 15 | 0 | 0.000 | 0.000 | 0 |
| `volatile_current` | 35 | 6 | 0.171 | 0.000 | 0 |

## Predicted route distribution

| Route | Count |
|---|---:|
| `answer` | 80 |
| `date_bound_answer` | 15 |
| `refuse` | 5 |

## Top route confusions (preferred → classified)

| Preferred | Classified | Count |
|---|---|---:|
| `answer` | `answer` | 34 |
| `verify` | `answer` | 27 |
| `re_anchor` | `answer` | 7 |
| `date_bound_answer` | `answer` | 7 |
| `re_anchor` | `date_bound_answer` | 6 |
| `verify` | `date_bound_answer` | 5 |
| `ask` | `answer` | 5 |
| `verify` | `refuse` | 3 |
| `date_bound_answer` | `date_bound_answer` | 3 |
| `re_anchor` | `refuse` | 2 |

## Failure mode counts

| Mode | Count |
|---|---:|
| `stale_premise_accepted` | 15 |
| `missing_date_boundary` | 6 |
| `verification_started_not_completed` | 2 |
| `unsupported_current_claim` | 1 |
| `stale_commitment` | 1 |

## Totals

| Field | Count |
|---|---:|
| total_tasks | 100 |
| scored_tasks | 100 |
| route_correct | 46 |
| route_correct_preferred | 37 |
| errored | 0 |

## Reporting discipline reminders

- This report exposes a **component vector**, not a single score.
- For any non-official scorecard, weights MUST be disclosed.
- A neutral baseline report must precede any MMV-side report.
- Standard-benchmark status is NOT claimed.

