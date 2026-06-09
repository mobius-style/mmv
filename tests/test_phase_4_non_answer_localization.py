"""Phase 4 focused tests: compose_non_answer_response localization (Issue B).

Per L0 v8.2 Evolution Log cyc_20260422_zh_en_deep_survey (2026-04-22):
the pre-Phase-4 behaviour returned English boilerplate for ask / verify /
abstain regardless of user_language. Upstream LLM rendering applies only
to the synthesize path; the short deterministic boilerplate here was
previously stuck at English. Phase 4 adds ZH / JP localizations while
preserving byte-identical EN output for the English fallback path.

Groups:
  1. Language dispatch (3 langs × 3 routes = 9 tests)
  2. Fallback (unknown / None / empty / casing)
  3. Regression guard (EN byte-identical to pre-Phase-4)
  4. Structure (dict completeness)
  5. Semantic (no cross-language script contamination)
"""
from __future__ import annotations

import re

import pytest

from src.compose.response_composer import (
    _BOILERPLATE_BY_LANG,
    _resolve_lang_key,
    compose_non_answer_response,
)
from src.kernel.route_decision import RouteDecision


def _make_decision(route: str) -> RouteDecision:
    return RouteDecision(
        route=route,
        reason_codes=[],
        confidence_posture="bounded",
        answer_shape=None,
    )


# ── Group 1: Language dispatch (9 tests) ─────────────────────────────────────

ROUTES = ("ask", "verify", "abstain")
LANGS = ("en", "ja", "zh")


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("route", ROUTES)
def test_language_dispatch_returns_correct_boilerplate(lang: str, route: str):
    resp = compose_non_answer_response(_make_decision(route), lang)
    expected = _BOILERPLATE_BY_LANG[lang][route]
    assert resp == expected, (
        f"Phase 4: lang={lang} route={route} expected byte-identical "
        f"boilerplate from dict, got differing string."
    )


# ── Group 2: Fallback (unknown / None / empty / casing) ─────────────────────

def test_fallback_unknown_language_returns_english():
    resp = compose_non_answer_response(_make_decision("ask"), "ko")
    assert resp == _BOILERPLATE_BY_LANG["en"]["ask"]


def test_fallback_none_language_returns_english():
    resp = compose_non_answer_response(_make_decision("ask"), None)  # type: ignore[arg-type]
    assert resp == _BOILERPLATE_BY_LANG["en"]["ask"]


def test_fallback_empty_language_returns_english():
    resp = compose_non_answer_response(_make_decision("ask"), "")
    assert resp == _BOILERPLATE_BY_LANG["en"]["ask"]


def test_casing_uppercase_language_is_normalized():
    # _resolve_lang_key lowercases the input; 'ZH' must map to 'zh'.
    resp = compose_non_answer_response(_make_decision("verify"), "ZH")
    assert resp == _BOILERPLATE_BY_LANG["zh"]["verify"]


def test_regional_variant_zh_cn_maps_to_zh():
    assert _resolve_lang_key("zh-cn") == "zh"
    assert _resolve_lang_key("zh-TW") == "zh"
    resp = compose_non_answer_response(_make_decision("ask"), "zh-cn")
    assert resp == _BOILERPLATE_BY_LANG["zh"]["ask"]


def test_regional_variant_ja_jp_maps_to_ja():
    assert _resolve_lang_key("ja-JP") == "ja"
    resp = compose_non_answer_response(_make_decision("abstain"), "ja-JP")
    assert resp == _BOILERPLATE_BY_LANG["ja"]["abstain"]


def test_casing_uppercase_en_returns_english():
    assert _resolve_lang_key("EN") == "en"


# ── Group 3: Regression guard (EN byte-identical to pre-Phase-4) ────────────

# These strings are the pre-Phase-4 hardcoded English boilerplate. Any
# divergence would break callers that may (in the future) assert on these
# exact strings.
_PRE_PHASE_4_EN = {
    "ask": (
        "I need one clarification to proceed — "
        "could you tell me a bit more about what you are looking for?"
    ),
    "verify": (
        "This needs evidence verification before I can answer. "
        "Checking sources now."
    ),
    "abstain": (
        "I cannot answer this directly. "
        "If you can reframe the question, I may be able to help."
    ),
}


@pytest.mark.parametrize("route", ROUTES)
def test_en_byte_identical_to_pre_phase_4(route: str):
    resp = compose_non_answer_response(_make_decision(route), "en")
    assert resp == _PRE_PHASE_4_EN[route], (
        f"Phase 4 regression: EN fallback for route={route} must be "
        f"byte-identical to pre-Phase-4 English boilerplate."
    )


def test_default_user_language_argument_is_en():
    # When caller omits user_language, the default kwarg is "en".
    resp_default = compose_non_answer_response(_make_decision("ask"))
    resp_en = compose_non_answer_response(_make_decision("ask"), "en")
    assert resp_default == resp_en


def test_unknown_route_falls_through_to_abstain():
    # Any route other than "ask"/"verify" (including "abstain", "explore",
    # arbitrary unknowns) returns the abstain boilerplate. This preserves
    # pre-Phase-4 behaviour.
    for route in ("abstain", "unknown", ""):
        resp = compose_non_answer_response(_make_decision(route), "en")
        assert resp == _PRE_PHASE_4_EN["abstain"]


# ── Group 4: Structure (dict completeness) ──────────────────────────────────

def test_boilerplate_dict_has_all_three_languages():
    assert set(_BOILERPLATE_BY_LANG.keys()) == {"en", "ja", "zh"}


def test_each_language_has_all_three_route_keys():
    expected_keys = {"ask", "verify", "abstain"}
    for lang, table in _BOILERPLATE_BY_LANG.items():
        assert set(table.keys()) == expected_keys, (
            f"language {lang!r} has keys {set(table.keys())}, "
            f"expected {expected_keys}"
        )


def test_no_empty_boilerplate_strings():
    for lang, table in _BOILERPLATE_BY_LANG.items():
        for key, value in table.items():
            assert value and value.strip(), (
                f"_BOILERPLATE_BY_LANG[{lang!r}][{key!r}] is empty/whitespace"
            )


# ── Group 5: Semantic (no cross-language script contamination) ──────────────

_HIRAGANA = re.compile(r"[぀-ゟ]")
_KATAKANA = re.compile(r"[゠-ヿ]")
_CJK = re.compile(r"[一-鿿]")
# Simplified-exclusive characters that should NOT appear in the JP strings
# if they are meant to stay within Japanese conventions. This list is
# small and conservative — we only check a handful that happen to appear
# in common Chinese localisations but are not used in natural Japanese
# prose.
_SIMPLIFIED_ONLY_MARKERS = ("为", "问", "帮", "换", "补", "体")


def test_zh_strings_contain_no_kana():
    for key, value in _BOILERPLATE_BY_LANG["zh"].items():
        assert not _HIRAGANA.search(value), (
            f"_BOILERPLATE_BY_LANG['zh'][{key!r}] contains hiragana; "
            f"ZH boilerplate must be CJK-only (no kana)."
        )
        assert not _KATAKANA.search(value), (
            f"_BOILERPLATE_BY_LANG['zh'][{key!r}] contains katakana; "
            f"ZH boilerplate must be CJK-only (no kana)."
        )


def test_ja_strings_contain_kana():
    # A natural Japanese boilerplate should include at least one kana
    # character — protects against accidentally copying ZH text into the
    # JA slot during maintenance.
    for key, value in _BOILERPLATE_BY_LANG["ja"].items():
        has_kana = bool(_HIRAGANA.search(value) or _KATAKANA.search(value))
        assert has_kana, (
            f"_BOILERPLATE_BY_LANG['ja'][{key!r}] has no kana; "
            f"JA boilerplate should contain hiragana or katakana."
        )


def test_en_strings_contain_no_cjk():
    for key, value in _BOILERPLATE_BY_LANG["en"].items():
        assert not _CJK.search(value), (
            f"_BOILERPLATE_BY_LANG['en'][{key!r}] contains CJK characters; "
            f"EN boilerplate must be ASCII/Latin only."
        )
        assert not _HIRAGANA.search(value)
        assert not _KATAKANA.search(value)


def test_ja_strings_do_not_use_simplified_only_markers():
    # Defensive: we do not want the JA slot to accidentally contain
    # characters that are simplified-only (would indicate a ZH leak).
    for key, value in _BOILERPLATE_BY_LANG["ja"].items():
        for marker in _SIMPLIFIED_ONLY_MARKERS:
            assert marker not in value, (
                f"_BOILERPLATE_BY_LANG['ja'][{key!r}] contains "
                f"simplified-only char {marker!r}; suggests ZH leak."
            )
