"""CLI wrapper: python -m benchmarks.operate_fr.harness.score_cli --results ... --labels ... --out summary.json"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .score import score_results


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="OPERATE-FR scorer")
    p.add_argument("--results", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--dataset", default="benchmarks/operate_fr/data/smoke100.jsonl")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    results = _read_jsonl(Path(args.results))
    labels = _read_jsonl(Path(args.labels))
    tasks = _read_jsonl(Path(args.dataset))

    labels_by_task = {r["task_id"]: r for r in labels}
    tasks_by_id = {t["id"]: t for t in tasks}

    summary = score_results(results, labels_by_task, tasks_by_id)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"Wrote summary → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
