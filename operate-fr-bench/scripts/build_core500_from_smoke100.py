#!/usr/bin/env python3
"""Build OPERATE-FR Core-500 candidate data from Smoke-100.

This is a controlled expansion, not an independent new benchmark. Each
Smoke-100 task receives five neutral prompt frames, preserving the original
route family and labels. The purpose is to test whether RC3.3 behavior holds
over a larger N while keeping the v0.1 family distribution unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SMOKE = ROOT / "data" / "smoke100.jsonl"
SMOKE_LABELS = ROOT / "data" / "labels" / "smoke100_route_labels.jsonl"
CORE = ROOT / "data" / "core500.jsonl"
CORE_LABELS = ROOT / "data" / "labels" / "core500_route_labels.jsonl"

FRAMES = (
    "{prompt}",
    "Please answer this user question: {prompt}",
    "Handle the following request carefully: {prompt}",
    "User request: {prompt}",
    "Respond to this question without adding unsupported assumptions: {prompt}",
)


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    tasks = read_jsonl(SMOKE)
    labels = {row["task_id"]: row for row in read_jsonl(SMOKE_LABELS)}

    out_tasks: list[dict] = []
    out_labels: list[dict] = []
    seq = 1
    for task in tasks:
        base_id = task["id"]
        label = labels[base_id]
        for variant_index, frame in enumerate(FRAMES):
            new_id = f"fr_core500_{seq:03d}"
            seq += 1

            t = dict(task)
            t["id"] = new_id
            t["suite"] = "core500_candidate"
            t["user_prompt"] = frame.format(prompt=task["user_prompt"])
            t["source_smoke100_id"] = base_id
            t["variant_index"] = variant_index
            t["derivation_method"] = "neutral_prompt_frame_variant"
            out_tasks.append(t)

            l = dict(label)
            l["task_id"] = new_id
            l["source_smoke100_id"] = base_id
            l["variant_index"] = variant_index
            l["route_notes"] = (
                f"{label.get('route_notes', '')} Core-500 candidate: "
                "controlled neutral prompt-frame variant of Smoke-100."
            ).strip()
            out_labels.append(l)

    if len(out_tasks) != 500 or len(out_labels) != 500:
        raise RuntimeError(
            f"expected 500 tasks/labels, got {len(out_tasks)}/{len(out_labels)}"
        )

    write_jsonl(CORE, out_tasks)
    write_jsonl(CORE_LABELS, out_labels)
    print(f"Wrote {CORE} ({len(out_tasks)} rows)")
    print(f"Wrote {CORE_LABELS} ({len(out_labels)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
