"""Tests for the `explain` CLI verb."""
from __future__ import annotations

from pathlib import Path

import pytest

from addons.secretary.cli import main


def test_explain_known_verb_prints_spec(capsys: pytest.CaptureFixture) -> None:
    rc = main(["explain", "version"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# version" in out
    assert "reads" in out
    assert "writes" in out
    assert "halt_aware" in out


def test_explain_unknown_verb_returns_error(capsys: pytest.CaptureFixture) -> None:
    rc = main(["explain", "this_verb_does_not_exist"])
    assert rc == 2
    out = capsys.readouterr().out
    # The body should mention the missing verb name.
    assert "this_verb_does_not_exist" in out


def test_explain_review_packet_includes_network_section(capsys: pytest.CaptureFixture) -> None:
    """review-packet has a real network entry, not null — explain must
    surface that the verb can call out to a provider."""
    rc = main(["explain", "review-packet"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# review-packet" in out
    assert "synthesis" in out.lower() or "network" in out.lower()
