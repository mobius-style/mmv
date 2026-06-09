#!/usr/bin/env bash
# Run the FULL suite. CAUTION: SWE-bench, WebArena, GAIA, ToolBench all need
# external installs and substantial wall-clock / disk / cloud spend.
# Requires explicit confirmation via BENCH_CONFIRM=I_UNDERSTAND.
set -euo pipefail

if [ "${BENCH_CONFIRM:-}" != "I_UNDERSTAND" ]; then
    echo "Refusing to run full suite without BENCH_CONFIRM=I_UNDERSTAND."
    echo "The full suite includes SWE-bench / WebArena / GAIA placeholders that"
    echo "expect external installs, large dataset downloads, and possibly"
    echo "non-trivial cloud spend. Read docs/BENCHMARK_RUNBOOK.md first."
    exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

VENV="$HOME/デスクトップ/mobius_ai/venv313/bin/activate"
if [ -f "$VENV" ]; then
    # shellcheck disable=SC1090
    source "$VENV"
fi

PROFILES="${BENCH_PROFILES:-local-ollama-9b,groq-gpt-oss-120b}"
echo "=== FULL suite | profiles: $PROFILES ==="
python benchmarks/run_suite.py --suite full --profiles "$PROFILES"

echo
python scripts/summarize_benchmarks.py
