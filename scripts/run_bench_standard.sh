#!/usr/bin/env bash
# Run the standard suite. Most entries will emit placeholders unless lm-eval /
# human-eval / etc. are installed (see docs/BENCHMARK_RUNBOOK.md).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

VENV="$HOME/デスクトップ/mobius_ai/venv313/bin/activate"
if [ -f "$VENV" ]; then
    # shellcheck disable=SC1090
    source "$VENV"
fi

PROFILES="${BENCH_PROFILES:-local-ollama-9b,groq-gpt-oss-120b}"
echo "=== standard suite | profiles: $PROFILES ==="
python benchmarks/run_suite.py --suite standard --profiles "$PROFILES"

echo
python scripts/summarize_benchmarks.py
