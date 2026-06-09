"""Placeholder for SWE-bench / SWE-bench Lite.

Requires:
  - `swebench` package
  - Docker (for the test-execution sandbox)
  - significant disk space (~100GB for full benchmark images)

Install path:
    pip install swebench
    # ensure docker daemon is running, user is in `docker` group

After install, integration should:
  1. Resolve dataset split + sample_size
  2. For each instance: build a prompt with repo state + failing test
  3. Capture model patch (unified diff)
  4. Submit to SWE-bench evaluation harness (containerized)
  5. Emit one normalized row per instance with score = resolved (0|1)

NOT suitable for casual smoke runs — even one instance can take minutes and
several GB of disk.
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
    "pip install swebench && "
    "ensure Docker is running. "
    "Plan for ~100GB disk for SWE-bench full."
)


def _have_swebench() -> bool:
    return importlib.util.find_spec("swebench") is not None


def run(
    profile_name: str,
    *,
    benchmark_name: str,
    sample_size: int | None = None,
    output_dir: Path | None = None,
) -> Path:
    output_dir = output_dir or DEFAULT_RESULTS_DIR
    if not _have_swebench():
        return emit_placeholder(
            benchmark_name=benchmark_name,
            profile_name=profile_name,
            output_dir=output_dir,
            install_hint=INSTALL_HINT,
            explanation="swebench package not installed",
        )
    return emit_placeholder(
        benchmark_name=benchmark_name,
        profile_name=profile_name,
        output_dir=output_dir,
        install_hint="swebench found; integration shim TODO (docker + patch capture).",
        explanation="integration shim TODO",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SWE-bench runner (placeholder)")
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
