# OPERATE-FR — Runbook

Operational guide for running the Smoke-100 suite end-to-end.

## 0. Prerequisites

- Python 3.13+ with `pyyaml`, `requests` installed. The MOBIUS-MMV
  venv (`$HOME/デスクトップ/mobius_ai/venv313`) already has these.
- For non-dummy profiles, the corresponding API key/endpoint:
  - `local-ollama-9b` — Ollama running locally with `qwen3.5:9b`.
  - `groq-gpt-oss-120b` — `GROQ_API_KEY` in `.env` or `.env.groq`.
  - `openai_compatible` — your own base URL + key, set per profile.
- The MMV runtime is in-process via `benchmarks/lib/mmv_engine_caller.py`
  (used only when explicitly opting into MMV profiles, not for neutral
  baselines).

## 1. Dry-run

Smoke-test the harness with the dummy backend (no API, no network):

```bash
python -m benchmarks.operate_fr.harness.run_eval \
    --suite benchmarks/operate_fr/configs/suite_smoke.yaml \
    --profile dummy \
    --out benchmarks/operate_fr/reports/dummy_smoke.jsonl

python -m benchmarks.operate_fr.harness.score_cli \
    --results benchmarks/operate_fr/reports/dummy_smoke.jsonl \
    --labels  benchmarks/operate_fr/data/labels/smoke100_route_labels.jsonl \
    --out     benchmarks/operate_fr/reports/dummy_smoke_summary.json

python -m benchmarks.operate_fr.harness.report_cli \
    --summary benchmarks/operate_fr/reports/dummy_smoke_summary.json \
    --out     benchmarks/operate_fr/reports/smoke_dry_run_report.md \
    --profile dummy --section-label neutral_baseline
```

## 2. Neutral baselines

Run the same three-step flow with non-MMV profiles. Put each result in
its own report path so they remain separable:

```bash
# 9B raw — open-weight local 7-13B class
python -m benchmarks.operate_fr.harness.run_eval \
    --suite benchmarks/operate_fr/configs/suite_smoke.yaml \
    --profile local-ollama-9b \
    --out benchmarks/operate_fr/reports/local-ollama-9b_smoke.jsonl

python -m benchmarks.operate_fr.harness.score_cli \
    --results benchmarks/operate_fr/reports/local-ollama-9b_smoke.jsonl \
    --labels  benchmarks/operate_fr/data/labels/smoke100_route_labels.jsonl \
    --out     benchmarks/operate_fr/reports/local-ollama-9b_smoke_summary.json

python -m benchmarks.operate_fr.harness.report_cli \
    --summary benchmarks/operate_fr/reports/local-ollama-9b_smoke_summary.json \
    --out     benchmarks/operate_fr/reports/baseline_local-ollama-9b.md \
    --profile local-ollama-9b --section-label neutral_baseline

# 120B raw — generic hosted strong baseline
python -m benchmarks.operate_fr.harness.run_eval \
    --suite benchmarks/operate_fr/configs/suite_smoke.yaml \
    --profile groq-gpt-oss-120b \
    --out benchmarks/operate_fr/reports/groq-gpt-oss-120b_smoke.jsonl

# … score + report as above
```

## 3. MMV-side technical report (separate)

```bash
python -m benchmarks.operate_fr.harness.run_eval \
    --suite benchmarks/operate_fr/configs/suite_smoke.yaml \
    --profile mobius-mmv-governed-9b-v2 \
    --out benchmarks/operate_fr/reports/mmv-9b-v2_smoke.jsonl

python -m benchmarks.operate_fr.harness.score_cli \
    --results benchmarks/operate_fr/reports/mmv-9b-v2_smoke.jsonl \
    --labels  benchmarks/operate_fr/data/labels/smoke100_route_labels.jsonl \
    --out     benchmarks/operate_fr/reports/mmv-9b-v2_smoke_summary.json

python -m benchmarks.operate_fr.harness.report_cli \
    --summary benchmarks/operate_fr/reports/mmv-9b-v2_smoke_summary.json \
    --out     benchmarks/operate_fr/reports/mmv_side_mmv-9b-v2.md \
    --profile mobius-mmv-governed-9b-v2 --section-label mmv_side_technical
```

Always use `--section-label mmv_side_technical` for MMV runs so the
report's header makes the section identity unambiguous.

## 4. Reading the reports

Each report carries:

- **Headline component vector** — overall correctness + cost-side
  metrics. **No composite.**
- **Route correctness by family** — the trade-off surface.
- **Failure-mode counts** — what went wrong.

Pair-wise comparison (e.g., 9B raw vs MMV-9B-v2) should be done by
reading two reports side by side or by aggregating their summary JSONs
into a small comparison script. Do NOT collapse the component vectors
into a single composite for headline use.

## 5. Adding a new profile

The harness re-uses `benchmarks/configs/model_profiles.yaml`. Add a
profile there with a recognised `backend` (`dummy` / `openai_compatible`
/ `ollama` / `groq` / `mobius_engine`) and then refer to its key via
`--profile <key>`.

## 6. Troubleshooting

- "PurityViolation" on a Groq run → your `GROQ_API_KEY` is missing or
  the model id mismatched. The harness will fail loud rather than
  silently fall back. Set the key and retry.
- "engine construction failed" on an MMV profile → check that `src/`
  is importable (the harness runs from repo root).
- "n_errors > 0" in the summary → look at the individual JSONL rows;
  the runner does not crash on a single failure, so other tasks still
  scored.
