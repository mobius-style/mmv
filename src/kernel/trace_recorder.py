"""
trace_recorder.py — Routing trace recorder for the Pattern Library.

Authoritative reference: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 2.6.

Properties:
    - Storage: data/pattern_library/traces/YYYY-MM-DD/*.jsonl
    - Retention: 30 days rolling, swept lazily on each record() call
    - Atomic write: per-trace temp file → os.replace into final path
    - Schema: trace_id / timestamp / query / library_lookup /
              legacy_routing / hybrid_decision / consulted_boxes /
              excluded_boxes / final_route

The recorder is a thin file-based collector. Aggregation, search, and
exposure happen in src/ui/library_inspector/lib/trace_reader.py
(Commit 8) and the routing_engine advisory hook (Commit 6).
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional

DEFAULT_TRACES_DIR = Path("data/pattern_library/traces")
DEFAULT_RETENTION_DAYS = 30


def _gen_trace_id(now: datetime) -> str:
    """Spec 2.6.1 example: trc_20260430_103045_abc."""
    return (
        "trc_" + now.strftime("%Y%m%d_%H%M%S") + "_"
        + secrets.token_hex(2)
    )


class TraceRecorder:
    """File-based trace recorder.

    Construct one per process; the lock guards atomic write under
    concurrent calls. The instance is cheap — no external resources held."""

    def __init__(
        self,
        traces_dir: Path = DEFAULT_TRACES_DIR,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ) -> None:
        self.traces_dir = Path(traces_dir)
        self.retention_days = int(retention_days)
        self._lock = Lock()
        self.traces_dir.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────
    # Recording
    # ─────────────────────────────────────────────────────────────────

    def record(
        self,
        *,
        query: str,
        library_lookup: Optional[dict[str, Any]] = None,
        legacy_routing: Optional[dict[str, Any]] = None,
        hybrid_decision: Optional[dict[str, Any]] = None,
        consulted_boxes: Optional[list[str]] = None,
        excluded_boxes: Optional[list[str]] = None,
        final_route: Optional[str] = None,
        query_lang_detected: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> Path:
        """Append one trace record. Returns the file path written."""
        now = timestamp or datetime.now(timezone.utc)
        trace = {
            "trace_id": _gen_trace_id(now),
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query": query,
            "query_lang_detected": query_lang_detected,
            "library_lookup": library_lookup or {},
            "legacy_routing": legacy_routing or {},
            "hybrid_decision": hybrid_decision or {},
            "consulted_boxes": list(consulted_boxes or []),
            "excluded_boxes": list(excluded_boxes or []),
            "final_route": final_route,
        }
        if extra:
            trace.update(extra)

        date_dir = self.traces_dir / now.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        target = date_dir / f"{trace['trace_id']}.jsonl"

        with self._lock:
            tmp = target.with_suffix(target.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps(trace, ensure_ascii=False) + "\n")
            os.replace(tmp, target)
            self.sweep_old_dirs(reference=now)
        return target

    # ─────────────────────────────────────────────────────────────────
    # Retention sweep
    # ─────────────────────────────────────────────────────────────────

    def sweep_old_dirs(
        self, reference: Optional[datetime] = None,
    ) -> list[str]:
        """Delete date directories older than retention_days. Returns the
        list of removed directory names (for testing)."""
        ref = reference or datetime.now(timezone.utc)
        cutoff = (ref - timedelta(days=self.retention_days)).date()
        removed: list[str] = []
        if not self.traces_dir.exists():
            return removed
        for child in self.traces_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                d = datetime.strptime(child.name, "%Y-%m-%d").date()
            except ValueError:
                continue
            if d < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                removed.append(child.name)
        return removed
