"""Suite orchestrator.

Walks a suite YAML, dispatches each (benchmark, profile) to its runner, and
writes a Markdown report summarising what ran and what is placeholder-only.

Usage:
    python benchmarks/run_suite.py --suite smoke
    python benchmarks/run_suite.py --suite standard --profiles local-ollama-9b
    python benchmarks/run_suite.py --suite governance --profiles local-ollama-9b,groq-gpt-oss-120b
"""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.lib.config_loader import (
    get_benchmark,
    load_benchmark_matrix,
    load_suite,
)
from benchmarks.runners._placeholder import emit_placeholder
from benchmarks.runners import (
    run_agent_benchmarks,
    run_humaneval,
    run_inhouse_mc,
    run_lm_eval,
    run_mobius_governance,
    run_swebench,
)

RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"
REPORTS_DIR = REPO_ROOT / "benchmarks" / "reports"

RUNNER_MODULES = {
    "run_mobius_governance": run_mobius_governance,
    "run_inhouse_mc": run_inhouse_mc,
    "run_lm_eval": run_lm_eval,
    "run_humaneval": run_humaneval,
    "run_swebench": run_swebench,
    "run_agent_benchmarks": run_agent_benchmarks,
}


def _resolve_benchmark_list(suite: dict) -> list[dict]:
    spec = suite.get("benchmarks")
    if spec == "*":
        return [{"name": b["name"]} for b in load_benchmark_matrix()]
    return list(spec or [])


def _dispatch(
    benchmark_name: str,
    profile_name: str,
    sample_size: int | None,
    output_dir: Path,
) -> dict:
    """Call the right runner for one (benchmark, profile) pair."""
    try:
        bench = get_benchmark(benchmark_name)
    except KeyError as e:
        return {
            "benchmark": benchmark_name,
            "profile": profile_name,
            "status": "missing",
            "path": None,
            "error": str(e),
        }

    runner_name = bench.get("runner")
    runner = RUNNER_MODULES.get(runner_name)
    if runner is None:
        path = emit_placeholder(
            benchmark_name=benchmark_name,
            profile_name=profile_name,
            output_dir=output_dir,
            install_hint=f"unknown runner '{runner_name}'",
            explanation="no runner module wired",
        )
        return {"benchmark": benchmark_name, "profile": profile_name,
                "status": "placeholder", "path": str(path), "error": None}

    try:
        path = runner.run(
            profile_name,
            benchmark_name=benchmark_name,
            sample_size=sample_size,
            output_dir=output_dir,
        )
        is_placeholder = bench.get("status") == "placeholder" or (
            runner_name in ("run_lm_eval", "run_humaneval", "run_swebench",
                            "run_agent_benchmarks")
        )
        return {
            "benchmark": benchmark_name,
            "profile": profile_name,
            "status": "placeholder" if is_placeholder else "enabled",
            "path": str(path),
            "error": None,
        }
    except Exception as e:
        return {
            "benchmark": benchmark_name,
            "profile": profile_name,
            "status": "error",
            "path": None,
            "error": f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=4)}",
        }


def _write_orchestrator_report(suite_name: str, run_records: list[dict],
                               report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Benchmark orchestrator report — suite `{suite_name}`",
        "",
        "| Benchmark | Profile | Status | JSONL |",
        "|---|---|---|---|",
    ]
    for r in run_records:
        if r["path"]:
            try:
                path_str = Path(r["path"]).relative_to(REPO_ROOT).as_posix()
            except ValueError:
                path_str = str(r["path"])
        else:
            path_str = "—"
        lines.append(
            f"| {r['benchmark']} | {r['profile']} | {r['status']} | "
            f"`{path_str}` |"
        )
    errors = [r for r in run_records if r["error"]]
    if errors:
        lines += ["", "## Errors", ""]
        for r in errors:
            lines.append(f"- **{r['benchmark']}** / `{r['profile']}`: {r['error']}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_suite(
    suite_name: str,
    profiles: list[str] | None = None,
    output_dir: Path | None = None,
    reports_dir: Path | None = None,
) -> tuple[list[dict], Path]:
    suite = load_suite(suite_name)
    bench_list = _resolve_benchmark_list(suite)
    profiles = profiles or list(suite.get("profiles") or [])
    output_dir = output_dir or RESULTS_DIR
    reports_dir = reports_dir or REPORTS_DIR

    print(f"=== Suite: {suite_name} | profiles={profiles} | "
          f"benchmarks={len(bench_list)} ===", flush=True)

    records: list[dict] = []
    for profile in profiles:
        for entry in bench_list:
            name = entry["name"]
            sample_size = entry.get("sample_size")
            print(f"\n▶ {name} / {profile} (sample_size={sample_size})", flush=True)
            rec = _dispatch(name, profile, sample_size, output_dir)
            records.append(rec)
            print(f"  → status={rec['status']} path={rec['path']}", flush=True)

    from benchmarks.lib.jsonl_writer import iso_now
    stamp = iso_now().replace(":", "").replace("-", "")
    report_path = reports_dir / f"suite_{suite_name}_{stamp}_orchestrator.md"
    _write_orchestrator_report(suite_name, records, report_path)
    print(f"\nOrchestrator report → {report_path}", flush=True)
    return records, report_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a benchmark suite end-to-end")
    p.add_argument("--suite", required=True,
                   help="suite name (matches benchmarks/suites/<name>.yaml)")
    p.add_argument("--profiles", type=str, default=None,
                   help="comma-separated model profile keys (overrides suite default)")
    p.add_argument("--output-dir", type=str, default=None)
    p.add_argument("--reports-dir", type=str, default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    profiles = [p.strip() for p in args.profiles.split(",")] if args.profiles else None
    out_dir = Path(args.output_dir) if args.output_dir else None
    rep_dir = Path(args.reports_dir) if args.reports_dir else None
    run_suite(args.suite, profiles=profiles, output_dir=out_dir, reports_dir=rep_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
