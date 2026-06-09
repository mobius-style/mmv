"""Möbius governance probes runner.

Reads benchmarks/data/governance_probes.jsonl, asks the model each probe,
grades the response with rule-based grading, and emits the normalized JSONL
schema. No external dataset or HuggingFace download required.

Grader kinds:
  - expect_any_substring : score 1 iff at least one substring is present
  - forbid_any_substring : score 0 iff ANY substring is present (overrides)
  - expect_all_substrings: score 1 iff every substring is present

A probe with multiple expect_any_substring graders requires ALL of them to fire.
A probe with a forbid_* grader can flip the score to 0 even if expects matched.
The per-probe score is in {0.0, 1.0}; the benchmark metric ('governance_score')
is the mean across probes per (category, model_profile).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.lib.config_loader import get_benchmark, get_profile
from benchmarks.lib.jsonl_writer import JsonlWriter, make_row, make_run_id
from benchmarks.lib.model_client import call_model
from benchmarks.lib.purity_guard import PurityViolation
from benchmarks.lib.sampling import stable_sample

DATA_PATH = REPO_ROOT / "benchmarks" / "data" / "governance_probes.jsonl"
DEFAULT_RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"


def _load_probes() -> list[dict]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(DATA_PATH)
    out = []
    with DATA_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _grade(response: str, graders: list[dict]) -> tuple[float, list[str]]:
    """Apply graders. Return (score, notes).

    Notes record which graders fired/missed so judgement is auditable.
    """
    text = (response or "").lower()
    notes: list[str] = []

    pass_all_expects = True
    for g in graders:
        kind = g.get("kind")
        vals = [str(v).lower() for v in g.get("values", [])]

        if kind == "expect_any_substring":
            hit = any(v in text for v in vals)
            notes.append(f"expect_any[{'hit' if hit else 'miss'}]={vals[:3]}")
            if not hit:
                pass_all_expects = False

        elif kind == "expect_all_substrings":
            hits = [v for v in vals if v in text]
            ok = len(hits) == len(vals)
            notes.append(f"expect_all[{'hit' if ok else 'partial'}]={len(hits)}/{len(vals)}")
            if not ok:
                pass_all_expects = False

        elif kind == "forbid_any_substring":
            present = [v for v in vals if v in text]
            if present:
                notes.append(f"forbid[hit]={present[:3]}")
                return 0.0, notes
            notes.append("forbid[clean]")

        else:
            notes.append(f"unknown_grader[{kind}]")

    return (1.0 if pass_all_expects else 0.0), notes


def run(
    profile_name: str,
    *,
    sample_size: int | None = None,
    output_dir: Path | None = None,
    category_filter: str | None = None,
    benchmark_name: str = "mobius_governance",
) -> Path:
    profile = get_profile(profile_name)
    matrix = get_benchmark(benchmark_name)
    if sample_size is None:
        sample_size = int(matrix.get("smoke_sample_size", 12))

    output_dir = output_dir or DEFAULT_RESULTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    probes = _load_probes()
    if category_filter:
        probes = [p for p in probes if p.get("category") == category_filter]
    selected = stable_sample(probes, sample_size, seed=f"gov:{benchmark_name}")

    run_id = make_run_id(f"{benchmark_name}_{profile_name}")
    out_path = output_dir / f"{run_id}.jsonl"

    print(f"[governance] profile={profile_name} probes={len(selected)} → {out_path}",
          flush=True)

    with JsonlWriter(out_path) as w:
        for probe in selected:
            prompt = probe["query"]
            try:
                cr = call_model(prompt, profile)
            except PurityViolation as e:
                cr = type("X", (), {})()
                cr.text = ""
                cr.latency_ms = 0
                cr.tokens_in = None
                cr.tokens_out = None
                cr.error = f"PurityViolation: {e}"

            score: float | None
            grader_notes: list[str]
            if getattr(cr, "error", None):
                score, grader_notes = None, [f"call_error: {cr.error}"]
            else:
                score, grader_notes = _grade(cr.text, probe.get("graders", []))

            w.write(make_row(
                run_id=run_id,
                model_profile=profile_name,
                benchmark=benchmark_name,
                task=probe.get("category", "*"),
                sample_id=probe["id"],
                prompt=prompt,
                output=cr.text,
                score=score,
                metric_name="governance_score",
                latency_ms=cr.latency_ms,
                tokens_in=cr.tokens_in,
                tokens_out=cr.tokens_out,
                error=cr.error,
                metadata={
                    "expected_behavior": probe.get("expected_behavior"),
                    "graders_fired": grader_notes,
                    "response_excerpt": (cr.text or "")[:400],
                    "intent": probe.get("metadata", {}).get("intent"),
                },
            ))
            print(
                f"  [{probe['id']}] cat={probe.get('category')} "
                f"score={score} latency={cr.latency_ms}ms",
                flush=True,
            )

    print(f"[governance] wrote {w.rows_written} rows", flush=True)
    return out_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Möbius governance probes runner")
    p.add_argument("--profile", required=True,
                   help="model profile key from model_profiles.yaml")
    p.add_argument("--sample-size", type=int, default=None,
                   help="override default smoke_sample_size from benchmark_matrix.yaml")
    p.add_argument("--category", type=str, default=None,
                   help="filter probes to one category")
    p.add_argument("--output-dir", type=str, default=None)
    p.add_argument("--benchmark", type=str, default="mobius_governance",
                   help="benchmark_matrix entry name (mobius_governance / sycophancy_eval)")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    out_dir = Path(args.output_dir) if args.output_dir else None
    path = run(
        args.profile,
        sample_size=args.sample_size,
        output_dir=out_dir,
        category_filter=args.category,
        benchmark_name=args.benchmark,
    )
    print(f"[governance] done → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
