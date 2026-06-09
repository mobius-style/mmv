# Benchmark runbook

Operational runbook for the standard benchmark harness. Pairs with
[BENCHMARKS.md](BENCHMARKS.md), which describes the catalogue.

## Setup

1. Activate the project venv (Python 3.13):
   ```bash
   source $HOME/デスクトップ/mobius_ai/venv313/bin/activate
   # or the `mobius` alias
   ```
2. Confirm Ollama is running and `qwen3.5:9b` is pulled:
   ```bash
   curl -s http://localhost:11434/api/tags | python -c "import json,sys; \
     [print(m['name']) for m in json.load(sys.stdin)['models']]" | grep qwen3.5:9b
   ```
3. Provide API keys for the 120B reference (Groq):
   - `.env` should contain `GROQ_API_KEY=...`, or
   - `.env.groq` should contain `GROQ_API_KEY=...` on a single line.
   The harness reads both. Keys are never logged.

## Required API keys

| Profile / benchmark | Env var | Where to get |
|---|---|---|
| `groq-gpt-oss-120b` | `GROQ_API_KEY` | https://console.groq.com/ |
| Brave Search (verify-route) | `BRAVE_API_KEY` | https://brave.com/search/api/ (not used by the standard benchmark harness yet) |
| MT-Bench / AlpacaEval judge | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | needed only when those benchmarks are unblocked |
| GAIA / ToolBench | varies | dataset/tool-specific |

## Quick commands

### Smoke (recommended first run)

```bash
bash scripts/run_bench_smoke.sh
```

Runs `mobius_governance`, `sycophancy_eval`, `inhouse_mc_smoke` on
**both** 9B and 120B (real model calls), and emits placeholder rows
for the remaining benchmarks. End-to-end wall clock is dominated by
the 120B latency × 16 samples; expect roughly **2–5 minutes** total.

Override profiles via env:
```bash
BENCH_PROFILES=local-ollama-9b bash scripts/run_bench_smoke.sh    # 9B only
BENCH_PROFILES=dummy bash scripts/run_bench_smoke.sh              # no network
```

### Standard

```bash
bash scripts/run_bench_standard.sh
```

Adds every `optional` benchmark to the call list. Without the external
deps installed, each will produce one placeholder row carrying an
`install_hint` so reports stay honest.

### Full

```bash
BENCH_CONFIRM=I_UNDERSTAND bash scripts/run_bench_full.sh
```

Walks **every** entry in `benchmark_matrix.yaml`. The guard env var is
mandatory because the full set includes SWE-bench / WebArena / GAIA,
which require external installs, GB-scale downloads, and possibly
non-trivial cloud spend. Do not run blindly.

### Individual benchmark

```bash
python benchmarks/runners/run_mobius_governance.py \
    --profile local-ollama-9b --sample-size 60
```

For any optional runner without its deps installed:
```bash
python benchmarks/runners/run_lm_eval.py \
    --profile local-ollama-9b --benchmark mmlu
# → emits a placeholder JSONL with install_hint
```

### Summary report

The shell scripts already call this at the end, but you can re-run it
ad-hoc:
```bash
python scripts/summarize_benchmarks.py
ls -1t benchmarks/reports/summary_*.md | head -1
```

## Reading the results

- `benchmarks/results/*.jsonl` — one row per sample, normalized schema
  (see [BENCHMARKS.md](BENCHMARKS.md) for the exact fields).
- `benchmarks/reports/summary_<UTC>.md` — human-readable aggregate.
- `benchmarks/reports/suite_<name>_*.md` — per-suite orchestrator log
  showing which benchmarks ran enabled vs placeholder vs errored.

Score interpretation:
- `score: 1.0` — sample passed its runner-defined check.
- `score: 0.0` — sample failed.
- `score: null` + `error: "PLACEHOLDER…"` — runner not wired or
  missing prereq. Treat as "not run."
- `score: null` + `error: <traceback>` — runner crashed. Re-run with
  the hint in the report.

## Unblocking the optional / placeholder benchmarks

### lm-eval-harness family (MMLU, MMLU-Pro, GPQA, BBH, HellaSwag, ARC, DROP, TruthfulQA, GSM8K, MATH, SVAMP, BBQ)

```bash
pip install lm-eval datasets
# then for an OpenAI-compatible 9B (Ollama exposes /v1):
python -m lm_eval \
    --model openai-completions \
    --model_args base_url=http://localhost:11434/v1,model=qwen3.5:9b \
    --tasks mmlu,gsm8k,hellaswag,arc_challenge,truthfulqa_mc1 \
    --num_fewshot 0 \
    --output_path benchmarks/results/lm_eval_9b
```
Then update `benchmarks/runners/run_lm_eval.py` to merge lm-eval's
output into the normalized schema. Until that bridge lands, the
runner emits a placeholder row.

### HumanEval / MBPP / LiveCodeBench

```bash
pip install human-eval datasets
# HumanEval grading EXECUTES generated code — review human-eval's
# safety notes before running on untrusted models.
```

### SWE-bench / SWE-bench Lite

```bash
pip install swebench
# requires Docker. Plan ~10GB disk for Lite, ~100GB for full.
```

### Agent benchmarks

| Benchmark | Setup |
|---|---|
| MT-Bench | `pip install "fschat[model_worker]"`; needs judge key. |
| AlpacaEval | `pip install alpaca-eval`; needs judge key. |
| GAIA | Clone `gaia-benchmark/GAIA`, accept dataset terms on HuggingFace. |
| WebArena | `pip install playwright && playwright install`; run reference Dockers. |
| AgentBench | Clone `THUDM/AgentBench`. |
| ToolBench | Clone `OpenBMB/ToolBench`; RapidAPI key required. |

After install, each `benchmarks/runners/run_*` placeholder script has a
single integration shim TODO marked in its module docstring. Wiring is
deliberately deferred until the deps are present and validated.

## Known constraints / gotchas

- **Ollama think:false** — qwen3.5:9b on `api/generate` requires
  `think: false`, otherwise `response` is empty. Already wired in
  `benchmarks/lib/model_client.py`. Do not silently switch to
  `api/chat`.
- **Backend purity** — A 120B request must not be answered by Ollama
  9B because Ollama also accepts unknown model ids (it errors, but if
  a wildcard were ever introduced this guard catches it). The
  `purity_guard` block in `model_profiles.yaml` is checked on every
  successful call.
- **Groq rate limits** — `retry: 2` on the profile. If you see HTTP
  429, lower the suite's sample sizes or insert sleeps.
- **Result directory grows** — each run writes a new JSONL. The
  summarizer reads everything in `benchmarks/results/`. Move or delete
  old artifacts between independent measurement campaigns.
- **No mocking of `tests/`** — the repo's existing test suite (~1500+
  passing) is invariant. The benchmark harness is separate and lives
  under `benchmarks/`. Do not import the harness from `src/` core or
  vice versa.

## How to add a new benchmark

1. Edit `benchmarks/configs/benchmark_matrix.yaml`. Pick a `name`,
   `category`, existing or new `runner`, `metric`, sample sizes, and
   honest `status`.
2. If a new runner module is needed: create
   `benchmarks/runners/run_<name>.py`, expose a `run(profile_name, *,
   benchmark_name, sample_size, output_dir)` function, and register it
   in `RUNNER_MODULES` inside `benchmarks/run_suite.py`.
3. Use `benchmarks.lib.jsonl_writer.make_row(...)` to emit rows so the
   schema stays uniform.
4. Add the benchmark name to the relevant suite YAML.
5. Run `pytest -q tests/test_benchmarks_smoke.py` to confirm the
   harness still imports and emits valid JSONL.
