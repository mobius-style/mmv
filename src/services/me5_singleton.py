"""me5_singleton.py — process-shared multilingual-e5-large lifecycle.

Phase 3 Commit 27. Spec v1.4 Section 5.4.1 + 7.8.1 (operational
constraints).

Problem statement:
    Phase 2's Library Inspector + RoutingEngine + autogen pipeline
    each lazy-loaded ME5 (multilingual-e5-large, 1024-dim, ~2GB on
    CPU memory). When the 33-scenario harness instantiates many
    RoutingEngine instances, ME5 is reloaded N times → ~5s × N of
    overhead, pushing env-on harness time to ~35-40 min.

Solution:
    Process-level singleton owning the SentenceTransformer model.
    First caller pays the load cost; subsequent callers reuse the
    same instance.

Thread safety:
    Double-checked locking pattern around lazy initialization.
    Concurrent first-callers race to acquire the lock; the loser
    sees the loaded instance via the post-lock recheck.

Performance target (Phase 3):
    env-on 33-scenario harness < 15 min (vs Phase 2's ~35-40 min).

Memory budget:
    ME5 model ~2GB CPU memory; the singleton holds one reference
    only. Existing Phase 2 callers that already loaded ME5 directly
    can either migrate to the singleton (preferred) or coexist
    (one extra in-memory copy until they migrate).

Public API:
    get_me5_singleton(model_name=None) -> ME5Singleton
    ME5Singleton.encode_query(text)        -> 1D vector (np.float32)
    ME5Singleton.encode_passage(text)      -> 1D vector (np.float32)
    ME5Singleton.encode_batch(texts, ...)  -> 2D array (N, 1024)
    reset_me5_singleton()                    [test helper]
"""
from __future__ import annotations

import threading
from typing import Iterable, Optional

DEFAULT_MODEL = "intfloat/multilingual-e5-large"
ME5_DIM = 1024

# Module-level singleton state. Access guarded by _lock.
_singleton: "Optional[ME5Singleton]" = None
_lock = threading.Lock()


class ME5Singleton:
    """Process-shared ME5 holder.

    Direct construction is allowed for tests but production callers
    should use `get_me5_singleton()`.

    The model load is deferred until first encode() call (lazy)."""

    def __init__(self, model_name: str = DEFAULT_MODEL,
                 _model=None) -> None:
        self.model_name = model_name
        self._model = _model      # injectable for tests; otherwise lazy
        self._load_lock = threading.Lock()
        self._encode_count = 0    # diagnostic
        self._loaded_at = None    # set on first load

    def _ensure_loaded(self):
        if self._model is not None:
            return self._model
        with self._load_lock:
            # Re-check after acquiring lock (double-checked locking)
            if self._model is not None:
                return self._model
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            import time
            self._loaded_at = time.time()
        return self._model

    # ─────────────────────────────────────────────────────────────────
    # Encoding API
    # ─────────────────────────────────────────────────────────────────

    def encode_query(self, text: str):
        """Encode a single query with the 'query: ' E5 prefix.
        Returns a 1D normalized float32 vector of length ME5_DIM."""
        import numpy as np
        m = self._ensure_loaded()
        v = m.encode(
            ["query: " + text],
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        self._encode_count += 1
        return np.asarray(v, dtype="float32")

    def encode_passage(self, text: str):
        """Encode a single passage with the 'passage: ' E5 prefix."""
        import numpy as np
        m = self._ensure_loaded()
        v = m.encode(
            ["passage: " + text],
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        self._encode_count += 1
        return np.asarray(v, dtype="float32")

    def encode_batch(
        self, texts: Iterable[str], *, prefix: str = "passage: ",
        batch_size: int = 32,
    ):
        """Batch-encode an iterable of strings with the given prefix."""
        import numpy as np
        m = self._ensure_loaded()
        prefixed = [prefix + t for t in texts]
        arr = m.encode(
            prefixed,
            batch_size=batch_size,
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        )
        self._encode_count += len(prefixed)
        return np.asarray(arr, dtype="float32")

    # ─────────────────────────────────────────────────────────────────
    # Diagnostic / introspection
    # ─────────────────────────────────────────────────────────────────

    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def encode_count(self) -> int:
        return self._encode_count

    @property
    def loaded_at(self):
        return self._loaded_at


# ─────────────────────────────────────────────────────────────────────
# Module-level accessors
# ─────────────────────────────────────────────────────────────────────

def get_me5_singleton(model_name: str = DEFAULT_MODEL) -> ME5Singleton:
    """Return the process-wide ME5 singleton, lazily creating it on
    first call. Subsequent calls return the same instance. The model
    is NOT loaded into memory until the first encode() is called.

    Thread-safe via double-checked locking."""
    global _singleton
    if _singleton is not None and _singleton.model_name == model_name:
        return _singleton
    with _lock:
        if _singleton is None or _singleton.model_name != model_name:
            _singleton = ME5Singleton(model_name=model_name)
    return _singleton


def reset_me5_singleton() -> None:
    """Test-only helper: reset the singleton to allow fresh
    construction. NOT thread-safe across reset + concurrent get."""
    global _singleton
    with _lock:
        _singleton = None
