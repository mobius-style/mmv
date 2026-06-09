"""
src/kernel/resource_lock.py — Phase C ResourceLockManager

Mutual exclusion between LLM (phi4-mini) and Argos translator.
Prevents VRAM contention, OOM, and guarantees sequential execution.

Author: Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations
import threading


class ResourceLockManager:
    """
    Mutual exclusion between translation_lock and llm_lock.

    Constraints:
      - Cannot acquire llm_lock while translation_lock is held
      - Cannot acquire translation_lock while llm_lock is held
      - Embedding device follows MMV_EMBEDDING_DEVICE; callers that co-host
        an LLM on the same GPU should use MMV_EMBEDDING_DEVICE=cpu or add an
        explicit embedding lock.

    Usage:
        lock = ResourceLockManager()

        # Before/after Argos call
        lock.acquire_translation()
        try:
            argos.translate(...)
        finally:
            lock.release_translation()

        # Before/after LLM inference
        lock.acquire_llm()
        try:
            adapter.generate(...)
        finally:
            lock.release_llm()
    """

    def __init__(self) -> None:
        self._translation_lock = threading.Lock()
        self._llm_lock         = threading.Lock()

    # ── Translation ──────────────────────────────────────────────────────────

    def acquire_translation(self) -> None:
        if self._llm_lock.locked():
            raise RuntimeError(
                "Cannot start Argos translation while LLM is running. "
                "ResourceLockManager prevents VRAM/RAM conflict."
            )
        self._translation_lock.acquire()

    def release_translation(self) -> None:
        if self._translation_lock.locked():
            self._translation_lock.release()

    def is_translating(self) -> bool:
        return self._translation_lock.locked()

    # ── LLM ──────────────────────────────────────────────────────────────────

    def acquire_llm(self) -> None:
        if self._translation_lock.locked():
            raise RuntimeError(
                "Cannot start LLM while Argos translation is running. "
                "ResourceLockManager prevents VRAM/RAM conflict."
            )
        self._llm_lock.acquire()

    def release_llm(self) -> None:
        if self._llm_lock.locked():
            self._llm_lock.release()

    def is_llm_running(self) -> bool:
        return self._llm_lock.locked()

    # ── Context managers ─────────────────────────────────────────────────────

    def translation_context(self):
        """Context manager for use with 'with' statement."""
        return _LockContext(self.acquire_translation, self.release_translation)

    def llm_context(self):
        """Context manager for use with 'with' statement."""
        return _LockContext(self.acquire_llm, self.release_llm)


class _LockContext:
    def __init__(self, acquire, release):
        self._acquire = acquire
        self._release = release

    def __enter__(self):
        self._acquire()
        return self

    def __exit__(self, *_):
        self._release()


# Global singleton (shared from MMV kernel)
_global_lock_manager: ResourceLockManager | None = None


def get_lock_manager() -> ResourceLockManager:
    global _global_lock_manager
    if _global_lock_manager is None:
        _global_lock_manager = ResourceLockManager()
    return _global_lock_manager
