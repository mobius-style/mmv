"""Cooperative halt switch for long-running secretary tasks.

Claude (or any supervising session) can touch
`addons/secretary/state/halt` to request that any halt-aware verb stop
cleanly at its next checkpoint. The verb raises `HaltRequested`, which
the CLI catches and surfaces with exit code 130 (SIGINT-style).

This is cooperative, not preemptive — a verb that does not call
`halt_check()` will not stop. New halt-aware code MUST call
`halt_check()` between coarse-grained steps (after each file read, before
each provider call, etc.).
"""
from __future__ import annotations

from pathlib import Path


HALT_FILE = (
    Path(__file__).resolve().parent / "halt"
)


class HaltRequested(Exception):
    """Raised by `halt_check()` when the halt file is present."""


def is_halted(halt_file: Path | None = None) -> bool:
    return (halt_file or HALT_FILE).exists()


def halt_check(halt_file: Path | None = None) -> None:
    """Raise HaltRequested if the supervisor has touched the halt file."""
    if is_halted(halt_file):
        raise HaltRequested(
            f"halt requested via {halt_file or HALT_FILE}"
        )


def request_halt(halt_file: Path | None = None) -> Path:
    """Programmatic halt request — primarily for tests. In normal use
    the supervisor just runs `touch addons/secretary/state/halt`."""
    target = halt_file or HALT_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    return target


def clear_halt(halt_file: Path | None = None) -> None:
    """Remove the halt file so subsequent verbs can run."""
    target = halt_file or HALT_FILE
    if target.exists():
        target.unlink()
