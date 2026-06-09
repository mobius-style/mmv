"""Tests for the `list` CLI verb."""
from __future__ import annotations

from pathlib import Path

import pytest

from addons.secretary.cli import main


def test_list_runs_and_returns_zero(capsys: pytest.CaptureFixture) -> None:
    rc = main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Permission ladder" in out
    # All four canonical verbs should be named.
    for verb in ("version", "bump", "review-packet", "list"):
        assert verb in out


def test_list_writes_audit_log() -> None:
    """A successful list invocation produces a JSONL audit log entry."""
    from addons.secretary.state.audit import LOGS_DIR
    before = set(LOGS_DIR.glob("list_*.jsonl")) if LOGS_DIR.exists() else set()
    rc = main(["list"])
    assert rc == 0
    after = set(LOGS_DIR.glob("list_*.jsonl"))
    new = after - before
    assert len(new) >= 1, "list verb did not write an audit log"
