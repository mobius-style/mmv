"""library_reader.py — read-only access to the Pattern Library on disk.

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.3.

The reader does NOT mutate any file on disk. It only walks
config/pattern_library/*.jsonl and returns Pattern objects + simple
aggregates (counts, group-by-topic). Mutating writers live in
proposal_writer.py and src/governance/deletion_manager.py.

Caching: the on-disk content is read once per LibraryReader instance.
Use LibraryReader.reload() to force a re-read.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from src.retrieval.pattern_schema import Pattern


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "pattern_library"


class LibraryReader:
    def __init__(self, config_dir: Path = DEFAULT_CONFIG_DIR) -> None:
        self.config_dir = Path(config_dir)
        self._patterns: list[Pattern] = []
        self._raw_by_id: dict[str, dict] = {}
        self._loaded = False

    # ─────────────────────────────────────────────────────────────────

    def reload(self) -> None:
        self._patterns = []
        self._raw_by_id = {}
        if not self.config_dir.exists():
            self._loaded = True
            return
        for jsonl in sorted(self.config_dir.glob("*.jsonl")):
            if jsonl.name.startswith("_"):
                continue
            for ln, line in enumerate(jsonl.open("r", encoding="utf-8"), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    p = Pattern.model_validate(raw)
                except Exception:
                    continue
                self._patterns.append(p)
                self._raw_by_id[p.id] = raw
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    # ─────────────────────────────────────────────────────────────────
    # Reads
    # ─────────────────────────────────────────────────────────────────

    def list_patterns(
        self,
        topic: Optional[str] = None,
        audit_status: Optional[str] = None,
        origin_type: Optional[str] = None,
    ) -> list[Pattern]:
        self._ensure_loaded()
        out = list(self._patterns)
        if topic:
            out = [p for p in out if p.topic == topic]
        if audit_status:
            out = [p for p in out if p.lifecycle.audit_status == audit_status]
        if origin_type:
            out = [p for p in out if p.origin.type == origin_type]
        return out

    def get(self, pattern_id: str) -> Optional[Pattern]:
        self._ensure_loaded()
        for p in self._patterns:
            if p.id == pattern_id:
                return p
        return None

    def get_raw(self, pattern_id: str) -> Optional[dict]:
        """Raw dict (for the detail page when we want the original
        JSON exactly as on disk)."""
        self._ensure_loaded()
        return self._raw_by_id.get(pattern_id)

    def by_topic(self) -> dict[str, list[Pattern]]:
        self._ensure_loaded()
        out: dict[str, list[Pattern]] = {}
        for p in self._patterns:
            out.setdefault(p.topic, []).append(p)
        for topic in out:
            out[topic].sort(key=lambda p: p.id)
        return dict(sorted(out.items()))

    # ─────────────────────────────────────────────────────────────────
    # Aggregates
    # ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        self._ensure_loaded()
        active = sum(
            1 for p in self._patterns
            if p.lifecycle.audit_status == "active" and not p.deprecated
        )
        deprecated = sum(1 for p in self._patterns if p.deprecated)
        proposals = sum(
            len(p.lifecycle.deletion_proposals) for p in self._patterns
        )
        return {
            "total": len(self._patterns),
            "active": active,
            "deprecated": deprecated,
            "deletion_proposals": proposals,
        }

    # ─────────────────────────────────────────────────────────────────
    # Search (text only here; semantic search lives in routes/search.py)
    # ─────────────────────────────────────────────────────────────────

    def text_search(self, q: str) -> list[Pattern]:
        self._ensure_loaded()
        if not q:
            return []
        ql = q.lower()
        hits: list[Pattern] = []
        for p in self._patterns:
            if (ql in p.id.lower()
                    or ql in p.intent.lower()
                    or ql in p.topic.lower()
                    or any(ql in e.lower() for e in p.examples)
                    or any(ql in e.lower() for e in p.negative_examples)
                    or any(ql in t.lower() for t in p.tags)):
                hits.append(p)
        return hits
