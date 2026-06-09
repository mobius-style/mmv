from src.kernel.language_policy import detect_language


def test_japanese_script_detection():
    assert detect_language("これは日本語です") == "ja"


def test_first_turn_fallback_defaults_to_english():
    assert detect_language("...", previous_language=None) == "en"


def test_inconclusive_short_text_keeps_previous_language():
    assert detect_language("ok", previous_language="ja") == "ja"
