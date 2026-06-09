#!/usr/bin/env bash
# Run the smoke suite end-to-end on 9B + 120B and emit a summary.
#
# Activates venv313 (see CLAUDE.md), then walks benchmarks/suites/smoke.yaml.
# Real model calls are issued only for `enabled` benchmarks; the rest emit
# placeholder rows (1 per benchmark) so the pipeline completes uniformly.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

VENV="$HOME/デスクトップ/mobius_ai/venv313/bin/activate"
if [ -f "$VENV" ]; then
    # shellcheck disable=SC1090
    source "$VENV"
else
    echo "[warn] venv313 not found at $VENV — using current python." >&2
fi

PROFILES="${BENCH_PROFILES:-local-ollama-9b,groq-gpt-oss-120b}"

echo "=== smoke suite | profiles: $PROFILES ==="
python benchmarks/run_suite.py --suite smoke --profiles "$PROFILES"

echo
echo "=== summarising ==="
python scripts/summarize_benchmarks.py

echo
echo "Latest reports:"
ls -1t benchmarks/reports/*.md | head -3
