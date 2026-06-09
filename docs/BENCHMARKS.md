# Standard benchmark harness — overview

Purpose: objectively compare MMV's 9B (local Ollama / qwen3.5:9b) and 120B
(Groq / openai/gpt-oss-120b) runtimes against widely-used LLM benchmarks
and against Möbius-specific governance probes, with a single normalized
output schema.

This document explains **what the harness covers**, **what is
runnable today**, and **what is intentionally a placeholder** so that
nobody confuses "runner wired" with "benchmark actually executed."

## Status legend (per `benchmarks/configs/benchmark_matrix.yaml`)

- `enabled` — runs immediately with no external install. Real samples
  are shipped inside the repo.
- `optional` — runner is wired, but the actual benchmark requires an
  external package (`lm-eval`, `human-eval`, `swebench`, …) and/or a
  dataset download. When the prerequisite is missing the runner emits
  a single placeholder JSONL row carrying an `install_hint`.
- `placeholder` — the runner exists for orchestration uniformity but
  the bridge to the upstream benchmark is intentionally TODO; do not
  read scores from these rows.

## Benchmarks

### 1. General Knowledge / Reasoning

| Benchmark | Status | Notes |
|---|---|---|
| MMLU | optional | via `lm-eval` |
| MMLU-Pro | optional | via `lm-eval` |
| GPQA | optional | via `lm-eval` |
| BIG-Bench Hard | optional | via `lm-eval` |
| HellaSwag | optional | via `lm-eval` |
| ARC-Challenge | optional | via `lm-eval` |
| DROP | optional | via `lm-eval` |
| TruthfulQA | optional | via `lm-eval` |
| inhouse_mc_smoke | **enabled** | 30 hand-curated MMLU-style items, in-tree, fully offline |

### 2. Math

| Benchmark | Status | Notes |
|---|---|---|
| GSM8K | optional | via `lm-eval` |
| MATH | optional | via `lm-eval` |
| AIME | placeholder | needs dataset access |
| SVAMP | optional | via `lm-eval` |

### 3. Coding

| Benchmark | Status | Notes |
|---|---|---|
| HumanEval | placeholder | needs `human-eval` + sandbox |
| MBPP | placeholder | needs `human-eval` |
| LiveCodeBench | placeholder | needs `livecodebench` |
| SWE-bench Lite | placeholder | needs `swebench` + Docker (~10GB) |
| SWE-bench (full) | placeholder | needs `swebench` + Docker (~100GB) |

### 4. Chat / Preference / Multi-turn

| Benchmark | Status | Notes |
|---|---|---|
| MT-Bench | placeholder | needs `fschat` + judge model API key |
| AlpacaEval | placeholder | needs `alpaca-eval` |
| Chatbot Arena (pairwise local) | placeholder | needs judge model API key |

### 5. Agent / Tool / Web

| Benchmark | Status | Notes |
|---|---|---|
| GAIA | placeholder | gated dataset, agent loop spec required |
| WebArena | placeholder | needs `playwright` + reference Dockers |
| AgentBench | placeholder | many subtasks |
| ToolBench | placeholder | RapidAPI key required |

### 6. Safety / Truthfulness / Governance

| Benchmark | Status | Notes |
|---|---|---|
| TruthfulQA | optional | via `lm-eval` |
| BBQ | optional | via `lm-eval` |
| sycophancy_eval | **enabled** | Möbius probe subset focused on push-back |
| **mobius_governance** | **enabled** | the seven Möbius categories: freshness, anti-sycophancy, safety_abstain, education_vs_advice, half_step, ambiguous_ask, no_unfounded_assertion, over_leading_suppression, reflective_readiness, answer_entitlement |

## What runs in `smoke`

The `smoke` suite runs the three **enabled** benchmarks on both profiles
(local-ollama-9b and groq-gpt-oss-120b) on small samples, and triggers
each remaining runner once so that the orchestration code path is exercised
end-to-end (one placeholder JSONL row per unavailable benchmark).

```bash
bash scripts/run_bench_smoke.sh
```

## What runs in `standard`

`standard` adds every `optional` benchmark to the call list. Without
`lm-eval` / `human-eval` installed they too emit placeholder rows.
See [BENCHMARK_RUNBOOK.md](BENCHMARK_RUNBOOK.md) for the install paths.

## Output formats

Every runner emits the same normalised JSONL row (one row per sample)
to `benchmarks/results/`:

```json
{
  "run_id": "mobius_governance_local-ollama-9b_20260516T120000Z",
  "timestamp": "2026-05-16T12:00:00Z",
  "model_profile": "local-ollama-9b",
  "benchmark": "mobius_governance",
  "task": "anti_sycophancy",
  "sample_id": "gov_anti_sycophancy_001",
  "prompt_hash": "sha256:…",
  "output_hash": "sha256:…",
  "score": 1.0,
  "metric_name": "governance_score",
  "latency_ms": 1230,
  "tokens_in": 45,
  "tokens_out": 92,
  "error": null,
  "metadata": { … }
}
```

`scripts/summarize_benchmarks.py` aggregates every JSONL in
`benchmarks/results/` into a Markdown report + CSV at
`benchmarks/reports/summary_<UTC>.md` / `.csv`.

## Backend purity guard

When a profile asks for the 120B but the local Ollama would also
accept the request, the harness must not silently fall back. Each
profile in `benchmarks/configs/model_profiles.yaml` declares a
`purity_guard` block (`require_backend`, `require_model_substring`,
`forbid_endpoint_substring`). Every successful call is checked by
[`benchmarks/lib/purity_guard.py`](../benchmarks/lib/purity_guard.py)
and a mismatch raises `PurityViolation` (fail-loud, not log-and-skip).

## Adding a new benchmark

1. Add an entry to `benchmarks/configs/benchmark_matrix.yaml`. Pick a
   `runner` (one of the modules under `benchmarks/runners/`) and set a
   realistic `status`. The `smoke_sample_size` / `full_sample_size`
   bound how aggressive the suites get.
2. If the runner needs a new module, create it under
   `benchmarks/runners/run_<name>.py` and add it to `RUNNER_MODULES` in
   `benchmarks/run_suite.py`.
3. Use `benchmarks.lib.jsonl_writer.make_row(...)` so the schema stays
   uniform.
4. Add a row to the relevant suite (`benchmarks/suites/*.yaml`).

## Secrets

- API keys (`GROQ_API_KEY`, `BRAVE_API_KEY`, future judge keys) are
  read from process env, `.env`, or `.env.groq`. They are never logged
  or echoed by the harness.
- Per `CLAUDE.md`, `.env` is gitignored and must not be committed.
