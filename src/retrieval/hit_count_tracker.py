"""HitCountTracker — thread-safe in-memory hit-count aggregation.

Phase 3 Commit 33. Tracks pattern hits at routing decision time
without slowing down each route call (single dict lookup + atomic
increment under a re-entrant lock). Periodic flush persists the
counts back to the pattern JSONL files via lifecycle.hit_count.

Design:
- Module-level singleton accessor ``get_tracker()``
- Per-pattern counter dict guarded by threading.RLock
- ``record(pattern_id)`` is the routing-side hot path; O(1)
- ``flush(config_dir)`` writes hit_count + last_hit_date back to
  config JSONL files; intended to be called periodically (e.g.,
  every 5 minutes or before audit)
- Spec ref: docs/PATTERN_LIBRARY_SPEC_v1_4.md §5.4.3 (Phase 3
  hit-count instrumentation)
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class HitCountTracker:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._last_hit: dict[str, datetime] = {}
        self._lock = threading.RLock()

    def record(self, pattern_id: str) -> None:
        if not pattern_id:
            return
        now = datetime.now(timezone.utc)
        with self._lock:
            self._counts[pattern_id] = self._counts.get(pattern_id, 0) + 1
            self._last_hit[pattern_id] = now

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()
            self._last_hit.clear()

    def total(self) -> int:
        with self._lock:
            return sum(self._counts.values())

    def flush(self, config_dir: Path) -> dict:
        """Persist accumulated hit counts back to the pattern JSONL
        files under ``config_dir``. Each pattern's
        ``lifecycle.hit_count`` is incremented by the recorded delta
        and ``lifecycle.last_hit_date`` is updated to the latest hit
        timestamp. Counts are reset after a successful flush.

        Returns a summary dict:
            {"patterns_updated": N, "total_hits": K,
             "files_written": M, "errors": [...]}
        """
        with self._lock:
            deltas = dict(self._counts)
            last_hits = dict(self._last_hit)
            self._counts.clear()
            self._last_hit.clear()

        if not deltas:
            return {"patterns_updated": 0, "total_hits": 0,
                    "files_written": 0, "errors": []}

        files_written = 0
        patterns_updated = 0
        errors: list[str] = []
        for jsonl in sorted(config_dir.glob("*.jsonl")):
            if jsonl.name.startswith("_"):
                continue
            try:
                lines = [
                    json.loads(line) for line in
                    jsonl.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            except Exception as e:  # malformed file — skip but record
                errors.append(f"{jsonl.name}: read error: {e}")
                continue
            changed = False
            for obj in lines:
                pid = obj.get("id")
                if pid not in deltas:
                    continue
                lifecycle = obj.setdefault("lifecycle", {})
                if not isinstance(lifecycle, dict):
                    lifecycle = {}
                    obj["lifecycle"] = lifecycle
                lifecycle["hit_count"] = (
                    int(lifecycle.get("hit_count", 0)) + deltas[pid]
                )
                last = last_hits.get(pid)
                if last is not None:
                    lifecycle["last_hit_date"] = last.isoformat().replace(
                        "+00:00", "Z"
                    )
                patterns_updated += 1
                changed = True
            if changed:
                with jsonl.open("w", encoding="utf-8") as fh:
                    for obj in lines:
                        fh.write(
                            json.dumps(obj, ensure_ascii=False) + "\n"
                        )
                files_written += 1
        return {
            "patterns_updated": patterns_updated,
            "total_hits": sum(deltas.values()),
            "files_written": files_written,
            "errors": errors,
        }


_tracker: Optional[HitCountTracker] = None
_tracker_lock = threading.Lock()


def get_tracker() -> HitCountTracker:
    """Return the process-shared HitCountTracker singleton."""
    global _tracker
    if _tracker is not None:
        return _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = HitCountTracker()
    return _tracker


def reset_tracker() -> None:
    """Test helper. Resets the module-level singleton."""
    global _tracker
    with _tracker_lock:
        _tracker = None
