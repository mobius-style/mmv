#!/usr/bin/env python3
"""
audit_store.py — MOBIUS MMV Phase D: Audit Log Store
src/audit/audit_store.py

JSONL append (async). Switchable to SQLite.
Append-only. External SIEM integration deferred (Principle E).

Output files (spec §8):
  logs/audit_turns.jsonl     -- Turn Audit Record + QK Snapshot + Decision Trace
  logs/audit_sessions.jsonl  -- Session Trace Summary (one record at session end)
  logs/audit_incidents.jsonl -- Incident / Tombstone Record (anomalies only)

Latency requirement (spec §11):
  audit_store.py append latency < 5ms (no impact on main thread)

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : phase_d_audit_spec.docx §5, §8, §11
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from audit_schema import (
    FullTurnAuditRecord,
    IncidentRecord,
    SessionTraceSummary,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_LOG_DIR         = Path("logs")
TURNS_FILE              = "audit_turns.jsonl"
SESSIONS_FILE           = "audit_sessions.jsonl"
INCIDENTS_FILE          = "audit_incidents.jsonl"
ROTATION_DAYS           = 30      # Rotation retention days
MAX_LATENCY_WARNING_MS  = 5       # Warn log if this threshold is exceeded

AuditRecord = Union[FullTurnAuditRecord, SessionTraceSummary, IncidentRecord]


class AuditStore:
    """
    JSONL append store. Async emit does not block the main thread.

    Design:
      - Writes are processed by a queue worker on a separate thread (equivalent to asyncio.create_task)
      - File handles are kept open (append-only)
      - Daily rotation uses gzip compression

    Usage:
        store = AuditStore(log_dir="logs")
        store.open()

        # Async write (does not block main thread)
        store.enqueue(turn_record)

        # Sync write (for testing)
        store.write_sync(turn_record)

        store.close()
    """

    def __init__(self, log_dir: Union[str, Path] = DEFAULT_LOG_DIR):
        self.log_dir = Path(log_dir)
        self._handles: dict[str, object] = {}
        self._lock    = threading.Lock()
        self._queue: list[tuple[str, dict]] = []
        self._worker_thread: threading.Thread | None = None
        self._running = False

    # ── Public API ──────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the store. Create log directory and start worker thread."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="AuditStoreWorker",
        )
        self._worker_thread.start()
        logger.info(f"[AuditStore] Opened. log_dir={self.log_dir}")

    def close(self) -> None:
        """Close the store. Flush queue then close files."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=3.0)
        with self._lock:
            for fh in self._handles.values():
                try:
                    fh.flush()
                    fh.close()
                except Exception:
                    pass
            self._handles.clear()
        logger.info("[AuditStore] Closed.")

    def enqueue(self, record: AuditRecord) -> None:
        """
        Add to async write queue (does not block main thread).

        To meet latency requirement < 5ms, actual writes are performed by the worker thread.
        """
        filename = self._filename_for(record)
        data     = record.to_dict()
        with self._lock:
            self._queue.append((filename, data))

    def write_sync(self, record: AuditRecord) -> float:
        """
        Synchronous write (for testing and debugging).

        Returns:
            Milliseconds taken for the write
        """
        filename = self._filename_for(record)
        data     = record.to_dict()
        t0 = time.time()
        self._write_one(filename, data)
        elapsed_ms = (time.time() - t0) * 1000
        if elapsed_ms > MAX_LATENCY_WARNING_MS:
            logger.warning(
                f"[AuditStore] write_sync latency={elapsed_ms:.1f}ms > {MAX_LATENCY_WARNING_MS}ms"
            )
        return elapsed_ms

    def flush(self) -> None:
        """Immediately write all remaining records in the queue (for testing)"""
        with self._lock:
            pending = list(self._queue)
            self._queue.clear()
        for filename, data in pending:
            self._write_one(filename, data)

    # ── Internal methods ─────────────────────────────────────────────────────

    def _filename_for(self, record: AuditRecord) -> str:
        if isinstance(record, FullTurnAuditRecord):
            return TURNS_FILE
        elif isinstance(record, SessionTraceSummary):
            return SESSIONS_FILE
        elif isinstance(record, IncidentRecord):
            return INCIDENTS_FILE
        else:
            return TURNS_FILE

    def _get_handle(self, filename: str):
        """Return cached file handle (kept open)"""
        if filename not in self._handles:
            path = self.log_dir / filename
            self._handles[filename] = open(path, "a", encoding="utf-8", buffering=1)
        return self._handles[filename]

    def _write_one(self, filename: str, data: dict) -> None:
        """Append one JSONL line"""
        line = json.dumps(data, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            fh = self._get_handle(filename)
            fh.write(line)

    def _worker(self) -> None:
        """Background worker. Consumes queue and writes."""
        while self._running or self._queue:
            with self._lock:
                if self._queue:
                    batch = list(self._queue)
                    self._queue.clear()
                else:
                    batch = []
            for filename, data in batch:
                try:
                    self._write_one(filename, data)
                except Exception as e:
                    logger.error(f"[AuditStore] write failed: {e}")
            time.sleep(0.001)  # 1ms sleep

    # ── Rotation ────────────────────────────────────────────────────────

    def rotate_if_needed(self) -> list[Path]:
        """
        Daily rotation. Compress files from previous days with gzip.
        Delete compressed files older than 30 days.

        Returns:
            List of paths of compressed files
        """
        rotated = []
        today   = datetime.now(timezone.utc).date().isoformat()

        for filename in (TURNS_FILE, SESSIONS_FILE, INCIDENTS_FILE):
            path = self.log_dir / filename
            if not path.exists():
                continue
            # File's last modification date
            mtime = datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            ).date().isoformat()
            if mtime < today:
                gz_path = path.with_suffix(
                    f".{mtime}.jsonl.gz"
                )
                with open(path, "rb") as f_in, \
                     gzip.open(gz_path, "wb") as f_out:
                    f_out.write(f_in.read())
                path.unlink()
                rotated.append(gz_path)
                logger.info(f"[AuditStore] Rotated: {gz_path}")

        # Delete old compressed files
        self._cleanup_old_gz()
        return rotated

    def _cleanup_old_gz(self) -> None:
        """Delete .gz files older than ROTATION_DAYS days"""
        now = time.time()
        cutoff = now - ROTATION_DAYS * 86400
        for gz in self.log_dir.glob("*.gz"):
            if gz.stat().st_mtime < cutoff:
                gz.unlink()
                logger.info(f"[AuditStore] Deleted old gz: {gz}")

    def stats(self) -> dict:
        """Return store statistics (for health checks)"""
        result = {}
        for filename in (TURNS_FILE, SESSIONS_FILE, INCIDENTS_FILE):
            path = self.log_dir / filename
            if path.exists():
                lines = sum(1 for _ in open(path, encoding="utf-8"))
                result[filename] = {
                    "exists": True,
                    "lines":  lines,
                    "size_kb": path.stat().st_size // 1024,
                }
            else:
                result[filename] = {"exists": False}
        result["queue_depth"] = len(self._queue)
        return result
