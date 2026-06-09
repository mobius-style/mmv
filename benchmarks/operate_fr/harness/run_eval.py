"""Evaluation runner for OPERATE-FR v0.1.

Three CLI entry points (each invocable via `python -m`):

    python -m benchmarks.operate_fr.harness.run_eval \\
        --suite benchmarks/operate_fr/configs/suite_smoke.yaml \\
        --profile dummy \\
        --out benchmarks/operate_fr/reports/dummy_smoke.jsonl

    python -m benchmarks.operate_fr.harness.score \\
        --results benchmarks/operate_fr/reports/dummy_smoke.jsonl \\
        --labels  benchmarks/operate_fr/data/labels/smoke100_route_labels.jsonl \\
        --out     benchmarks/operate_fr/reports/dummy_smoke_summary.json

    python -m benchmarks.operate_fr.harness.report \\
        --summary benchmarks/operate_fr/reports/dummy_smoke_summary.json \\
        --out     benchmarks/operate_fr/reports/smoke_dry_run_report.md
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import yaml

from .adapters import invoke
from .classify_route import RouteClassifier
from .schemas import validate_result, validate_task

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _load_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def run_suite(
    suite_path: Path,
    profile_name: str,
    out_path: Path,
    *,
    max_tasks: int | None = None,
) -> dict:
    suite = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    data_path = REPO_ROOT / suite["dataset"]

    tasks = _load_jsonl(data_path)
    for t in tasks:
        validate_task(t)

    if max_tasks is not None:
        tasks = tasks[:max_tasks]

    classifier = RouteClassifier()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"ok": 0, "errors": 0}

    with out_path.open("w", encoding="utf-8") as fh:
        for i, task in enumerate(tasks, 1):
            try:
                resp = invoke(task["user_prompt"], profile_name)
                cls = classifier.classify(
                    prompt=task["user_prompt"],
                    response=resp.text,
                    tool_calls=resp.tool_calls,
                )
                row = {
                    "task_id": task["id"],
                    "suite": task["suite"],
                    "family": task["family"],
                    "profile": profile_name,
                    "user_prompt": task["user_prompt"],
                    "response_text": resp.text,
                    "predicted_route": cls["route"],
                    "classifier_confidence": cls["confidence"],
                    "classifier_evidence": cls["evidence"],
                    "classifier_notes": cls["notes"],
                    "tool_calls": resp.tool_calls,
                    "latency_ms": resp.latency_ms,
                    "tokens_in": resp.tokens_in,
                    "tokens_out": resp.tokens_out,
                    "error": resp.error,
                }
                validate_result(row)
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                if resp.error:
                    counts["errors"] += 1
                else:
                    counts["ok"] += 1
                print(
                    f"  [{i}/{len(tasks)}] {task['id']} family={task['family']} "
                    f"→ {cls['route']} (conf={cls['confidence']}) "
                    f"lat={resp.latency_ms}ms err={resp.error or '-'}",
                    flush=True,
                )
            except Exception as e:  # do NOT crash whole run
                err_row = {
                    "task_id": task.get("id", f"unknown_{i}"),
                    "suite": task.get("suite", "?"),
                    "family": task.get("family", "?"),
                    "profile": profile_name,
                    "user_prompt": task.get("user_prompt", ""),
                    "response_text": "",
                    "predicted_route": None,
                    "classifier_confidence": 0.0,
                    "classifier_evidence": {},
                    "classifier_notes": "",
                    "tool_calls": [],
                    "latency_ms": 0,
                    "tokens_in": None,
                    "tokens_out": None,
                    "error": f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}",
                }
                try:
                    validate_result(err_row)
                except Exception:
                    pass
                fh.write(json.dumps(err_row, ensure_ascii=False) + "\n")
                counts["errors"] += 1
                print(f"  [{i}/{len(tasks)}] {task.get('id')} ERROR: {e}",
                      flush=True)

    return {
        "out_path": str(out_path),
        "counts": counts,
        "n_tasks": len(tasks),
        "profile": profile_name,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OPERATE-FR v0.1 runner")
    p.add_argument("--suite", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-tasks", type=int, default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    info = run_suite(
        Path(args.suite), args.profile, Path(args.out),
        max_tasks=args.max_tasks,
    )
    print(f"\nDone: {info}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
