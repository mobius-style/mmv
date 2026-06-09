"""Tests for the cooperative halt switch (addons.secretary.state.halt).

Halt is cooperative: only verbs that call `halt_check()` notice it.
We verify the primitive directly here (file create/check/clear);
verb-level halt behavior is covered in the CLI tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from addons.secretary.state import halt as halt_mod


def test_halt_check_no_file_does_nothing(tmp_path: Path) -> None:
    halt_file = tmp_path / "halt"
    assert halt_mod.is_halted(halt_file) is False
    halt_mod.halt_check(halt_file)  # should not raise


def test_halt_check_raises_when_file_present(tmp_path: Path) -> None:
    halt_file = tmp_path / "halt"
    halt_mod.request_halt(halt_file)
    assert halt_mod.is_halted(halt_file) is True
    with pytest.raises(halt_mod.HaltRequested):
        halt_mod.halt_check(halt_file)


def test_clear_halt_round_trip(tmp_path: Path) -> None:
    halt_file = tmp_path / "halt"
    halt_mod.request_halt(halt_file)
    assert halt_file.exists()
    halt_mod.clear_halt(halt_file)
    assert not halt_file.exists()
    # Clearing again is idempotent (no error).
    halt_mod.clear_halt(halt_file)


def test_default_halt_file_path() -> None:
    """Sanity: the default halt file lives at the documented location."""
    assert halt_mod.HALT_FILE.name == "halt"
    assert halt_mod.HALT_FILE.parent.name == "state"
