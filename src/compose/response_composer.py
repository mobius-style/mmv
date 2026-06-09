from __future__ import annotations

from ..kernel.route_decision import RouteDecision


# Phase 4 Issue B resolution (per L0 v8.2 Evolution Log
# cyc_20260422_zh_en_deep_survey, 2026-04-22): localize non-answer
# boilerplate per user_language. Previously all routes returned English
# regardless of user_language; ask route does not invoke upstream LLM
# rendering so localization was missing. This addressed 465 cases of
# 3328 in the Phase 3 post ZH eval (ZH 249 + JP 141 + EN 75).
#
# Translation policy:
#   - Semantic equivalence with the EN original.
#   - JP uses です/ます調 polite register, consistent with MMV JP UX.
#   - ZH uses 礼貌体, concise. Simplified characters.
#   - Key names match route names in RouteDecision ("ask" / "verify" /
#     "abstain"); "abstain" slot also serves the default non-answer path.
_BOILERPLATE_BY_LANG: dict[str, dict[str, str]] = {
    "en": {
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
    },
    "ja": {
        "ask": (
            "少し確認させてください — "
            "もう少し詳しく教えていただけますか？"
        ),
        "verify": (
            "回答の前に裏付けを確認させてください。"
            "現在、情報源を調べています。"
        ),
        "abstain": (
            "この質問には直接お答えできません。"
            "別の形で質問を整理していただければ、お手伝いできるかもしれません。"
        ),
    },
    "zh": {
        "ask": (
            "为了更好地回答，我需要您补充一点信息 — "
            "能否告诉我具体想了解什么？"
        ),
        "verify": (
            "回答之前需要核实证据，"
            "正在查阅来源。"
        ),
        "abstain": (
            "我无法直接回答这个问题。"
            "如果可以换一种方式提问，或许能帮到您。"
        ),
    },
}


def _resolve_lang_key(user_language: str | None) -> str:
    """Normalize user_language to one of the supported keys; fallback to 'en'.

    Unknown / None / empty values fall back to English, preserving the
    pre-Phase-4 behaviour for any caller that does not supply a recognised
    language code.
    """
    if not user_language:
        return "en"
    key = user_language.strip().lower()
    # Narrow zh-cn / zh-tw / ja-jp variants to the base bucket.
    if key.startswith("zh"):
        return "zh"
    if key.startswith("ja"):
        return "ja"
    if key.startswith("en"):
        return "en"
    return "en"


def compose_non_answer_response(
    decision: RouteDecision,
    user_language: str = "en",
) -> str:
    """
    Compose a minimal non-answer response for ask / verify / abstain routes.

    Design principle (Constitutional Core):
      Re-anchor: return the interaction to firmer ground.
      When the system cannot commit, point toward the next
      resolvable step rather than simply stopping.

    Phase 4 Issue B resolution (2026-04-22, per Evolution Log
    cyc_20260422_zh_en_deep_survey): boilerplate is now localized by
    user_language for 'en' / 'ja' / 'zh'. Upstream LLM rendering applies
    only to the synthesize path (verify-success/partial); the ask /
    verify-pending / abstain boilerplate returned here is a short
    deterministic string, so localization happens in this function.
    Unknown user_language falls back to English.

    Note: LLM-generated re-anchoring for ask/abstain is deferred to v3.
    verify-failed re-anchoring is handled in verify_synthesizer.py.
    """
    lang_key = _resolve_lang_key(user_language)
    boilerplate = _BOILERPLATE_BY_LANG[lang_key]

    if decision.route == "ask":
        return boilerplate["ask"]
    if decision.route == "verify":
        return boilerplate["verify"]
    # abstain and all other non-answer routes
    return boilerplate["abstain"]
