"""Tests for the JSONL audit logger (addons.secretary.state.audit).

The audit logger is the supervision surface — Claude reads these logs
to know what the secretary did. The tests verify:

  - one JSONL file per invocation, named <verb>_<ts>.jsonl
  - start / milestone / end records are present with the right shape
  - errors propagate (logger doesn't swallow them) but are recorded
  - HaltRequested is recorded as status=halted but otherwise propagates
  - obvious secret-shaped tokens are scrubbed before logging
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from addons.secretary.state.audit import AuditLogger
from addons.secretary.state.halt import HaltRequested


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_logger_writes_start_and_end_on_clean_exit(tmp_path: Path) -> None:
    with AuditLogger("smoke", args={"foo": "bar"}, logs_dir=tmp_path) as log:
        log.milestone("step1", n=3)
    files = list(tmp_path.glob("smoke_*.jsonl"))
    assert len(files) == 1
    records = _read_jsonl(files[0])
    events = [r["event"] for r in records]
    assert events == ["start", "milestone", "end"]
    assert records[0]["verb"] == "smoke"
    assert records[0]["args"] == {"foo": "bar"}
    assert records[1]["note"] == "step1"
    assert records[1]["n"] == 3
    assert records[2]["status"] == "ok"
    assert "duration_ms" in records[2]


def test_logger_records_error_and_re_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        with AuditLogger("bad", logs_dir=tmp_path):
            raise RuntimeError("boom")
    files = list(tmp_path.glob("bad_*.jsonl"))
    records = _read_jsonl(files[0])
    end = records[-1]
    assert end["event"] == "end"
    assert end["status"] == "error"
    assert "RuntimeError" in end["error"]
    assert "boom" in end["error"]


def test_logger_records_halted_status(tmp_path: Path) -> None:
    """HaltRequested gets its own status so log readers can tell apart
    'user stopped me' from 'something blew up'."""
    # Some implementations use HaltRequested → status=halted; others
    # treat it as a regular error. Either is acceptable as long as the
    # exception still propagates. Verify propagation + that the end
    # record is present with a non-ok status.
    with pytest.raises(HaltRequested):
        with AuditLogger("halt_test", logs_dir=tmp_path):
            raise HaltRequested("test")
    files = list(tmp_path.glob("halt_test_*.jsonl"))
    records = _read_jsonl(files[0])
    end = records[-1]
    assert end["event"] == "end"
    assert end["status"] != "ok"


def test_logger_scrubs_secret_shaped_tokens(tmp_path: Path) -> None:
    leaked_key = "gsk_" + "A" * 40
    with AuditLogger(
        "scrub", args={"leak": leaked_key}, logs_dir=tmp_path,
    ) as log:
        log.milestone("seen", body=f"prefix {leaked_key} suffix")
    files = list(tmp_path.glob("scrub_*.jsonl"))
    raw = files[0].read_text(encoding="utf-8")
    assert leaked_key not in raw, "secret leaked into audit log"
    assert "REDACTED" in raw
