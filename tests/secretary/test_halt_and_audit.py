"""Tests for the Phase 1 supervision primitives:

  - addons.secretary.state.halt — cooperative halt switch
  - addons.secretary.state.audit — JSONL invocation log
  - CLI integration — every verb writes a log; review-packet honors halt
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from addons.secretary.cli import main
from addons.secretary.state.audit import AuditLogger
from addons.secretary.state.halt import (
    HALT_FILE,
    HaltRequested,
    clear_halt,
    halt_check,
    is_halted,
    request_halt,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_DIR = (
    REPO_ROOT
    / "operate-fr-bench"
    / "reports"
    / "human_review_packet_mmv_large_rc3_3"
)


# ─── halt switch ────────────────────────────────────────────────────────


def test_halt_check_noop_when_file_absent(tmp_path: Path) -> None:
    halt_file = tmp_path / "halt"
    assert not is_halted(halt_file)
    halt_check(halt_file)  # must not raise


def test_halt_check_raises_when_file_present(tmp_path: Path) -> None:
    halt_file = tmp_path / "halt"
    request_halt(halt_file)
    assert is_halted(halt_file)
    with pytest.raises(HaltRequested):
        halt_check(halt_file)
    clear_halt(halt_file)
    assert not is_halted(halt_file)


def test_clear_halt_is_idempotent(tmp_path: Path) -> None:
    halt_file = tmp_path / "halt"
    clear_halt(halt_file)  # must not raise even when absent
    request_halt(halt_file)
    clear_halt(halt_file)
    clear_halt(halt_file)
    assert not halt_file.exists()


# ─── audit logger ───────────────────────────────────────────────────────


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_audit_logger_writes_start_milestone_end(tmp_path: Path) -> None:
    with AuditLogger("foo", args={"x": 1}, logs_dir=tmp_path) as log:
        log.milestone("step_a", n=3)
        log.milestone("step_b", detail="hello")
    records = _read_jsonl(log.path)
    assert records[0]["event"] == "start"
    assert records[0]["verb"] == "foo"
    assert records[0]["args"] == {"x": 1}
    assert records[1]["event"] == "milestone"
    assert records[1]["note"] == "step_a"
    assert records[1]["n"] == 3
    assert records[2]["event"] == "milestone"
    assert records[2]["note"] == "step_b"
    assert records[2]["detail"] == "hello"
    assert records[3]["event"] == "end"
    assert records[3]["status"] == "ok"
    assert "duration_ms" in records[3]


def test_audit_logger_records_exception_status(tmp_path: Path) -> None:
    try:
        with AuditLogger("boom", logs_dir=tmp_path) as log:
            raise RuntimeError("kaboom")
    except RuntimeError:
        pass
    records = _read_jsonl(log.path)
    end = records[-1]
    assert end["event"] == "end"
    assert end["status"] == "error"
    assert "RuntimeError" in end["error"]
    assert "kaboom" in end["error"]


def test_audit_logger_scrubs_obvious_secrets(tmp_path: Path) -> None:
    leaky_key = "gsk_" + "A" * 32
    with AuditLogger("scrub", args={"key": leaky_key}, logs_dir=tmp_path) as log:
        log.milestone("leak", embedded=f"got {leaky_key} oops")
    text = log.path.read_text(encoding="utf-8")
    assert leaky_key not in text
    assert "***REDACTED***" in text


# ─── CLI integration ───────────────────────────────────────────────────


pytestmark = pytest.mark.skipif(
    not PACKET_DIR.exists(),
    reason="RC3.3 human-review packet not present in this checkout",
)


def test_cli_version_writes_audit_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Redirect audit logs to a tmp dir so we don't pollute state/logs/.
    import addons.secretary.state.audit as audit_mod
    monkeypatch.setattr(audit_mod, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(
        "addons.secretary.cli.AuditLogger",
        lambda verb, args=None: AuditLogger(verb, args=args or {}, logs_dir=tmp_path),
    )

    rc = main(["version"])
    assert rc == 0
    logs = list(tmp_path.glob("version_*.jsonl"))
    assert len(logs) == 1
    records = _read_jsonl(logs[0])
    assert records[0]["event"] == "start"
    assert records[-1]["event"] == "end"
    assert records[-1]["status"] == "ok"


def test_cli_review_packet_aborts_on_halt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Touch the halt file before review-packet runs; expect exit 130
    and an audit log with status=error and error=HaltRequested."""
    import addons.secretary.state.audit as audit_mod
    monkeypatch.setattr(audit_mod, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(
        "addons.secretary.cli.AuditLogger",
        lambda verb, args=None: AuditLogger(verb, args=args or {}, logs_dir=tmp_path),
    )

    request_halt(HALT_FILE)
    try:
        rc = main([
            "review-packet",
            "--target", str(PACKET_DIR),
            "--out", str(tmp_path / "should_not_appear.md"),
        ])
    finally:
        clear_halt(HALT_FILE)

    assert rc == 130
    logs = list(tmp_path.glob("review-packet_*.jsonl"))
    assert len(logs) == 1
    end = _read_jsonl(logs[0])[-1]
    assert end["event"] == "end"
    assert end["status"] == "error"
    assert "HaltRequested" in (end.get("error") or "")
