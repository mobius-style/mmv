"""JSONL audit log for secretary verb invocations.

Every CLI invocation opens an audit log at
`addons/secretary/state/logs/<verb>_<ts>.jsonl` and emits at least:

  - one `event: start` record (verb name, arguments)
  - zero or more `event: milestone` records (free-form notes)
  - one `event: end` record (status, duration_ms, optional error)

Logs are append-only and survive across runs so the supervising
Claude session can `Read` them to see what the secretary actually did.
Sensitive values (API keys) MUST NOT pass through the milestone
payload — `record()` strips known prefixes defensively.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOGS_DIR = Path(__file__).resolve().parent / "logs"

_SECRET_RX = re.compile(
    r"(gsk_[A-Za-z0-9_\-]{16,}|"
    r"sk-[A-Za-z0-9_\-]{16,}|"
    r"ghp_[A-Za-z0-9]{20,})"
)


def _scrub(value: Any) -> Any:
    """Defensive: redact obvious secret-shaped tokens from log payloads."""
    if isinstance(value, str):
        return _SECRET_RX.sub("***REDACTED***", value)
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


@dataclass
class AuditLogger:
    """Context manager that writes JSONL records about a verb run."""

    verb: str
    args: dict[str, Any] = field(default_factory=dict)
    logs_dir: Path = LOGS_DIR
    _path: Path | None = field(default=None, init=False)
    _t0: float = field(default=0.0, init=False)
    _ended: bool = field(default=False, init=False)

    @property
    def path(self) -> Path:
        assert self._path is not None, "audit logger not entered"
        return self._path

    def __enter__(self) -> "AuditLogger":
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")[:-3] + "Z"
        self._path = self.logs_dir / f"{self.verb}_{stamp}.jsonl"
        self._t0 = time.time()
        self._write(
            event="start",
            verb=self.verb,
            args=self.args,
            pid=os.getpid(),
        )
        return self

    def milestone(self, note: str, /, **fields: Any) -> None:
        self._write(event="milestone", note=note, **fields)

    def end(
        self, *, status: str = "ok", error: str | None = None, **fields: Any,
    ) -> None:
        if self._ended:
            return
        self._ended = True
        duration_ms = int((time.time() - self._t0) * 1000)
        self._write(
            event="end",
            status=status,
            duration_ms=duration_ms,
            error=error,
            **fields,
        )

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._ended:
            if exc_type is None:
                self.end(status="ok")
            else:
                self.end(
                    status="error",
                    error=f"{exc_type.__name__}: {exc}",
                )

    def _write(self, **payload: Any) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            **_scrub(payload),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
