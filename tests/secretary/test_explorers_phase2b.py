"""Phase-2b explorer tests: pattern_library + docs_md.

Phase 2 introduced 4 explorers (eval-results, git-history, bench-summary,
repo-grep). Phase 2b adds two more driven by the actual hot directories
in the recent git history:

  - `pattern-library`  → config/pattern_library/*.jsonl
  - `docs`             → docs/*.md

These are read-only, no-network explorers following the same conventions
as the rest of Phase 2.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from addons.secretary.explorers import docs_md, pattern_library


# ---------- pattern_library ----------

def _pattern(
    *, id: str, sub_topic: str, status: str = "active",
    deprecated: bool = False, hit_count: int = 0, priority: int = 100,
    examples: int = 3, negatives: int = 2, xling: int = 4,
    history: list[dict] | None = None,
) -> dict:
    return {
        "id": id,
        "topic": "test_topic",
        "sub_topic": sub_topic,
        "priority": priority,
        "examples": [f"ex{i}" for i in range(examples)],
        "negative_examples": [f"neg{i}" for i in range(negatives)],
        "cross_lingual_test_queries": [
            {"lang": "ja", "query": f"q{i}", "expected_match": True,
             "min_cosine": 0.6}
            for i in range(xling)
        ],
        "lifecycle": {
            "audit_status": status,
            "hit_count": hit_count,
            "history": history or [],
        },
        "deprecated": deprecated,
    }


def _write_lib(tmp_path: Path, files: dict[str, list[dict]]) -> Path:
    lib = tmp_path / "pattern_library"
    lib.mkdir()
    for name, rows in files.items():
        path = lib / f"{name}.jsonl"
        path.write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n",
            encoding="utf-8",
        )
    return lib


def test_pattern_library_counts_by_status(tmp_path: Path) -> None:
    # status counts and deprecated counts are independent — a pattern can
    # be both audit_status=active and deprecated=True transiently. Tests
    # treat them as separate buckets.
    lib = _write_lib(tmp_path, {
        "topic_a": [
            _pattern(id="p1", sub_topic="st_a"),  # active, not deprecated
            _pattern(id="p2", sub_topic="st_a", status="quarantined"),
            _pattern(id="p3", sub_topic="st_b", deprecated=True),
        ],
    })
    d = pattern_library.digest_library(lib)
    assert d.total_rows == 3
    assert d.total_active == 2  # p1 + p3 (p3 is deprecated but still active-status)
    assert d.total_quarantined == 1
    assert d.total_deprecated == 1


def test_pattern_library_aggregates_sub_topics(tmp_path: Path) -> None:
    lib = _write_lib(tmp_path, {
        "topic_a": [
            _pattern(id=f"a_{i}", sub_topic="st_a") for i in range(5)
        ] + [
            _pattern(id=f"b_{i}", sub_topic="st_b") for i in range(3)
        ],
        "topic_b": [
            _pattern(id=f"c_{i}", sub_topic="st_a") for i in range(2)
        ],
    })
    d = pattern_library.digest_library(lib)
    assert d.sub_topic_totals["st_a"] == 7  # 5 + 2 across both files
    assert d.sub_topic_totals["st_b"] == 3


def test_pattern_library_recent_events_ordering(tmp_path: Path) -> None:
    lib = _write_lib(tmp_path, {
        "topic_a": [
            _pattern(
                id="p1", sub_topic="st_a",
                history=[
                    {"timestamp": "2026-01-01T00:00:00Z",
                     "event": "created", "actor": "ci"},
                    {"timestamp": "2026-03-01T00:00:00Z",
                     "event": "updated", "actor": "ci"},
                ],
            ),
            _pattern(
                id="p2", sub_topic="st_b",
                history=[
                    {"timestamp": "2026-02-01T00:00:00Z",
                     "event": "created", "actor": "ci"},
                ],
            ),
        ],
    })
    d = pattern_library.digest_library(lib, recent_events_n=10)
    # Newest first
    assert d.recent_events[0][1] == "p1"
    assert d.recent_events[0][0] == "2026-03-01T00:00:00Z"
    assert d.recent_events[-1][0] == "2026-01-01T00:00:00Z"


def test_pattern_library_render_includes_sections(tmp_path: Path) -> None:
    lib = _write_lib(tmp_path, {
        "topic_a": [_pattern(id="p1", sub_topic="st_a")],
    })
    md = pattern_library.build_digest(lib)
    assert "# Pattern-library digest" in md
    assert "## Totals" in md
    assert "## Per-file" in md
    assert "## Sub-topic saturation" in md


def test_pattern_library_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        pattern_library.digest_library(tmp_path / "nope")


def test_pattern_library_real_dir_resolves() -> None:
    """Canary: the real on-disk library should be parseable end-to-end."""
    repo = Path(__file__).resolve().parents[2]
    lib = repo / "config" / "pattern_library"
    if not lib.exists():
        pytest.skip("config/pattern_library/ not present in this checkout")
    d = pattern_library.digest_library(lib)
    assert d.total_rows > 0, "no patterns parsed from real library"
    assert len(d.file_digests) >= 1


# ---------- docs_md ----------

def _write_doc(
    path: Path, *, title: str = "Title", body: str = "Summary line.",
    mtime: float | None = None,
) -> None:
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    if mtime is not None:
        import os
        os.utime(path, (mtime, mtime))


def test_docs_md_groups_by_prefix(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    _write_doc(docs / "PHASE_4_REPORT.md", title="P4")
    _write_doc(docs / "PHASE_5A_REPORT.md", title="P5A")
    _write_doc(docs / "RC3_2_REPORT.md", title="RC32")
    groups = docs_md.digest_docs(docs)
    assert "PHASE" in groups
    assert "RC" in groups
    assert len(groups["PHASE"]) == 2


def test_docs_md_recent_days_filter(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    fresh = (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()
    old = (datetime.now(timezone.utc) - timedelta(days=60)).timestamp()
    _write_doc(docs / "FRESH_DOC.md", mtime=fresh)
    _write_doc(docs / "OLD_DOC.md", mtime=old)
    groups = docs_md.digest_docs(docs, recent_days=7)
    # OLD_DOC should be filtered out
    flat = [e.path.name for es in groups.values() for e in es]
    assert "FRESH_DOC.md" in flat
    assert "OLD_DOC.md" not in flat


def test_docs_md_extracts_title_and_summary(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    p = docs / "EXAMPLE_REPORT.md"
    p.write_text(
        "# Example title\n\nThe first paragraph is the summary.\n"
        "It can span multiple lines.\n\n## Section two\n\nIgnored.\n",
        encoding="utf-8",
    )
    groups = docs_md.digest_docs(docs)
    # _classify_prefix takes only the first uppercase token, so the
    # group is "EXAMPLE", not "EXAMPLE_REPORT".
    entry = groups["EXAMPLE"][0]
    assert entry.title == "Example title"
    assert "first paragraph is the summary" in entry.summary


def test_docs_md_real_dir_resolves() -> None:
    """Canary: the real docs/ should produce a non-empty digest."""
    repo = Path(__file__).resolve().parents[2]
    docs = repo / "docs"
    if not docs.exists():
        pytest.skip("docs/ not present")
    md = docs_md.build_digest(docs, recent_days=365)
    assert "# Docs digest" in md
    assert "groups: **" in md
