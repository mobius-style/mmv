"""Placeholder for HumanEval / MBPP / LiveCodeBench.

These require:
  - the `human-eval` package (sandboxed Python execution)
  - the dataset (HF `openai_humaneval` for HumanEval, `mbpp` for MBPP)
  - care: HumanEval/MBPP grading runs candidate code; need sandbox

Install path:
    pip install human-eval datasets
    # for livecodebench:
    pip install livecodebench

After install, this script should:
  1. Pull N samples from the dataset (smoke_sample_size)
  2. Generate completions via the model profile
  3. Execute via human-eval sandbox
  4. Emit one normalized row per sample
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
    "pip install human-eval datasets  "
    "# (livecodebench: pip install livecodebench)"
)


def _have_humaneval() -> bool:
    return importlib.util.find_spec("human_eval") is not None


def run(
    profile_name: str,
    *,
    benchmark_name: str,
    sample_size: int | None = None,
    output_dir: Path | None = None,
) -> Path:
    output_dir = output_dir or DEFAULT_RESULTS_DIR
    if not _have_humaneval():
        return emit_placeholder(
            benchmark_name=benchmark_name,
            profile_name=profile_name,
            output_dir=output_dir,
            install_hint=INSTALL_HINT,
            explanation="human-eval not installed; coding benchmarks skipped",
        )
    return emit_placeholder(
        benchmark_name=benchmark_name,
        profile_name=profile_name,
        output_dir=output_dir,
        install_hint="human-eval found; integration shim TODO.",
        explanation="integration shim TODO (sandbox + dataset wiring)",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="HumanEval-family runner (placeholder)")
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
