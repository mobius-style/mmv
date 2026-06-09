#!/bin/bash
# Orchestrate the 6 conditions × 4 benches in the order from spec §7 Phase 3.
# Ollama model swap discipline: unload current model before loading next.
set -e

OUTDIR="${1:?usage: run_all.sh <outdir> [--limit N]}"
shift
LIMIT_ARGS=""
if [ "$1" = "--limit" ]; then
    LIMIT_ARGS="--limit $2"
    shift 2
fi

cd "$(dirname "$0")/../.."
RUN_ID="frontier_smoke_$(date +%Y%m%d_%H%M%S)"

run_condition () {
    local cond="$1"
    for bench in mmlu_pro gpqa_diamond truthfulqa_mc1 simpleqa; do
        echo "===== $cond / $bench ====="
        python -m benchmarks.frontier_smoke.runner \
            --bench "$bench" --condition "$cond" --outdir "$OUTDIR" \
            --run-id "$RUN_ID" $LIMIT_ARGS
    done
}

# qwen3.5:9b conditions
run_condition raw_qwen35_9b
run_condition mmv_small

# Swap to gemma4:26b
echo "===== ollama stop qwen3.5:9b ====="
ollama stop qwen3.5:9b 2>/dev/null || true
sleep 2

run_condition raw_gemma4_26b
run_condition mmv_medium

# Unload local model before Groq calls (frees VRAM, not strictly needed)
echo "===== ollama stop gemma4:26b ====="
ollama stop gemma4:26b 2>/dev/null || true
sleep 2

# Groq conditions
run_condition raw_gpt_oss_120b
run_condition mmv_large

echo "===== ALL DONE: $RUN_ID ====="
echo "$RUN_ID" > "$OUTDIR/run_id.txt"
