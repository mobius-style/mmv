"""Shared base for placeholder runners.

Each placeholder runner emits exactly ONE JSONL row with:
  - score: None
  - error: "PLACEHOLDER: <package> not installed / dataset not downloaded"
  - metadata.install_hint: shell-command suggestion

This keeps the summarize_benchmarks.py logic uniform — every benchmark in a
suite produces a JSONL file, and the report can show what failed vs ran.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.lib.config_loader import get_benchmark, get_profile
from benchmarks.lib.jsonl_writer import JsonlWriter, make_row, make_run_id


def emit_placeholder(
    benchmark_name: str,
    profile_name: str,
    output_dir: Path,
    install_hint: str,
    explanation: str = "",
) -> Path:
    """Write a single placeholder row and return the path."""
    profile = get_profile(profile_name)
    bench = get_benchmark(benchmark_name)
    _ = profile  # not used yet but checked-for-existence

    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = make_run_id(f"{benchmark_name}_{profile_name}_placeholder")
    out_path = output_dir / f"{run_id}.jsonl"

    with JsonlWriter(out_path) as w:
        w.write(make_row(
            run_id=run_id,
            model_profile=profile_name,
            benchmark=benchmark_name,
            task="*",
            sample_id="placeholder",
            prompt="",
            output="",
            score=None,
            metric_name=str(bench.get("metric", "n/a")),
            latency_ms=0,
            error=f"PLACEHOLDER: {explanation or 'runner not implemented'}",
            metadata={
                "install_hint": install_hint,
                "dataset": bench.get("dataset"),
                "requires_external_install": bench.get("requires_external_install", []),
                "requires_api_key": bench.get("requires_api_key", False),
                "status": bench.get("status"),
                "reproduce": (
                    f"# After installing prerequisites:\n"
                    f"python benchmarks/runners/{bench.get('runner')}.py "
                    f"--profile {profile_name} --benchmark {benchmark_name}"
                ),
            },
        ))
    print(
        f"[placeholder] {benchmark_name} profile={profile_name} "
        f"→ {out_path} (install_hint: {install_hint})",
        flush=True,
    )
    return out_path
