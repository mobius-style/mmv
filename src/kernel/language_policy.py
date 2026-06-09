from __future__ import annotations

import re
from typing import Optional

try:
    from langdetect import detect
except Exception:  # pragma: no cover
    detect = None

# Phase E resolution 2026-04-23 (per Evolution Log
# cyc_20260423_en_focused_integrated_survey): split the prior combined
# `ja: [぀-ヿ一-龯]` pattern into two. The old pattern conflated Japanese
# and Chinese by matching ALL CJK ideographs as `ja`, which set
# state.active_language = "ja" for Chinese queries and drove the 91%
# systemic ZH→JP response pattern observed in pre-Phase-3 through post-
# Phase-4 evals. The correct ja/zh split already existed in
# src/kernel/language_anchor.py:_detect_script but was limited to
# vague-continuation anchor resolution only; this fix brings that logic
# into the dominant detect_language path.
#
# Iteration order matters: ja (kana) MUST be checked before zh (CJK
# ideographs only), so that Japanese prose with kana+kanji correctly
# classifies as `ja` via its kana content. CJK-only text with no kana
# classifies as `zh`. Pure Latin / other scripts continue to fall
# through to langdetect or previous_language as before.
SCRIPT_PATTERNS = {
    "ja": re.compile(r"[぀-ヿ]"),              # Hiragana U+3040-309F + Katakana U+30A0-30FF (kana)
    "zh": re.compile(r"[一-龯]"),              # CJK Unified Ideographs U+4E00-9FAF (no kana)
    "ko": re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯]"),
    "ar": re.compile(r"[؀-ۿ]"),
    "ru": re.compile(r"[Ѐ-ӿ]"),
}


def _script_heuristic(text: str) -> Optional[str]:
    for lang, pattern in SCRIPT_PATTERNS.items():
        if pattern.search(text):
            return lang
    if re.search(r"[A-Za-z]", text):
        return None  # Latin scripts require fallback.
    return None


def detect_language(text: str, previous_language: Optional[str] = None) -> str:
    detected = _script_heuristic(text)
    if detected:
        return detected

    latin_chars = re.findall(r"[A-Za-z]", text)
    if len(latin_chars) >= 6 and detect is not None:
        try:
            return detect(text)
        except Exception:
            pass

    if previous_language:
        return previous_language
    return "en"
