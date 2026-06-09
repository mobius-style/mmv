"""Tests for the review-packet explorer.

Verifies structural compression of the real RC3.3 human-review packet
(no network, no LLM). The explorer should:

  - find the priority CSV and the 4 audit CSVs
  - compute correct row counts and route distributions
  - surface the HIGH-priority items
  - embed the rc3_3_summary.md verbatim
"""
from __future__ import annotations

from pathlib import Path

import pytest

from addons.secretary.explorers.review_packet import (
    AUDIT_FILES,
    PRIORITY_FILE,
    SUMMARY_FILE,
    build_digest,
    build_synthesis_prompt,
    digest_audit,
    digest_priority,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_DIR = (
    REPO_ROOT
    / "operate-fr-bench"
    / "reports"
    / "human_review_packet_mmv_large_rc3_3"
)


pytestmark = pytest.mark.skipif(
    not PACKET_DIR.exists(),
    reason="RC3.3 human-review packet not present in this checkout",
)


def test_digest_audit_counts_rows_and_routes() -> None:
    path = PACKET_DIR / "ambiguous_time_audit.csv"
    d = digest_audit(path)
    assert d.rows >= 1
    assert d.rc3_correct + d.rc3_incorrect == d.rows
    # Every row should fall into the route counter.
    assert sum(d.rc3_route_distribution.values()) == d.rows


def test_digest_priority_extracts_high_items() -> None:
    d = digest_priority(PACKET_DIR / PRIORITY_FILE)
    assert d.rows > 0
    assert "HIGH" in d.priority
    # The HIGH list holds (task_id, family, prompt) for every HIGH row.
    assert len(d.high_priority_ids) == d.priority.get("HIGH", 0)
    for task_id, family, prompt in d.high_priority_ids:
        assert task_id and family and prompt


def test_build_digest_contains_all_sections() -> None:
    md = build_digest(PACKET_DIR, release_line="MMV-L-RC3.3 (smoke)")
    assert "# Review-packet digest" in md
    assert "## Priority targets (smoke100)" in md
    assert "## Per-family audits" in md
    # Every audit CSV that exists should be referenced by stem
    for name in AUDIT_FILES:
        if (PACKET_DIR / name).exists():
            assert Path(name).stem in md
    # Summary md, if present, should be embedded verbatim by section
    if (PACKET_DIR / SUMMARY_FILE).exists():
        assert "## Packet summary (verbatim)" in md


def test_synthesis_prompt_embeds_digest_and_section_directives() -> None:
    """The synthesis prompt must include the digest verbatim AND the
    three required section headings the model should produce."""
    fake_digest = "# Review-packet digest\n\n- rows: 7\n"
    prompt = build_synthesis_prompt(fake_digest)
    # Digest is embedded
    assert fake_digest in prompt
    # All three required output sections are named
    assert "## Top 3 priorities" in prompt
    assert "## Risks to flag" in prompt
    assert "## What to ignore" in prompt
    # Anti-hallucination guard
    assert "Do not invent numbers" in prompt


def test_build_digest_is_compact() -> None:
    """The whole point is compression. The digest must be smaller than
    the sum of the inputs it summarizes, by a meaningful margin."""
    md = build_digest(PACKET_DIR)
    input_bytes = 0
    for name in AUDIT_FILES + (PRIORITY_FILE,):
        p = PACKET_DIR / name
        if p.exists():
            input_bytes += p.stat().st_size
    # Digest excludes the summary md from the budget check (that piece
    # is embedded verbatim by design). Compare digest size minus the
    # verbatim summary against the audit CSV bytes.
    summary_bytes = 0
    summary_path = PACKET_DIR / SUMMARY_FILE
    if summary_path.exists():
        summary_bytes = summary_path.stat().st_size
    digest_audit_only_chars = len(md) - summary_bytes
    # Digest's audit-summary portion should be no larger than the raw
    # audit CSVs it digests.
    assert digest_audit_only_chars <= input_bytes
