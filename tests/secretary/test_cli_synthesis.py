"""Tests for the secretary CLI synthesis paths:

  - `review-packet --with-synthesis --dry-run-synthesis` (offline path,
    no network, prompt embedded in digest)
  - `review-packet --with-synthesis` without an API key (skip path,
    digest gets a clearly labelled "Synthesis skipped" section)
  - baseline: `review-packet` without flags produces no synthesis text
"""
from __future__ import annotations

from pathlib import Path

import pytest

from addons.secretary.cli import main


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


def test_dry_run_synthesis_embeds_prompt(tmp_path: Path) -> None:
    out = tmp_path / "digest.md"
    rc = main([
        "review-packet",
        "--target", str(PACKET_DIR),
        "--out", str(out),
        "--with-synthesis",
        "--dry-run-synthesis",
    ])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    # Dry-run path embeds the literal prompt in a fenced block.
    assert "Synthesis prompt (dry-run, not sent)" in text
    # Prompt body is recognizable.
    assert "Top 3 priorities" in text
    assert "Risks to flag" in text


def test_with_synthesis_skips_when_api_key_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    out = tmp_path / "digest.md"
    rc = main([
        "review-packet",
        "--target", str(PACKET_DIR),
        "--out", str(out),
        "--with-synthesis",
    ])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    # Skip path produces a clearly labelled section, no provider call.
    assert "## Synthesis skipped" in text
    assert "GROQ_API_KEY" in text


def test_review_packet_without_synthesis_is_unchanged(tmp_path: Path) -> None:
    """Baseline: the original structural-only digest path still works
    when --with-synthesis is not passed (no synthesis section appears)."""
    out = tmp_path / "digest.md"
    rc = main([
        "review-packet",
        "--target", str(PACKET_DIR),
        "--out", str(out),
    ])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "## Synthesis" not in text
    assert "MMV-Large synthesis" not in text
