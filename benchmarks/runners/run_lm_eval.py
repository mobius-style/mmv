"""Placeholder runner that bridges to lm-evaluation-harness.

lm-eval is NOT installed by default — keeps the runtime venv lean.
Install path:

    pip install lm-eval datasets

Then run, e.g.:

    python -m lm_eval \\
        --model openai-completions \\
        --model_args base_url=http://localhost:11434/v1,model=qwen3.5:9b \\
        --tasks mmlu \\
        --num_fewshot 0 \\
        --output_path benchmarks/results/lm_eval_mmlu_9b

This script's job for now is to:
  - confirm import of lm_eval (and emit install hint if missing)
  - if installed, shell out to `lm-eval` and merge its JSON output into our
    normalized JSONL schema (best-effort, one row per (benchmark, task))
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.runners._placeholder import emit_placeholder

DEFAULT_RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"

INSTALL_HINT = (
    "pip install lm-eval datasets  "
    "# then: python benchmarks/runners/run_lm_eval.py --profile <P> --benchmark <B>"
)


def _have_lm_eval() -> bool:
    return importlib.util.find_spec("lm_eval") is not None


def run(
    profile_name: str,
    *,
    benchmark_name: str,
    sample_size: int | None = None,
    output_dir: Path | None = None,
) -> Path:
    output_dir = output_dir or DEFAULT_RESULTS_DIR
    if not _have_lm_eval():
        return emit_placeholder(
            benchmark_name=benchmark_name,
            profile_name=profile_name,
            output_dir=output_dir,
            install_hint=INSTALL_HINT,
            explanation="lm-eval-harness not installed",
        )
    # When installed, this is the integration point. Left as TODO so we do
    # not silently call an environment that wasn't validated.
    return emit_placeholder(
        benchmark_name=benchmark_name,
        profile_name=profile_name,
        output_dir=output_dir,
        install_hint="lm-eval found; integration shim TODO. "
                     "See docs/BENCHMARK_RUNBOOK.md for the manual command.",
        explanation="integration shim TODO",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="lm-evaluation-harness bridge (placeholder)")
    p.add_argument("--profile", required=True)
    p.add_argument("--benchmark", required=True,
                   help="entry name from benchmark_matrix.yaml (e.g. mmlu, gsm8k)")
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
