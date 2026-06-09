"""
src/adapters/argos_bridge.py — Phase C ArgosBridge

Multi-language translation bridge using ArgosTranslate.
Exclusive resource control via ResourceLockManager. CPU only.

Principle C: Argos materializes only for non-English queries.
Principle B: Never run concurrently with the LLM.

Author: Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations
import logging
from typing import Optional

from src.kernel.resource_lock import ResourceLockManager, get_lock_manager

logger = logging.getLogger(__name__)


class ArgosAdapter:
    """
    ArgosTranslate wrapper.
    Acquires ResourceLockManager's translation_lock before translating.
    """

    def __init__(self, lock_manager: Optional[ResourceLockManager] = None) -> None:
        self._lock = lock_manager or get_lock_manager()
        self._available: set[tuple[str, str]] = set()
        self._loaded = False

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return True
        try:
            import argostranslate.package
            import argostranslate.translate
            installed = argostranslate.package.get_installed_packages()
            for pkg in installed:
                self._available.add((pkg.from_code, pkg.to_code))
            self._loaded = True
            logger.info(f"ArgosTranslate loaded. Available pairs: {len(self._available)}")
            return True
        except ImportError:
            logger.warning("argostranslate not installed. Translation unavailable.")
            return False

    def is_available(self, src_lang: str, tgt_lang: str) -> bool:
        """Check whether the specified language pair is installed."""
        if not self._ensure_loaded():
            return False
        return (src_lang, tgt_lang) in self._available

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> str:
        """
        Translate text. Uses ResourceLockManager for exclusive control with LLM.
        On failure, returns the original text as-is (no error raised).
        """
        if src_lang == tgt_lang:
            return text

        if not self.is_available(src_lang, tgt_lang):
            logger.debug(f"Language pair {src_lang}→{tgt_lang} not available. Returning original.")
            return text

        self._lock.acquire_translation()
        try:
            import argostranslate.translate
            result = argostranslate.translate.translate(text, src_lang, tgt_lang)
            return result if result else text
        except Exception as e:
            logger.warning(f"ArgosTranslate error ({src_lang}→{tgt_lang}): {e}")
            return text
        finally:
            self._lock.release_translation()

    def translate_for_query(self, text: str, src_lang: str,
                            tgt_lang: str = "en") -> tuple[str, bool]:
        """
        Query-side translation.
        Returns: (translated_text, translation_invoked)
        """
        if src_lang == "en" or not self.is_available(src_lang, tgt_lang):
            return text, False
        return self.translate(text, src_lang, tgt_lang), True

    def translate_for_localization(self, text: str, src_lang: str = "en",
                                   tgt_lang: str = "en") -> tuple[str, bool]:
        """
        Response-side translation.
        Returns: (localized_text, translation_invoked)
        """
        if tgt_lang == "en" or not self.is_available(src_lang, tgt_lang):
            return text, False
        return self.translate(text, src_lang, tgt_lang), True

    def list_available_pairs(self) -> list[tuple[str, str]]:
        """Return a list of installed language pairs."""
        self._ensure_loaded()
        return sorted(self._available)
