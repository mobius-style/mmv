"""Schema + family-distribution tests for the OPERATE-FR Smoke-100 dataset."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.operate_fr.harness.schemas import (
    SchemaError,
    validate_label,
    validate_task,
)

DATA = REPO_ROOT / "benchmarks" / "operate_fr" / "data"


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def test_smoke100_count() -> None:
    tasks = _read_jsonl(DATA / "smoke100.jsonl")
    assert len(tasks) == 100


def test_smoke100_family_distribution() -> None:
    tasks = _read_jsonl(DATA / "smoke100.jsonl")
    fams = Counter(t["family"] for t in tasks)
    assert fams["volatile_current"]      == 35
    assert fams["stale_premise_trap"]    == 15
    assert fams["stable_control"]        == 25
    assert fams["date_boundary"]         == 10
    assert fams["query_neutrality"]      == 10
    assert fams["ambiguous_time_frame"]  == 5
    assert fams.get("freshness_long_run", 0) == 0


def test_smoke100_all_tasks_validate() -> None:
    tasks = _read_jsonl(DATA / "smoke100.jsonl")
    for t in tasks:
        validate_task(t)  # raises on failure


def test_labels_validate_and_align_with_tasks() -> None:
    tasks = _read_jsonl(DATA / "smoke100.jsonl")
    labels = _read_jsonl(DATA / "labels" / "smoke100_route_labels.jsonl")
    assert len(labels) == len(tasks)
    task_ids = {t["id"] for t in tasks}
    for lab in labels:
        validate_label(lab)
        assert lab["task_id"] in task_ids


def test_schema_rejects_unknown_family() -> None:
    bad = {
        "id": "x", "suite": "smoke100", "family": "not_a_family",
        "domain": "x", "language": "en", "user_prompt": "?",
        "temporal_volatility": "none", "requires_current_verification": False,
        "tool_mode": "no_tool", "expected_routes": ["answer"],
        "disallowed_routes": [], "primary_metric": "route_correctness",
    }
    with pytest.raises(SchemaError):
        validate_task(bad)


def test_schema_rejects_unknown_route() -> None:
    bad = {
        "id": "x", "suite": "smoke100", "family": "stable_control",
        "domain": "math", "language": "en", "user_prompt": "?",
        "temporal_volatility": "none", "requires_current_verification": False,
        "tool_mode": "no_tool", "expected_routes": ["FOOBAR"],
        "disallowed_routes": [], "primary_metric": "route_correctness",
    }
    with pytest.raises(SchemaError):
        validate_task(bad)
