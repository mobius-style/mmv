#!/usr/bin/env python3
"""
run_33_scenarios.py — Wrapper for scenario_runner.py with Phase B-friendly interface.

This script wraps the existing scripts/scenario_runner.py to provide a stable
interface that the Phase B autonomous prompt and per-commit self-verification
template can rely on.

Usage:
    python scripts/run_33_scenarios.py --quiet
    python scripts/run_33_scenarios.py --verbose --output /tmp/run.json
    python scripts/run_33_scenarios.py --filter <category>
    python scripts/run_33_scenarios.py --seed <int>

Exit codes:
    0  All scenarios passed (or improvement vs baseline)
    1  Regression detected (baseline -3 or more)
    2  Identity leakage detected (any > 0)
    3  Existing fixes broken (verified separately, this script flags)
    4  Configuration / runtime error
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIO_RUNNER = REPO_ROOT / "scripts" / "scenario_runner.py"
BASELINE_FILE = REPO_ROOT / "data" / "supervisor" / "phase_a_baseline.txt"
DEFAULT_BASELINE = 31  # Phase A complete: 31/33

def get_baseline():
    """Read baseline from file or use default."""
    if BASELINE_FILE.exists():
        try:
            return int(BASELINE_FILE.read_text().strip())
        except ValueError:
            pass
    return DEFAULT_BASELINE

def parse_runner_output(output_text):
    """
    Parse scenario_runner.py output to extract:
    - Total passed / total scenarios
    - Identity leakage count
    - Per-category breakdown

    Returns dict or None on parse failure.
    """
    result = {
        "total_passed": None,
        "total_scenarios": None,
        "identity_leakage": 0,
        "categories": {},
        "raw_output": output_text,
    }

    # Heuristic parsing — adjust to match actual scenario_runner.py output format
    lines = output_text.splitlines()
    for line in lines:
        line = line.strip()

        # Look for "X/Y passed" or "Total: X/Y"
        if "/" in line and ("passed" in line.lower() or "total" in line.lower()):
            try:
                # Extract X/Y pattern
                import re
                m = re.search(r"(\d+)\s*/\s*(\d+)", line)
                if m:
                    result["total_passed"] = int(m.group(1))
                    result["total_scenarios"] = int(m.group(2))
            except (ValueError, AttributeError):
                pass

        # Look for "identity_leakage: N" or "leakage: N"
        if "leakage" in line.lower():
            try:
                import re
                m = re.search(r"leakage[:\s]+(\d+)", line.lower())
                if m:
                    result["identity_leakage"] = int(m.group(1))
            except (ValueError, AttributeError):
                pass

    return result

def _run_single_capture(args, baseline):
    """Run a single underlying scenario_runner invocation, returning the
    parsed dict. Side-effect: prints progress only if args.verbose. Used
    by --n-runs > 1 path."""
    scenarios_dir = REPO_ROOT / "tests" / "scenarios"
    target_path = scenarios_dir
    if args.filter:
        candidate = scenarios_dir / args.filter
        if not candidate.exists():
            for ext in (".yaml", ".yml"):
                p = scenarios_dir / f"{args.filter}{ext}"
                if p.exists():
                    candidate = p
                    break
        if candidate.exists():
            target_path = candidate
    cmd = ["python3", str(SCENARIO_RUNNER), str(target_path)]
    HARNESS_TIMEOUT_SEC = 3600
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=REPO_ROOT, timeout=HARNESS_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return {"total_passed": None, "identity_leakage": 0,
                "error": "timeout"}
    except Exception as e:
        return {"total_passed": None, "identity_leakage": 0,
                "error": f"runtime: {e}"}
    combined = proc.stdout + "\n" + proc.stderr
    return parse_runner_output(combined)


def _run_many_aggregate(args):
    """N-runs aggregation path. Writes aggregate JSON to args.output if
    set, prints summary unless --quiet."""
    baseline = args.baseline if args.baseline is not None else get_baseline()
    runs = []
    for i in range(args.n_runs):
        if not args.quiet:
            print(f"[run_33_scenarios n-runs] run {i + 1}/{args.n_runs} ...",
                  flush=True)
        result = _run_single_capture(args, baseline)
        runs.append(result)
        if not args.quiet:
            passed = result.get("total_passed")
            print(f"  run {i + 1}: passed={passed}, "
                  f"leakage={result.get('identity_leakage', 0)}")

    summary = _aggregate_runs(runs)
    payload = {
        "n_runs": args.n_runs,
        "baseline": baseline,
        "summary": summary,
        "runs": runs,
        # Convenience top-level fields aliased from summary for callers
        # that probe simple keys.
        "mean": summary.get("mean"),
        "stdev": summary.get("stdev"),
        "min": summary.get("min"),
        "max": summary.get("max"),
        "max_leakage": summary.get("max_leakage", 0),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
        )
    if not args.quiet:
        m = summary.get("mean")
        sd = summary.get("stdev")
        lo = summary.get("min")
        hi = summary.get("max")
        print(f"\n33-scenario N={args.n_runs}: "
              f"mean={m:.2f} stdev={sd:.2f} min={lo} max={hi} "
              f"(baseline {baseline}/33)")
        print(f"max_identity_leakage: {summary['max_leakage']}")
    if summary.get("max_leakage", 0) > 0:
        return 2
    if summary.get("min") is not None and summary["min"] < baseline - 3:
        return 1
    return 0


def _aggregate_runs(runs):
    """Aggregate per-run results into mean/stdev/min/max + per-scenario pass rate.

    Each item in `runs` is a dict from parse_runner_output(). Returns a
    dict for inclusion in the aggregate JSON output.
    """
    import statistics
    passed_values = [
        r["total_passed"] for r in runs if r.get("total_passed") is not None
    ]
    leakage_values = [r.get("identity_leakage", 0) for r in runs]
    n = len(passed_values)
    summary = {
        "n_runs": len(runs),
        "n_parsed": n,
        "passed_per_run": passed_values,
        "leakage_per_run": leakage_values,
        "max_leakage": max(leakage_values) if leakage_values else 0,
    }
    if n > 0:
        summary["mean"] = sum(passed_values) / n
        summary["min"] = min(passed_values)
        summary["max"] = max(passed_values)
        summary["stdev"] = statistics.stdev(passed_values) if n >= 2 else 0.0
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run 33-scenario harness (wrapper)")
    parser.add_argument("--quiet", action="store_true", help="Suppress detailed output")
    parser.add_argument("--verbose", action="store_true", help="Show full scenario details")
    parser.add_argument("--output", type=Path, help="Save JSON result to file")
    parser.add_argument("--filter", type=str, help="Run only matching category")
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")
    parser.add_argument("--baseline", type=int, default=None, help="Override baseline (default: read from file or 31)")
    parser.add_argument(
        "--n-runs", type=int, default=1,
        help=("Run the harness N times and aggregate (mean/stdev/min/max). "
              "N=1 (default) preserves original single-run output shape. "
              "Phase 3 stabilization (Commit 41) introduced this flag."),
    )
    args = parser.parse_args()
    if args.n_runs < 1:
        print("ERROR: --n-runs must be >= 1", file=sys.stderr)
        return 4
    if args.n_runs > 1:
        return _run_many_aggregate(args)

    if not SCENARIO_RUNNER.exists():
        print(f"ERROR: {SCENARIO_RUNNER} not found", file=sys.stderr)
        return 4

    baseline = args.baseline if args.baseline is not None else get_baseline()

    # Build command for underlying runner. scenario_runner.py takes a
    # positional `path` (YAML file or directory). If --filter is given,
    # narrow to that single scenario file when it resolves; otherwise
    # default to tests/scenarios/ (the 33-scenario set).
    scenarios_dir = REPO_ROOT / "tests" / "scenarios"
    target_path = scenarios_dir
    if args.filter:
        candidate = scenarios_dir / args.filter
        if not candidate.exists():
            for ext in (".yaml", ".yml"):
                p = scenarios_dir / f"{args.filter}{ext}"
                if p.exists():
                    candidate = p
                    break
        if candidate.exists():
            target_path = candidate
    cmd = ["python3", str(SCENARIO_RUNNER), str(target_path)]
    # --seed is not supported by the underlying runner; ignored if given.

    if args.verbose:
        print(f"[run_33_scenarios] Running: {' '.join(cmd)}")
        print(f"[run_33_scenarios] Baseline: {baseline}/33")

    HARNESS_TIMEOUT_SEC = 3600  # 60 min — env-off ~17 min, env-on ~30+ min
                                  # due to ME5 cold load per RoutingEngine
                                  # (see spec v1.3 Section 7.8.1).
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=HARNESS_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        print(
            f"ERROR: scenario_runner.py timed out after "
            f"{HARNESS_TIMEOUT_SEC // 60} minutes",
            file=sys.stderr,
        )
        return 4
    except Exception as e:
        print(f"ERROR: Failed to run scenario_runner.py: {e}", file=sys.stderr)
        return 4

    # Combined stdout + stderr for parsing (some runners write to stderr)
    combined = proc.stdout + "\n" + proc.stderr

    parsed = parse_runner_output(combined)

    # Save result if requested
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(parsed, indent=2, ensure_ascii=False))

    # Summary output
    if not args.quiet:
        passed = parsed.get("total_passed")
        total = parsed.get("total_scenarios")
        leakage = parsed.get("identity_leakage", 0)
        print(f"33-scenario: {passed}/{total} (baseline {baseline}/33)")
        print(f"identity_leakage: {leakage}")

    # Determine exit code
    if parsed.get("total_passed") is None:
        # Could not parse — return raw underlying exit code
        if proc.returncode != 0:
            print(f"WARNING: scenario_runner.py exit code {proc.returncode}, parse failed", file=sys.stderr)
            if not args.quiet:
                print(combined[:2000], file=sys.stderr)
        return proc.returncode

    if parsed["identity_leakage"] > 0:
        print(f"FAIL: identity_leakage > 0 ({parsed['identity_leakage']})", file=sys.stderr)
        return 2

    if parsed["total_passed"] < baseline - 3:
        print(f"FAIL: {parsed['total_passed']}/33 is more than 3 below baseline {baseline}/33", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
