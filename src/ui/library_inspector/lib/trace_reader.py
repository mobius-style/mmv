"""trace_reader.py — read-only access to routing traces.

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.4.4."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class TraceReader:
    def __init__(self, traces_dir: Path) -> None:
        self.traces_dir = Path(traces_dir)

    def latest(
        self,
        n: int = 50,
        matched_pattern_id: Optional[str] = None,
        topic: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> list[dict]:
        """Return up to n traces, newest first. Filter by matched
        pattern id / topic via library_lookup metadata, or by date range
        (YYYY-MM-DD inclusive)."""
        if not self.traces_dir.exists():
            return []
        # Walk date dirs newest → oldest
        date_dirs = sorted(
            (d for d in self.traces_dir.iterdir() if d.is_dir()),
            key=lambda d: d.name, reverse=True,
        )
        results: list[dict] = []
        for d in date_dirs:
            try:
                _ = datetime.strptime(d.name, "%Y-%m-%d")
            except ValueError:
                continue
            if from_date and d.name < from_date:
                break
            if to_date and d.name > to_date:
                continue
            for fp in sorted(d.glob("*.jsonl"), reverse=True):
                if len(results) >= n:
                    return results
                try:
                    raw = fp.read_text(encoding="utf-8").strip()
                    if not raw:
                        continue
                    obj = json.loads(raw)
                except Exception:
                    continue
                if matched_pattern_id:
                    mp = (obj.get("library_lookup") or {}).get(
                        "matched_pattern_id"
                    )
                    if mp != matched_pattern_id:
                        continue
                if topic:
                    obj_topic = (obj.get("library_lookup") or {}).get("topic")
                    if obj_topic != topic:
                        continue
                results.append(obj)
        return results
