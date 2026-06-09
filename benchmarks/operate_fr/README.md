# OPERATE-FR v0.1 — Freshness Routing Track

**Status:** candidate operational benchmark track, **not** a validated standard
benchmark. This release ships the v0.1 Smoke-100 runnable artifact: dataset,
labels, rule-based route classifier, scorer, and runner. Core-500 is future
work. No official composite score is computed.

This package is integrated into the broader MOBIUS-MMV repository under
`benchmarks/operate_fr/` rather than the spec's top-level `operate-fr-bench/`
layout — the existing project already has a `benchmarks/` evaluation tree.
Section 3 of the spec explicitly allows this adaptation.

## Layout

```
benchmarks/operate_fr/
  README.md                    — this file
  data/
    smoke100.jsonl             — 100 probes (35/15/25/10/10/5/0 by family)
    labels/
      smoke100_route_labels.jsonl
  harness/
    schemas.py                 — task / label / result schema validation
    adapters.py                — thin wrapper over benchmarks/lib/model_client
    classify_route.py          — RULE-BASED route classifier (no LLM)
    score.py                   — component-vector scorer (no composite)
    report.py                  — Markdown renderer
    run_eval.py                — runner CLI
    score_cli.py               — scorer CLI
    report_cli.py              — report CLI
  configs/
    suite_smoke.yaml
    model_profiles.example.yaml
  docs/
    PAPER.md                   — spec digest
    annotation_guide.md
    route_taxonomy.md
    adjudication_rules.md
    runbook.md
  reports/
    baseline_report_template.md
    (run outputs land here)
  tests/
    test_schema.py
    test_route_classifier.py
    test_scoring.py
    test_smoke_dry_run.py
```

## Three-step workflow

```bash
# 1. RUN the suite on a model profile (produces a JSONL of results)
python -m benchmarks.operate_fr.harness.run_eval \
    --suite benchmarks/operate_fr/configs/suite_smoke.yaml \
    --profile dummy \
    --out benchmarks/operate_fr/reports/dummy_smoke.jsonl

# 2. SCORE the results into a JSON component vector
python -m benchmarks.operate_fr.harness.score_cli \
    --results benchmarks/operate_fr/reports/dummy_smoke.jsonl \
    --labels  benchmarks/operate_fr/data/labels/smoke100_route_labels.jsonl \
    --out     benchmarks/operate_fr/reports/dummy_smoke_summary.json

# 3. RENDER a Markdown report (section_label = neutral_baseline or mmv_side_technical)
python -m benchmarks.operate_fr.harness.report_cli \
    --summary benchmarks/operate_fr/reports/dummy_smoke_summary.json \
    --out     benchmarks/operate_fr/reports/smoke_dry_run_report.md \
    --profile dummy \
    --section-label neutral_baseline
```

## Reporting discipline

- Neutral baselines (non-MMV systems) are reported FIRST and SEPARATELY.
- MMV / MOBIUS systems live in a separate MMV-side technical report.
- v0.1 reports a component vector — **no official composite score**.
- Route correctness is the primary metric; cost-side metrics (stale-commitment,
  over-verification, date-boundary clarity, latency, response length) expose
  trade-offs.

See [docs/PAPER.md](docs/PAPER.md), [docs/route_taxonomy.md](docs/route_taxonomy.md),
[docs/adjudication_rules.md](docs/adjudication_rules.md), and
[NON_ASSERTION_COVENANT.md](NON_ASSERTION_COVENANT.md).
