# OPERATE-FR Core-500 Candidate Protocol -- 2026-05-21

## Status

This protocol records the 2026-05-21 Core-500 candidate evaluation pass for
MMV Small, Medium, and Large.

Core-500 candidate is a **controlled larger-N stress suite**, not an
independent benchmark standard. It is derived from Smoke-100 by applying five
neutral prompt-frame variants to each original task.

## Claim Boundary

Allowed claim:

> On a controlled Smoke-100-derived Core-500 candidate suite, the MMV release
> lines produced the reported component-vector results.

Disallowed claims:

- Core-500 candidate proves universal benchmark superiority.
- Core-500 candidate is externally validated.
- Core-500 candidate replaces an independently authored Core-500 benchmark.
- Small or Medium inherit Large RC3.3 quality claims.
- A single composite score represents OPERATE-FR performance.

## Dataset Construction

Source dataset:

- `operate-fr-bench/data/smoke100.jsonl`
- `operate-fr-bench/data/labels/smoke100_route_labels.jsonl`

Generated dataset:

- `operate-fr-bench/data/core500.jsonl`
- `operate-fr-bench/data/labels/core500_route_labels.jsonl`

Builder:

- `operate-fr-bench/scripts/build_core500_from_smoke100.py`

Expansion rule:

- Each Smoke-100 task is represented by five rows.
- `variant_index = 0` preserves the original prompt.
- `variant_index = 1..4` applies neutral prompt frames that should not change
  route entitlement.
- Labels, allowed routes, preferred routes, and disallowed routes are copied
  from the source task and label.
- Every generated row records `source_smoke100_id`, `variant_index`, and
  `derivation_method = neutral_prompt_frame_variant`.

Family distribution:

| Family | n |
|---|---:|
| volatile_current | 175 |
| stale_premise_trap | 75 |
| stable_control | 125 |
| date_boundary | 50 |
| query_neutrality | 50 |
| ambiguous_time_frame | 25 |
| **Total** | **500** |

## Profiles

| Line | Profile |
|---|---|
| Small RC3.3 | `mmv_small_rc3_3_stabilized` |
| Medium RC3.3 | `gemma4_26b_route_transformer_plus_validator_v3_1` |
| Large RC3.3 | `120b_route_transformer_plus_validator_v3_1` |

Profiles are defined in:

- `operate-fr-bench/configs/model_profiles.example.yaml`

Suite config:

- `operate-fr-bench/configs/suite_core500.yaml`

## Scoring

Scoring uses the existing OPERATE-FR rule-based route classifier and scorer:

- `operate-fr-bench/harness/classify_route.py`
- `operate-fr-bench/harness/score.py`
- `operate-fr-bench/harness/report.py`

The canonical output is a component vector:

- route correctness overall
- preferred-route match
- route correctness by family
- stale commitment rate
- unsupported current-claim rate
- over-verification rate on stable controls
- date-boundary clarity rate
- verification completion rate
- failure-mode counts
- route distribution
- response length
- latency

No official composite score is computed.

## Statistical Reporting

For paper-facing reporting:

- Report `n`, `errored`, route-correct count, route-correctness rate, and
  Wilson 95% confidence interval.
- Report per-family route-correctness rates.
- Report cost-side and failure-side metrics next to reliability metrics.
- Do not omit weaknesses or family-level degradation.

Audit packet builder:

- `operate-fr-bench/scripts/build_core500_candidate_audit_packet.py`

Expected audit outputs:

- `operate-fr-bench/reports/core500_candidate_paper_audit_20260521.md`
- `operate-fr-bench/reports/core500_candidate_paper_audit_20260521.manifest.json`

## Reproducibility Notes

The audit manifest records SHA-256 hashes for the dataset, labels, suite,
builders, row outputs, summaries, and reports. These hashes are necessary for
later paper drafting because the candidate suite is derived and should not be
confused with a separately authored benchmark.

## Residual Limits

This protocol does not resolve:

- external human adjudication;
- independent Core-500 authoring;
- LLM-as-judge cross-checking;
- tool-enabled verification completion;
- standard-benchmark status.

