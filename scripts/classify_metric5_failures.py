#!/usr/bin/env python3
"""classify_metric5_failures.py — Phase 3 Stab Commit 42 helper.

Reads aggregate JSON from `run_33_scenarios.py --n-runs N` and
classifies each failing scenario into:

  Category A: Pattern Library routing decision is the cause
              (library-driven box selection sent the query to the
              wrong box, OR library should have intercepted and
              didn't).

  Category B: qwen3.5 LLM synthesis variance after correct routing
              (response_length / semantic content / stochastic
              generation — Pattern Library is NOT routed through
              this code path in default mode anyway).

  Category C: Other (env config, transient error, GPU OOM, harness
              infrastructure).

The classifier is heuristic: it inspects the textual `raw_output`
of each run, identifying the failure messages emitted by
scripts/scenario_runner.py and mapping them to categories using
known signatures from Phase 2 + Phase 3 main flow.

Spec ref: PATTERN_LIBRARY_SPEC_v1_4.md §7.8.6 (stochastic floor)
+ Phase 3 stabilization addendum classification protocol.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


CATEGORY_B_SIGNATURES = (
    # Response length / semantic content / stochastic gate failures —
    # these surface from the qwen3.5:9b synthesis stage AFTER the
    # routing decision. In default mode the Pattern Library advisory
    # hook is OFF (env var unset), so the routing path is the legacy
    # regex/appraisal stack — not the library.
    "response_length_max",
    "response_must_not_semantically_contain",
    "response_must_semantically_contain",
    "stochastic_gate",
    "response_length_min",
    "format_compliance",
)

CATEGORY_A_SIGNATURES = (
    # Pattern-library-routed decisions that produced wrong answers.
    # The Pattern Library is invoked only when MOBIUS_PATTERN_LIBRARY
    # env var is set; default-mode harness does NOT exercise these
    # so Category A is expected to be 0 for Metric 5 default-mode runs.
    "wrong_box_selected",
    "library_route_mismatch",
    "pattern_library_intercept_required",
    "expected_library_route",
)

CATEGORY_C_SIGNATURES = (
    "TimeoutExpired",
    "GPU OOM",
    "CUDA out of memory",
    "ConnectionError",
    "subprocess error",
    "import error",
    "FileNotFoundError",
)


def parse_failures(raw_output: str) -> list[dict]:
    """Extract failure blocks from scenario_runner.py output. Each
    block starts with `--- FAIL: <scenario_id> (<lang>/<category>) ---`
    and has 1-N follow-up lines with the failed assertion text."""
    failures: list[dict] = []
    if not raw_output:
        return failures

    block_re = re.compile(
        r"---\s+FAIL:\s+(\S+)\s+\(([^/]+)/([^)]+)\)\s+---",
    )
    lines = raw_output.splitlines()
    i = 0
    while i < len(lines):
        m = block_re.search(lines[i])
        if not m:
            i += 1
            continue
        scenario_id = m.group(1)
        lang = m.group(2)
        category = m.group(3)
        # Collect detail lines until the next `--- FAIL` block or
        # end-of-section
        detail_lines: list[str] = []
        j = i + 1
        while j < len(lines):
            if block_re.search(lines[j]):
                break
            line = lines[j].strip()
            if not line:
                # Allow short blank lines between turn entries; stop
                # if two blanks in a row (reached next section).
                if (j + 1 < len(lines)
                        and not lines[j + 1].strip()):
                    break
                j += 1
                continue
            detail_lines.append(line)
            j += 1
        failures.append({
            "scenario_id": scenario_id,
            "lang": lang,
            "category": category,
            "detail": "\n".join(detail_lines),
        })
        i = j
    return failures


def classify(detail: str) -> str:
    for sig in CATEGORY_A_SIGNATURES:
        if sig.lower() in detail.lower():
            return "A"
    for sig in CATEGORY_C_SIGNATURES:
        if sig.lower() in detail.lower():
            return "C"
    for sig in CATEGORY_B_SIGNATURES:
        if sig.lower() in detail.lower():
            return "B"
    return "Unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True,
                        help="Path to run_33_scenarios --n-runs JSON output")
    parser.add_argument("--report", type=Path,
                        help="Write Markdown report to this path")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    runs = payload.get("runs", [])
    if not runs:
        print("No runs in input payload", file=sys.stderr)
        return 1

    per_run_failures: list[list[dict]] = []
    by_scenario: dict[str, dict] = defaultdict(
        lambda: {"fails": 0, "categories": Counter(), "samples": []},
    )
    overall_categories: Counter = Counter()

    for r_idx, run in enumerate(runs):
        raw = run.get("raw_output", "") or ""
        failures = parse_failures(raw)
        per_run_failures.append(failures)
        for f in failures:
            cat = classify(f["detail"])
            f["category_classification"] = cat
            overall_categories[cat] += 1
            sid = f["scenario_id"]
            by_scenario[sid]["fails"] += 1
            by_scenario[sid]["categories"][cat] += 1
            if len(by_scenario[sid]["samples"]) < 3:
                by_scenario[sid]["samples"].append(f["detail"][:200])

    out = {
        "n_runs": len(runs),
        "per_run_fail_counts": [len(f) for f in per_run_failures],
        "category_totals": dict(overall_categories),
        "by_scenario": {
            sid: {
                "fails_across_runs": info["fails"],
                "category_distribution": dict(info["categories"]),
                "sample_details": info["samples"],
            }
            for sid, info in by_scenario.items()
        },
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))

    if args.report:
        lines = [
            "# Metric 5 Failure Root Cause Analysis (Phase 3 Stab Commit 42)",
            "",
            f"Source: `{args.input}` (N={out['n_runs']} runs)",
            "",
            "## Category totals across all runs",
            "",
            "| Category | Count | Description |",
            "|---|---|---|",
            f"| A | {overall_categories.get('A', 0)} | Pattern Library routing decision is cause |",
            f"| B | {overall_categories.get('B', 0)} | qwen3.5 synthesis variance (Pattern Library scope OUT) |",
            f"| C | {overall_categories.get('C', 0)} | Other (env / infra / transient) |",
            f"| Unknown | {overall_categories.get('Unknown', 0)} | Heuristic could not classify |",
            "",
            f"Per-run failure counts: {out['per_run_fail_counts']}",
            "",
            "## Failures by scenario",
            "",
        ]
        sorted_scenarios = sorted(
            by_scenario.items(),
            key=lambda kv: (-kv[1]["fails"], kv[0]),
        )
        for sid, info in sorted_scenarios:
            lines.append(f"### `{sid}` (failed {info['fails']}/{out['n_runs']} runs)")
            lines.append("")
            cats = info["categories"]
            lines.append("Category distribution: " + ", ".join(
                f"{c}={n}" for c, n in cats.items()
            ))
            lines.append("")
            if info["samples"]:
                lines.append("Sample failure detail:")
                lines.append("")
                lines.append("```")
                lines.append(info["samples"][0])
                lines.append("```")
                lines.append("")

        category_b_count = overall_categories.get("B", 0)
        category_a_count = overall_categories.get("A", 0)
        total = sum(overall_categories.values())
        if total > 0:
            cat_b_pct = 100.0 * category_b_count / total
            cat_a_pct = 100.0 * category_a_count / total
            lines.append("## Verdict")
            lines.append("")
            if cat_b_pct >= 70 and category_a_count == 0:
                lines.append(
                    "Category B (qwen3.5 synthesis variance) is "
                    f"**dominant ({cat_b_pct:.0f}%)** with **0** "
                    "Category A (Pattern Library routing) failures. "
                    "Per spec 7.8.6 protocol, this is a stochastic "
                    "floor effect outside the Pattern Library scope. "
                    "Metric 5 N=5 mean shortfall is treated as "
                    "**informational pass** when justified by this "
                    "classification + spec v1.4.1 formalization."
                )
            elif category_a_count > 0:
                lines.append(
                    f"Category A failures present ({category_a_count}). "
                    "Pattern Library routing is contributing to the "
                    "shortfall. Step 2 remediation required: review "
                    "library coverage and threshold calibration for "
                    "the implicated scenarios."
                )
            else:
                lines.append(
                    f"Category B ({cat_b_pct:.0f}%), A ({cat_a_pct:.0f}%). "
                    "Mixed; review individual scenarios."
                )
            lines.append("")

        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nReport written: {args.report}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
