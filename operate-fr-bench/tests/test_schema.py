"""Schema + dataset-shape tests for OPERATE-FR v0.1."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.schemas import (  # noqa: E402
    FAMILIES,
    ROUTES,
    TOOL_MODES,
    validate_label,
    validate_task,
)

DATA = ROOT / "data" / "smoke100.jsonl"
LABELS = ROOT / "data" / "labels" / "smoke100_route_labels.jsonl"
CORE500_DATA = ROOT / "data" / "core500.jsonl"
CORE500_LABELS = ROOT / "data" / "labels" / "core500_route_labels.jsonl"

EXPECTED_FAMILY_COUNTS = {
    "volatile_current": 35,
    "stale_premise_trap": 15,
    "stable_control": 25,
    "date_boundary": 10,
    "query_neutrality": 10,
    "ambiguous_time_frame": 5,
    "freshness_long_run": 0,
}

EXPECTED_CORE500_FAMILY_COUNTS = {
    fam: count * 5 for fam, count in EXPECTED_FAMILY_COUNTS.items()
}


def _read_jsonl(p: Path) -> list[dict]:
    out = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def test_smoke100_exists_and_count() -> None:
    assert DATA.exists(), f"Smoke-100 dataset missing: {DATA}"
    rows = _read_jsonl(DATA)
    assert len(rows) == 100, f"Smoke-100 must have 100 tasks, got {len(rows)}"


def test_family_distribution_exact() -> None:
    rows = _read_jsonl(DATA)
    fam_count = Counter(r["family"] for r in rows)
    for fam, expected in EXPECTED_FAMILY_COUNTS.items():
        assert fam_count.get(fam, 0) == expected, (
            f"family {fam!r}: expected {expected}, got {fam_count.get(fam, 0)}"
        )


def test_unique_ids() -> None:
    rows = _read_jsonl(DATA)
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == len(ids), "task ids must be unique"
    assert all(i.startswith("fr_smoke_") for i in ids)


def test_every_task_validates() -> None:
    rows = _read_jsonl(DATA)
    for r in rows:
        errs = validate_task(r)
        assert not errs, f"task {r['id']} failed: {errs}"


def test_routes_in_taxonomy() -> None:
    rows = _read_jsonl(DATA)
    for r in rows:
        for route in r["expected_routes"]:
            assert route in ROUTES, f"{r['id']}: unknown expected route {route!r}"
        for route in r["disallowed_routes"]:
            assert route in ROUTES, f"{r['id']}: unknown disallowed route {route!r}"
        # expected and disallowed must not intersect
        overlap = set(r["expected_routes"]) & set(r["disallowed_routes"])
        assert not overlap, f"{r['id']}: routes overlap: {overlap}"


def test_tool_modes_valid() -> None:
    rows = _read_jsonl(DATA)
    for r in rows:
        assert r["tool_mode"] in TOOL_MODES, (
            f"{r['id']}: bad tool_mode {r['tool_mode']!r}"
        )


def test_labels_exist_and_count() -> None:
    assert LABELS.exists(), f"Labels missing: {LABELS}"
    rows = _read_jsonl(LABELS)
    assert len(rows) == 100, f"Expected 100 labels, got {len(rows)}"


def test_labels_validate() -> None:
    rows = _read_jsonl(LABELS)
    for r in rows:
        errs = validate_label(r)
        assert not errs, f"label {r.get('task_id')} failed: {errs}"


def test_label_task_id_correspondence() -> None:
    tasks = _read_jsonl(DATA)
    labels = _read_jsonl(LABELS)
    task_ids = {t["id"] for t in tasks}
    label_ids = {l["task_id"] for l in labels}
    assert task_ids == label_ids, (
        f"task/label id mismatch: only_in_tasks={task_ids - label_ids}, "
        f"only_in_labels={label_ids - task_ids}"
    )


def test_preferred_route_in_allowed() -> None:
    rows = _read_jsonl(LABELS)
    for r in rows:
        assert r["preferred_route"] in r["allowed_routes"], (
            f"{r['task_id']}: preferred_route {r['preferred_route']!r} "
            f"not in allowed {r['allowed_routes']}"
        )


def test_stable_controls_allow_only_answer() -> None:
    tasks = {t["id"]: t for t in _read_jsonl(DATA)}
    labels = {l["task_id"]: l for l in _read_jsonl(LABELS)}
    for tid, t in tasks.items():
        if t["family"] != "stable_control":
            continue
        lab = labels[tid]
        assert lab["allowed_routes"] == ["answer"], (
            f"{tid}: stable_control label must allow only 'answer', "
            f"got {lab['allowed_routes']}"
        )
        # The over-verification failure mode hinges on these three. Refuse /
        # abstain on a stable arithmetic question is a different (rarer)
        # failure mode and not always listed in disallowed; we just enforce
        # the verification-side disallowances here.
        for forbidden in ("verify", "ask", "date_bound_answer"):
            assert forbidden in lab["disallowed_routes"], (
                f"{tid}: stable_control must disallow {forbidden!r}, got "
                f"{lab['disallowed_routes']}"
            )


def test_volatile_current_disallows_answer() -> None:
    """High-volatility volatile_current items must disallow the
    `answer` route. Medium-volatility items (e.g. package deprecation,
    minimum-wage levels that change every few years) may permit `answer`
    when the underlying fact is widely known and stable enough to risk
    a direct response.
    """
    tasks = {t["id"]: t for t in _read_jsonl(DATA)}
    labels = {l["task_id"]: l for l in _read_jsonl(LABELS)}
    for tid, t in tasks.items():
        if t["family"] != "volatile_current":
            continue
        if t.get("temporal_volatility") != "high":
            continue
        lab = labels[tid]
        assert "answer" in lab["disallowed_routes"], (
            f"{tid}: high-volatility volatile_current must disallow 'answer', "
            f"got disallowed={lab['disallowed_routes']}"
        )


def test_core500_candidate_exists_and_count() -> None:
    assert CORE500_DATA.exists(), f"Core-500 candidate missing: {CORE500_DATA}"
    rows = _read_jsonl(CORE500_DATA)
    assert len(rows) == 500, (
        f"Core-500 candidate must have 500 tasks, got {len(rows)}"
    )


def test_core500_candidate_family_distribution_exact() -> None:
    rows = _read_jsonl(CORE500_DATA)
    fam_count = Counter(r["family"] for r in rows)
    for fam, expected in EXPECTED_CORE500_FAMILY_COUNTS.items():
        assert fam_count.get(fam, 0) == expected, (
            f"family {fam!r}: expected {expected}, got {fam_count.get(fam, 0)}"
        )


def test_core500_candidate_validates() -> None:
    rows = _read_jsonl(CORE500_DATA)
    labels = _read_jsonl(CORE500_LABELS)
    assert len(labels) == 500, f"Expected 500 Core-500 labels, got {len(labels)}"

    for r in rows:
        errs = validate_task(r)
        assert not errs, f"task {r['id']} failed: {errs}"
        assert r["id"].startswith("fr_core500_")
        assert r["suite"] == "core500_candidate"
        assert r["derivation_method"] == "neutral_prompt_frame_variant"
        assert r["source_smoke100_id"].startswith("fr_smoke_")
        assert r["variant_index"] in {0, 1, 2, 3, 4}

    for r in labels:
        errs = validate_label(r)
        assert not errs, f"label {r.get('task_id')} failed: {errs}"

    task_ids = {t["id"] for t in rows}
    label_ids = {l["task_id"] for l in labels}
    assert task_ids == label_ids


def test_core500_candidate_has_five_variants_per_smoke_item() -> None:
    rows = _read_jsonl(CORE500_DATA)
    variants_by_source = {}
    for row in rows:
        variants_by_source.setdefault(row["source_smoke100_id"], set()).add(
            row["variant_index"]
        )

    smoke_ids = {row["id"] for row in _read_jsonl(DATA)}
    assert set(variants_by_source) == smoke_ids
    for source_id, variants in variants_by_source.items():
        assert variants == {0, 1, 2, 3, 4}, (
            f"{source_id}: expected five variants 0-4, got {sorted(variants)}"
        )
