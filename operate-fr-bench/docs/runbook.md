# Runbook — OPERATE-FR v0.1

Operational guide for running the harness.

## Prerequisites

- Python 3.10+ (3.13 used in the parent project).
- `PyYAML` and `requests` (already in the parent `pyproject.toml`).
- Optional for `cloud_reference_no_tool`: `GROQ_API_KEY` in `.env` or
  `.env.groq` at the repo root, or exported in the environment.
- Optional for `open_weight_local_9b_no_tool`: Ollama daemon running
  with `qwen3.5:9b` pulled.

## Quick commands

All commands assume `cwd = operate-fr-bench/`.

### 1. Dummy dry-run (no API access required)

```bash
python -m harness.run_eval \
    --suite configs/suite_smoke.yaml \
    --profile dummy \
    --out reports/dummy_smoke.jsonl

python -m harness.score \
    --results reports/dummy_smoke.jsonl \
    --labels  data/labels/smoke100_route_labels.jsonl \
    --suite-data data/smoke100.jsonl \
    --out reports/dummy_smoke_summary.json

python -m harness.report \
    --summary reports/dummy_smoke_summary.json \
    --out reports/smoke_dry_run_report.md
```

### 2. Neutral baseline — open-weight 9B, no tools

```bash
python -m harness.run_eval \
    --suite configs/suite_smoke.yaml \
    --profile open_weight_local_9b_no_tool \
    --out reports/9b_no_tool.jsonl

python -m harness.score \
    --results reports/9b_no_tool.jsonl \
    --labels  data/labels/smoke100_route_labels.jsonl \
    --suite-data data/smoke100.jsonl \
    --out reports/9b_no_tool_summary.json

python -m harness.report \
    --summary reports/9b_no_tool_summary.json \
    --out reports/baseline_9b_no_tool.md
```

### 3. Neutral baseline — cloud reference, no tools

```bash
python -m harness.run_eval \
    --suite configs/suite_smoke.yaml \
    --profile cloud_reference_no_tool \
    --out reports/cloud_no_tool.jsonl

python -m harness.score \
    --results reports/cloud_no_tool.jsonl \
    --labels  data/labels/smoke100_route_labels.jsonl \
    --suite-data data/smoke100.jsonl \
    --out reports/cloud_no_tool_summary.json

python -m harness.report \
    --summary reports/cloud_no_tool_summary.json \
    --out reports/baseline_cloud_no_tool.md
```

### 4. Tests

```bash
pytest tests/ -q
```

## Cost notes

- `dummy` — instantaneous, no network. Recommended first run.
- `open_weight_local_9b_no_tool` — 100 sequential calls × ~2 s/call
  ≈ 3–4 min on a single RTX 3070.
- `cloud_reference_no_tool` — 100 sequential calls × ~1 s/call ≈ 100 s,
  ~10K input / ~30K output tokens. Cost depends on the provider.

## Adding a profile

Edit `configs/model_profiles.example.yaml` (or copy to a private
`configs/model_profiles.yaml` that is gitignored — but make sure no
secrets are committed). Each profile must declare:

```yaml
profile_key:
  backend: dummy | openai_compatible | ollama
  model_id: <name>
  temperature: 0.0
  max_tokens: 1024
  timeout_s: 60
  # backend-specific:
  base_url: <url>     # openai_compatible / ollama
  api_key_env: ENV_VAR   # openai_compatible only
```

## Reporting discipline

Per [NON_ASSERTION_COVENANT.md](../NON_ASSERTION_COVENANT.md):

- Neutral baseline reports (open-weight 9B no-tool, cloud reference
  no-tool, etc.) go in `reports/baseline_*.md`.
- Governed-system results (MMV, MOBIUS, …) go in a separate
  `reports/mmv_side_*.md` and are not the lead numbers in any
  neutral baseline report.
- v0.1 does **not** ship a composite score. If you generate one,
  label it non-official and disclose weights.

## Common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| `profile 'X' not in ...example.yaml` | typo or profile not in YAML | check spelling / YAML structure |
| `ollama http 404` | model not pulled | `ollama pull qwen3.5:9b` |
| `groq http 401` | missing or wrong API key | check `.env` / `.env.groq` |
| `task schema invalid: …` | smoke100.jsonl edited and validator failed | run `pytest tests/test_schema.py` |
| zero `verify` route on a baseline | model has no tool access; expected | report as `route_correctness_by_family` not failure |
