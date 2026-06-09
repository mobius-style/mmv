# Non-Assertion Covenant — OPERATE-FR v0.1

**Draft; subject to legal review. Not legal advice.**

This covenant accompanies the OPERATE-FR v0.1 benchmark specification and
its artifact (data, labels, harness, classifier, documentation).

## 1. Purpose

OPERATE-FR is published as a **candidate operational benchmark track**.
It is intended to surface the trade-off between freshness reliability and
user-side friction (direct answers, latency, over-verification, query
contamination) so that systems can be measured along multiple axes rather
than ranked on a single composite score.

## 2. Non-assertion of empirical superiority

Publication of OPERATE-FR does not assert that any participating system,
including any MMV/MOBIUS-originating system, is empirically superior.

- v0.1 ships **without any leaderboard**.
- v0.1 ships **without an official composite score**.
- Any results table is reported as a **component vector**.
- Standard-benchmark status is not claimed and may not be claimed until
  independent external validation exists.

## 3. Non-assertion of legal status

This document is a covenant about how the benchmark is published and
discussed. It is **not legal advice** and creates no contractual
obligation outside what the underlying licenses already establish. Final
legal scope is subject to review.

## 4. Originator-disclosure requirement

Any party reporting OPERATE-FR results from an MMV/MOBIUS-originating
system shall:

1. produce a **neutral baseline report first** that does not lead with
   the originating system, and
2. report the MMV-side run as a **separate MMV-side technical report**
   that clearly identifies its origin.

This is a discipline against self-grading; it does not prohibit MMV-side
reporting.

## 5. Cost-side honesty

If a governed system shows no loss on at least one cost-side dimension
(response length, latency, over-verification on stable controls, query
contamination), this is to be **flagged as a benchmark stress-test
trigger**, not interpreted as evidence of universal superiority. The
expectation is that any reliability lift carries a measurable friction or
latency cost; benchmarks that fail to surface that cost should be
revised.

## 6. Modification

Modifications to this covenant must preserve sections 2–5 in substance,
or must be marked as a fork of the covenant with an explicit changed
section list. Forking is permitted.

## 7. Reservation

Nothing in this covenant waives the rights of contributors, originators,
or downstream users under the underlying software / data licenses.
