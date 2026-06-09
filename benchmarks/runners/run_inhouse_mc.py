"""In-house MMLU-style multiple-choice runner.

Asks the model to answer A/B/C/D for a small in-tree dataset. Designed so the
harness has at least one knowledge benchmark that runs fully offline (no HF
dataset download, no lm-eval-harness install).

Grading:
  - normalize the response, look for the first standalone A/B/C/D token
  - score 1 iff that token equals the gold answer
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.lib.config_loader import get_benchmark, get_profile
from benchmarks.lib.jsonl_writer import JsonlWriter, make_row, make_run_id
from benchmarks.lib.model_client import call_model
from benchmarks.lib.purity_guard import PurityViolation
from benchmarks.lib.sampling import stable_sample

DATA_PATH = REPO_ROOT / "benchmarks" / "data" / "inhouse_mc_smoke.jsonl"
DEFAULT_RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"

PROMPT_TEMPLATE = (
    "Answer the following multiple-choice question. "
    "Respond with ONLY the single letter A, B, C, or D — no explanation.\n\n"
    "Question: {question}\n"
    "A) {a}\n"
    "B) {b}\n"
    "C) {c}\n"
    "D) {d}\n\n"
    "Answer:"
)

LETTER_RE = re.compile(r"\b([ABCD])\b")


def _extract_letter(text: str) -> str | None:
    if not text:
        return None
    text = text.strip()
    # Trim common preamble like "Answer:" or "The answer is"
    for prefix in ("answer:", "the answer is", "answer is"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
    m = LETTER_RE.search(text.upper())
    return m.group(1) if m else None


def _load_items() -> list[dict]:
    out = []
    with DATA_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def run(
    profile_name: str,
    *,
    sample_size: int | None = None,
    output_dir: Path | None = None,
    benchmark_name: str = "inhouse_mc_smoke",
) -> Path:
    profile = get_profile(profile_name)
    matrix = get_benchmark(benchmark_name)
    if sample_size is None:
        sample_size = int(matrix.get("smoke_sample_size", 10))

    output_dir = output_dir or DEFAULT_RESULTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    items = _load_items()
    selected = stable_sample(items, sample_size, seed=f"imc:{benchmark_name}")

    run_id = make_run_id(f"{benchmark_name}_{profile_name}")
    out_path = output_dir / f"{run_id}.jsonl"

    print(f"[inhouse_mc] profile={profile_name} items={len(selected)} → {out_path}",
          flush=True)

    with JsonlWriter(out_path) as w:
        for item in selected:
            ch = item["choices"]
            prompt = PROMPT_TEMPLATE.format(
                question=item["question"],
                a=ch["A"], b=ch["B"], c=ch["C"], d=ch["D"],
            )
            try:
                cr = call_model(prompt, profile)
            except PurityViolation as e:
                cr = type("X", (), {})()
                cr.text = ""
                cr.latency_ms = 0
                cr.tokens_in = None
                cr.tokens_out = None
                cr.error = f"PurityViolation: {e}"

            predicted = _extract_letter(cr.text) if not getattr(cr, "error", None) else None
            if getattr(cr, "error", None):
                score = None
            else:
                score = 1.0 if predicted == item["answer"] else 0.0

            w.write(make_row(
                run_id=run_id,
                model_profile=profile_name,
                benchmark=benchmark_name,
                task=item.get("subject", "*"),
                sample_id=item["id"],
                prompt=prompt,
                output=cr.text,
                score=score,
                metric_name="accuracy",
                latency_ms=cr.latency_ms,
                tokens_in=cr.tokens_in,
                tokens_out=cr.tokens_out,
                error=cr.error,
                metadata={
                    "gold": item["answer"],
                    "predicted": predicted,
                    "response_excerpt": (cr.text or "")[:200],
                },
            ))
            print(
                f"  [{item['id']}] subj={item.get('subject')} "
                f"gold={item['answer']} pred={predicted} score={score}",
                flush=True,
            )

    print(f"[inhouse_mc] wrote {w.rows_written} rows", flush=True)
    return out_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="In-house MC runner")
    p.add_argument("--profile", required=True)
    p.add_argument("--sample-size", type=int, default=None)
    p.add_argument("--output-dir", type=str, default=None)
    p.add_argument("--benchmark", type=str, default="inhouse_mc_smoke")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    out_dir = Path(args.output_dir) if args.output_dir else None
    path = run(
        args.profile, sample_size=args.sample_size, output_dir=out_dir,
        benchmark_name=args.benchmark,
    )
    print(f"[inhouse_mc] done → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
