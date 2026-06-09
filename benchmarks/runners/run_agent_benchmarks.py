"""Placeholder for agent / chat-preference benchmarks.

Covers: GAIA, WebArena, AgentBench, ToolBench, MT-Bench, AlpacaEval, and a
local chatbot_arena_pairwise smoke variant.

Each of these has its own dataset format and execution sandbox; a uniform
bridge is non-trivial. For now this script emits a placeholder row so the
benchmark matrix is honoured by the harness pipeline, with a per-benchmark
install_hint specific to the requested benchmark.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.runners._placeholder import emit_placeholder

DEFAULT_RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"


HINTS = {
    "mt_bench": (
        "Install FastChat: pip install fschat[model_worker]. "
        "Run gen_model_answer.py and gen_judgment.py with judge=gpt-4."
    ),
    "alpaca_eval": (
        "pip install alpaca-eval; export OPENAI_API_KEY or ANTHROPIC_API_KEY; "
        "alpaca_eval --model_outputs <yours.json>."
    ),
    "chatbot_arena_pairwise": (
        "Provide local/chatbot_arena_pairwise_smoke.jsonl with model_a/model_b "
        "responses; wire a judge call (Anthropic or OpenAI)."
    ),
    "gaia": (
        "Clone gaia-benchmark/GAIA, fill HuggingFace credential, follow agent "
        "loop spec in docs."
    ),
    "webarena": (
        "Install WebArena: pip install playwright; playwright install. "
        "Spin up reference Docker containers for shopping/gitlab/reddit/etc."
    ),
    "agentbench": "Clone THUDM/AgentBench, follow per-task launcher.",
    "toolbench": "Clone OpenBMB/ToolBench; needs RapidAPI key for tool calls.",
}


def run(
    profile_name: str,
    *,
    benchmark_name: str,
    sample_size: int | None = None,
    output_dir: Path | None = None,
) -> Path:
    output_dir = output_dir or DEFAULT_RESULTS_DIR
    hint = HINTS.get(benchmark_name, "See docs/BENCHMARK_RUNBOOK.md for setup.")
    return emit_placeholder(
        benchmark_name=benchmark_name,
        profile_name=profile_name,
        output_dir=output_dir,
        install_hint=hint,
        explanation=f"agent/chat benchmark '{benchmark_name}' runner not implemented",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Agent/chat benchmarks (placeholder)")
    p.add_argument("--profile", required=True)
    p.add_argument("--benchmark", required=True)
    p.add_argument("--sample-size", type=int, default=None)
    p.add_argument("--output-dir", type=str, default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    out_dir = Path(args.output_dir) if args.output_dir else None
    run(args.profile, benchmark_name=args.benchmark,
        sample_size=args.sample_size, output_dir=out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
