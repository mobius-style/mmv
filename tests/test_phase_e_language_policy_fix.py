"""Phase E fix focused tests: language_policy.py SCRIPT_PATTERNS ja/zh split.

Per L0 v8.2 Evolution Log cyc_20260423_en_focused_integrated_survey (Phase E
finding): the pre-fix SCRIPT_PATTERNS["ja"] pattern `[぀-ヿ一-龯]` matched
all CJK ideographs as `ja`, conflating Chinese and Japanese and causing a
systemic 91% ZH→JP response bias observed across pre-Phase-3 through
post-Phase-4 evals. This fix splits into:

  ja  → `[぀-ヿ]`   (Hiragana U+3040-309F + Katakana U+30A0-30FF — kana only)
  zh  → `[一-龯]`   (CJK Unified Ideographs U+4E00-9FAF — no kana)

Iteration order `ja` → `zh` means Japanese prose with kana+kanji still
classifies as `ja` (kana hits first), while CJK-only text classifies as
`zh`. EN path is unchanged (EN has no CJK).
"""
from __future__ import annotations

import pytest

from src.kernel.language_policy import (
    SCRIPT_PATTERNS,
    _script_heuristic,
    detect_language,
)


# ── Group 1: Pure kana → ja ────────────────────────────────────────────────

def test_pure_hiragana_detected_as_ja():
    assert detect_language("ひらがなだけの文") == "ja"


def test_pure_katakana_detected_as_ja():
    assert detect_language("カタカナダケノブン") == "ja"


def test_mixed_kana_detected_as_ja():
    assert detect_language("ひらがなとカタカナ") == "ja"


# ── Group 2: Japanese prose (kana + CJK) → ja (kana hits first) ─────────────

def test_japanese_prose_with_kanji_detected_as_ja():
    # Canonical Japanese mixed script must remain `ja`. This is the critical
    # regression guard after the ja/zh split: Japanese must NOT drift to zh.
    assert detect_language("日本語の文章は漢字と仮名を混ぜます") == "ja"


def test_japanese_question_detected_as_ja():
    assert detect_language("今日の天気はどうですか？") == "ja"


def test_japanese_technical_text_detected_as_ja():
    assert detect_language("キャッシュはCPUに近い位置に配置された小容量の記憶領域です") == "ja"


# ── Group 3: CJK-only (Chinese) → zh ────────────────────────────────────────

def test_simplified_chinese_detected_as_zh():
    # This is the headline fix: pre-Phase-E, this returned "ja".
    assert detect_language("中文的简体字只有汉字没有假名") == "zh"


def test_traditional_chinese_detected_as_zh():
    assert detect_language("繁體中文也只有漢字沒有假名") == "zh"


def test_chinese_question_detected_as_zh():
    assert detect_language("你好，今天天气怎么样？") == "zh"


def test_chinese_technical_text_detected_as_zh():
    assert detect_language("缓存是位于CPU和主内存之间的小容量高速存储器") == "zh"


def test_chinese_with_ascii_punctuation_detected_as_zh():
    # ASCII punctuation is OK; the CJK content still determines the bucket.
    assert detect_language("抛硬币的概率是多少?") == "zh"


# ── Group 4: EN unchanged (regression guard, T priority) ────────────────────

def test_english_detected_as_en():
    # Plain English with enough latin content falls through to langdetect
    # or the `en` default. Must not be disturbed by the ja/zh split.
    assert detect_language("The quick brown fox jumps over the lazy dog") == "en"


def test_english_short_defaults_to_en():
    # Short latin text with no prior → `en` default path.
    assert detect_language("hi") == "en"


def test_en_prev_language_fallback_unchanged():
    # Previous language fallback path unchanged.
    assert detect_language("???", previous_language="en") == "en"


# ── Group 5: Mixed Latin + CJK ──────────────────────────────────────────────

def test_mixed_en_ja_detected_as_ja_via_kana():
    # English tech terms embedded in Japanese: kana hits → ja.
    assert detect_language("TCP/IPプロトコルを使ってデータを送信します") == "ja"


def test_mixed_en_zh_detected_as_zh_via_cjk():
    # English tech terms embedded in Chinese: no kana, CJK hits → zh.
    assert detect_language("使用TCP/IP协议发送数据") == "zh"


# ── Group 6: Hangul / non-CJK scripts unchanged ─────────────────────────────

def test_hangul_detected_as_ko():
    # Korean script must not be confused with ja/zh by the split.
    assert detect_language("안녕하세요") == "ko"


def test_hangul_not_ja_or_zh():
    # Defensive: Korean text contains neither kana nor CJK ideograph
    # ranges as defined here, so ja/zh patterns must not match it.
    assert not SCRIPT_PATTERNS["ja"].search("안녕하세요")
    assert not SCRIPT_PATTERNS["zh"].search("안녕하세요")


def test_arabic_detected_as_ar():
    assert detect_language("مرحبا بالعالم") == "ar"


def test_russian_detected_as_ru():
    assert detect_language("Привет мир") == "ru"


# ── Group 7: SCRIPT_PATTERNS structure regression guard ────────────────────

def test_script_patterns_has_zh_key_after_fix():
    # Before Phase E: "zh" key did not exist.
    # After Phase E: "zh" key must exist for the CJK-only split.
    assert "zh" in SCRIPT_PATTERNS


def test_script_patterns_ja_key_no_longer_matches_cjk_only():
    # The ja pattern must NOT match pure CJK text (the conflation bug).
    ja_pattern = SCRIPT_PATTERNS["ja"]
    assert not ja_pattern.search("中文汉字没有假名")
    assert not ja_pattern.search("繁體漢字")


def test_script_patterns_zh_key_matches_cjk_only():
    zh_pattern = SCRIPT_PATTERNS["zh"]
    assert zh_pattern.search("中文")
    assert zh_pattern.search("繁體")


def test_script_patterns_ja_matches_kana():
    ja_pattern = SCRIPT_PATTERNS["ja"]
    assert ja_pattern.search("ひらがな")
    assert ja_pattern.search("カタカナ")


def test_script_patterns_iteration_order_ja_before_zh():
    # Insertion order matters for _script_heuristic: ja must appear before zh
    # so that kana+kanji Japanese classifies as ja, not zh.
    keys = list(SCRIPT_PATTERNS.keys())
    assert keys.index("ja") < keys.index("zh")


# ── Group 8: Underlying heuristic direct tests ──────────────────────────────

def test_script_heuristic_returns_ja_for_kana_plus_cjk():
    assert _script_heuristic("日本語と仮名") == "ja"


def test_script_heuristic_returns_zh_for_cjk_only():
    assert _script_heuristic("中文汉字") == "zh"


def test_script_heuristic_returns_none_for_latin_only():
    # Latin-only must not trigger script heuristic; langdetect takes over.
    assert _script_heuristic("English only text") is None
