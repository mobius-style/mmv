"""Phase 5I Cell B — Wikipedia alias resolution (β layer).

Loads a pre-built alias dictionary (Phase 5I Cell A) and provides
runtime lookup. Normalization at lookup time MUST match the build-
time normalization in scripts/build_alias_dictionary.py.

Pipeline position: runs AFTER α surface-form normalization. Hit
returns the canonical Wikipedia article path (underscored title,
e.g. "Graphics_processing_unit"); miss returns None.

This module is EN-only by design — the source is the English ZIM.
Multi-language alias resolution is explicitly out of scope per the
Phase 5I T-directive.
"""
from __future__ import annotations

import json
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DICT = ROOT / "data" / "alias_dictionary.pkl"
DEFAULT_CONFIG = ROOT / "config" / "alias_resolver.json"


def _normalize(s: str) -> str:
    """Build/runtime normalization. MUST match build_alias_dictionary.py."""
    return s.strip().lower()


class AliasResolver:
    """Lazy-loading alias resolver.

    Construction does NOT load the dictionary; the first resolve()
    call triggers a load. This keeps import cheap when the resolver
    is constructed but not used.
    """

    def __init__(
        self,
        dict_path: Path = DEFAULT_DICT,
        *,
        enabled: bool = True,
    ):
        self.dict_path = Path(dict_path)
        self.enabled = enabled
        self._aliases: Optional[dict[str, str]] = None
        self._load_elapsed_ms: Optional[float] = None
        self._stats = {"hits": 0, "misses": 0, "calls": 0}

    @classmethod
    def from_config(cls, config_path: Path = DEFAULT_CONFIG) -> "AliasResolver":
        """Load configuration JSON. ENV `MMV_ALIAS_RESOLVER_DISABLED=1`
        forces disable regardless of the JSON `enabled` flag."""
        cfg: dict = {}
        if Path(config_path).exists():
            cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        dict_path = Path(cfg.get("dict_path", DEFAULT_DICT))
        if not dict_path.is_absolute():
            dict_path = ROOT / dict_path
        enabled = bool(cfg.get("enabled", True))
        if os.environ.get("MMV_ALIAS_RESOLVER_DISABLED") == "1":
            enabled = False
        return cls(dict_path=dict_path, enabled=enabled)

    def _ensure_loaded(self) -> None:
        if self._aliases is not None or not self.enabled:
            return
        if not self.dict_path.exists():
            log.warning("alias dictionary not found at %s; resolver disabled",
                        self.dict_path)
            self.enabled = False
            return
        t0 = time.perf_counter()
        with self.dict_path.open("rb") as f:
            self._aliases = pickle.load(f)
        self._load_elapsed_ms = (time.perf_counter() - t0) * 1000.0
        log.info("loaded alias dictionary: %d entries in %.1f ms",
                 len(self._aliases), self._load_elapsed_ms)

    def resolve(self, query: str) -> Optional[str]:
        """Look up a query string. Returns canonical path on hit, None otherwise.

        The query is normalized (lower-case + strip) before lookup. If
        the resolver is disabled or the dict is unavailable, returns None.
        """
        self._stats["calls"] += 1
        if not self.enabled:
            return None
        self._ensure_loaded()
        if self._aliases is None:
            return None
        if not query:
            self._stats["misses"] += 1
            return None
        key = _normalize(query)
        target = self._aliases.get(key)
        if target is not None:
            self._stats["hits"] += 1
            return target
        # α/β plural→singular fallback (simple EN rules, T directive
        # scope). Tried in order; first hit wins. Length guard prevents
        # over-stripping ("is" → "i" empty-stem absurdities).
        for stripped, replacement in (
            ("ies", "y"),  # "memories" → "memory"
            ("es", ""),    # "potatoes" → "potato"
            ("s", ""),     # "GPUs" → "GPU", "vaccines" → "vaccine"
        ):
            if key.endswith(stripped) and len(key) > len(stripped) + 1:
                singular_key = key[: -len(stripped)] + replacement
                target = self._aliases.get(singular_key)
                if target is not None:
                    self._stats["hits"] += 1
                    return target
        self._stats["misses"] += 1
        return None

    def resolve_in_query(self, query: str) -> Optional[tuple[str, str]]:
        """Resolve an alias appearing inside a sentence-form query.

        Phase 5I-smoke iter1 extension. Strategy:
          1. Try whole-query lookup via resolve() (existing behavior)
          2. If miss: extract all-caps tokens of length ≥ 2 (typical
             abbreviation/acronym signal in English) and try each
          3. Return (matched_token, canonical_target) on hit, else None

        The all-caps heuristic catches sentence-embedded aliases like
        "GPU" in "What does GPU stand for?" without requiring full
        NER. It is intentionally narrow: it fires only on tokens that
        are themselves all-caps (≥ 2 chars), so common words and
        sentence-initial capitalization do not produce false matches.
        """
        # Whole-query attempt first (existing semantics)
        target = self.resolve(query)
        if target is not None:
            return (query, target)
        # All-caps token fallback
        if not query or not self.enabled or self._aliases is None:
            return None
        for tok in query.split():
            stripped = tok.strip(",.?!:;'\"()[]")
            if (
                len(stripped) >= 2
                and stripped.isupper()
                and any(c.isalpha() for c in stripped)
            ):
                target = self._aliases.get(stripped.lower())
                if target is not None:
                    self._stats["hits"] += 1  # extra hit (whole-query miss path counted as miss)
                    return (stripped, target)
        return None

    @property
    def stats(self) -> dict:
        s = dict(self._stats)
        s["hit_rate"] = (
            s["hits"] / s["calls"] if s["calls"] else 0.0
        )
        s["load_elapsed_ms"] = self._load_elapsed_ms
        s["dict_size"] = (
            len(self._aliases) if self._aliases is not None else None
        )
        s["enabled"] = self.enabled
        return s


# Module-level singleton (lazy)
_singleton: Optional[AliasResolver] = None


def get_resolver() -> AliasResolver:
    """Return the process-singleton resolver (lazy-init)."""
    global _singleton
    if _singleton is None:
        _singleton = AliasResolver.from_config()
    return _singleton


def reset_singleton() -> None:
    """Test-only: drop the singleton so it gets re-initialized."""
    global _singleton
    _singleton = None
