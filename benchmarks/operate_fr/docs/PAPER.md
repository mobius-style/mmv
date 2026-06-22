# OPERATE-FR v0.1 — Specification Digest

> **Version note.** This is the v0.1 specification digest. The current empirical paper is **OPERATE-FR v0.3.6** (Smoke-100 validation + Core-500 candidate stress check), deposited on Zenodo as the **OPERATE-R Freshness Routing Track**: [doi.org/10.5281/zenodo.20510113](https://doi.org/10.5281/zenodo.20510113).

This document is a working digest of the v0.1 specification of
**OPERATE-R Freshness Routing Track**. The authoritative source of truth
is the paper of the same name ([doi.org/10.5281/zenodo.20510113](https://doi.org/10.5281/zenodo.20510113)); this digest exists so that the runnable
artifact can be operated without re-reading the full paper for each
session.

## 1. What the benchmark measures

OPERATE-FR is a **route-first freshness evaluation**. For each input
prompt, it asks: *did the system choose the right operational route?*

Routes for v0.1 scoring:

- `answer` — direct factual response from memory
- `ask` — clarifying question to the user
- `verify` — external verification action (browser/tool, or declared
  inability to verify)
- `date_bound_answer` — answer with explicit "as of" date qualifier
- `abstain` — declines to answer (value-laden, unsafe, out of scope)
- `re_anchor` — corrects a stale premise embedded in the user's prompt

A successful evaluation requires both:

1. Routing into the **allowed routes** for the prompt's family.
2. NOT exhibiting one of the labelled **failure modes**.

## 2. Why route-first

Freshness benchmarks that score on factual outcome alone reward models
that happen to be retrained recently. Route-first scoring asks the
operational question: when a model does not know, does it act like it
does not know? When the user's premise is stale, does it re-anchor? When
the question is a stable fact, does it answer directly without
over-verification?

This isolates the **operational reliability** layer from the
**knowledge recency** layer.

## 3. Component vector, not composite

v0.1 deliberately does NOT compute a composite score. The component
vector exposes trade-offs:

- Route correctness (overall, by family)
- Stale-commitment rate
- Over-verification rate on stable controls
- Date-boundary clarity rate
- Verification completion rate (in tool-mode)
- Average response length
- Average latency
- Failure-mode counts

A governed system that wins on freshness but loses on directness or
latency is a **trade-off**, not a universally better system. Composite
scores hide this.

## 4. Suite composition

v0.1 ships Smoke-100. A Core-500 candidate stress check was added later (controlled 5× expansion of Smoke-100); see OPERATE-FR v0.3.6. Smoke-100 family
distribution:

| Family | Count |
|---|---:|
| volatile_current | 35 |
| stale_premise_trap | 15 |
| stable_control | 25 |
| date_boundary | 10 |
| query_neutrality | 10 |
| ambiguous_time_frame | 5 |
| freshness_long_run | 0 (not in Smoke-100) |

## 5. What v0.1 does NOT claim

- Not a standard benchmark.
- Not externally validated.
- No official composite score.
- No claim that any governed system is universally superior.
- No claim of empirical results unless the actual benchmark was run.

## 6. Reporting discipline

- Neutral baselines first.
- MMV-side results in a separate MMV-side technical report.
- Run actual evaluations; do not extrapolate from descriptions.
- If a governed system does not lose on at least one cost-side
  dimension, treat it as a stress-test trigger, not as proof of
  superiority.
