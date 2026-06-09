# OPERATE-FR v0.1 — Freshness Routing Track

**Status:** candidate operational benchmark track. **Not a standard benchmark.**
No external validation, no leaderboard, no official composite score.

OPERATE-FR is a **route-first freshness evaluation**: given a user prompt, it
asks whether a model picked the right *route* (answer vs ask vs verify vs
date-bound answer vs abstain) rather than only whether it got a final answer
"right". Stable controls are included alongside volatile-current and
stale-premise-trap items so the harness can detect both
under-verification (stale commitment) and over-verification (treating
arithmetic like a freshness question).

## What is shipped here

This directory is a **runnable artifact release** containing:

- `data/smoke100.jsonl` — 100-task Smoke-100 (volatile / stale-premise /
  stable / date-boundary / query-neutrality / ambiguous-time-frame)
- `data/labels/smoke100_route_labels.jsonl` — per-task allowed/preferred
  routes
- `data/core500.jsonl` — controlled 500-task candidate expansion of
  Smoke-100 using neutral prompt-frame variants
- `data/labels/core500_route_labels.jsonl` — per-task labels for the
  Core-500 candidate expansion
- `harness/` — transparent rule-based route classifier + scorer + runner +
  reporter
- `configs/` — suite definition and model-profile examples
- `tests/` — schema, classifier, scoring, and dry-run pytest
- `docs/` — paper-aligned specification, route taxonomy, adjudication
  rules, annotation guide, runbook
- `reports/` — baseline report template and the dry-run report

Core-500 candidate is included as a derived stress suite, not as an
independently authored benchmark standard. No `freshness_long_run` items are
included in Smoke-100.

## What is NOT here

- No claim of standard-benchmark status.
- No official composite score in scoring output. Optional scorecards are
  labelled `non_official_scorecard` with weights disclosed.
- No LLM-judge-only classification. The default classifier is a
  transparent rule-based detector whose evidence is exposed in every
  output record.
- No MMV/MOBIUS results in the neutral baseline report. MMV-side runs are
  produced as a **separate** `MMV-side technical report` per the
  reporting discipline in `docs/PAPER.md`.

## Quick start (dry-run, no API keys)

```bash
# from repo root
cd operate-fr-bench
python -m harness.run_eval \
    --suite configs/suite_smoke.yaml \
    --profile dummy \
    --out reports/dummy_smoke.jsonl
python -m harness.score \
    --results reports/dummy_smoke.jsonl \
    --labels  data/labels/smoke100_route_labels.jsonl \
    --out reports/dummy_smoke_summary.json
python -m harness.report \
    --summary reports/dummy_smoke_summary.json \
    --out reports/smoke_dry_run_report.md
```

## Neutral baseline (real models)

The neutral baseline report should be produced before any MMV-side
report. Run open-weight models without tools first, then with tools.

```bash
# example: open-weight ~9B, no tools (Ollama local)
python -m harness.run_eval \
    --suite configs/suite_smoke.yaml \
    --profile open_weight_local_9b_no_tool \
    --out reports/open_weight_9b_no_tool.jsonl
```

See `docs/runbook.md` for the full sequence and
`reports/baseline_report_template.md` for the reporting format.

## MMV Large RC3.3 — Temporal Governance Update

- Large-model no-tool Smoke-100 candidate engineering result
- Release pointer: [releases/large/current.yaml](releases/large/current.yaml)
- Freeze note: [docs/MMV_Large_RC3_3_FREEZE_NOTE.md](docs/MMV_Large_RC3_3_FREEZE_NOTE.md)
- Smoke report: [reports/MMV_Large_RC3_3_smoke_report.md](reports/MMV_Large_RC3_3_smoke_report.md)
- Human review packet: [reports/human_review_packet_mmv_large_rc3_3/](reports/human_review_packet_mmv_large_rc3_3/)
- Stress-test FLAG retained (Section 14)
- Controlled Core-500 candidate stress result recorded; independent Core-500
  validation pending

## MMV Medium RC3.3 — Local Gemma binding (active: gemma4:12b)

- Medium-model local line. RC3.3 maintained; **2026-06-06 model-binding
  update** `gemma4:26b` → `gemma4:12b` under the identical Large RC3.3 v3.1
  governance stack (governance bit-identical → same RC label)
- Release pointer: [releases/medium/current.yaml](releases/medium/current.yaml)
- Freeze note: [docs/MMV_Medium_RC3_3_FREEZE_NOTE.md](docs/MMV_Medium_RC3_3_FREEZE_NOTE.md)
  (see "2026-06-06 model-binding update" section)
- Governance stack: Large RC3.3 v3.1 route transformer + post-validator + force re-anchor, with local Gemma backend
- Head-to-head 12b-vs-26b comparison (Smoke-100 + Core-500): [reports/MMV_Medium_12b_vs_26b_smoke_comparison.md](reports/MMV_Medium_12b_vs_26b_smoke_comparison.md)
- Evidence: Core-500 candidate `route_correctness_overall` 0.738 (26b) → 0.760 (12b),
  ~2.4× lower latency; one small stale_premise_trap regression. No-Large-quality-transfer caveat retained.

## MMV Small RC3.3 — Routing Stabilization Update

- Small-model no-tool Smoke-100 candidate engineering result
- Freeze basis: v1 (`mmv_small_rc3_3_stabilized`)
- v1.1 attempted and reverted (preserved as documented evidence)
- Release pointer: [releases/small/current.yaml](releases/small/current.yaml)
- Freeze note: [docs/MMV_Small_RC3_3_FREEZE_NOTE.md](docs/MMV_Small_RC3_3_FREEZE_NOTE.md)
- Smoke report: [reports/MMV_Small_RC3_3_smoke_report.md](reports/MMV_Small_RC3_3_smoke_report.md)
- Human review packet: [reports/human_review_packet_mmv_small_rc3_3/](reports/human_review_packet_mmv_small_rc3_3/)
- Stress-test FLAG retained (Section 14)
- Controlled Core-500 candidate stress result recorded; independent Core-500
  validation pending

## License & covenant

- Code: see `LICENSE` (inherits project license).
- The dataset and benchmark documents are covered by the
  `NON_ASSERTION_COVENANT.md` — **draft; subject to legal review; not
  legal advice**.

## Reading the results

OPERATE-FR reports a **component vector**, not a single number:

- `route_correctness_overall`
- `route_correctness_by_family`
- `stale_commitment_rate` (volatile/stale-premise items where the model
  asserted a current fact without verification)
- `over_verification_rate_on_stable_controls`
- `date_boundary_clarity_rate`
- `verification_completion_rate` (if tool calls were attempted)
- `query_contamination_rate` (if tool queries are logged)
- `failure_mode_counts`
- `average_response_length`
- `latency` (if measured)

There is no official aggregate. Cost-side metrics (length, latency,
over-verification) are reported alongside reliability metrics so that
trade-offs are visible.
