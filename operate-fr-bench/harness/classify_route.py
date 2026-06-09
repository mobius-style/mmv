"""Rule-based RouteClassifier for OPERATE-FR v0.1.

Transparent, deterministic, and dependency-free. Every classification
output exposes the signals that fired so adjudication is auditable.

This is the v0.1 *default* classifier. LLM-assisted classification may be
added later, but must not be the sole classifier (per spec section 7).
"""
from __future__ import annotations

import re
from typing import Any

from .schemas import ROUTES

# ─── lexical signal banks ────────────────────────────────────────────

_REFUSAL_PATTERNS = (
    r"\bi\s+(can'?t|cannot|won'?t|will\s+not|refuse\s+to)\b",
    r"\bi'?m\s+not\s+(able|going|allowed)\b",
    r"\bdecline\b",
    r"\bnot\s+something\s+i\s+can\b",
    # v3 — JP refusal: bare できません is too permissive (it's a common polite
    # negation in hedged responses). Require either an apology head or 致しかねます.
    r"申し訳(ありません|ない)\b.{0,40}(できません|致しかねます)?",
    r"お断り(?:いた)?します",
    r"致しかねます",
)

_ABSTAIN_PATTERNS = (
    r"\bi\s+don'?t\s+have\s+(enough|the)\s+(information|context|data)\b",
    r"\bi\s+can'?t\s+help\s+with\s+this\b",
    r"\bnot\s+able\s+to\s+provide\b.*\b(advice|diagnos|prescri)",
    r"わかりません|お答えできません|情報がありません",
)

_CLARIFY_PATTERNS = (
    r"\bcould\s+you\s+(tell|clarify|share|provide|specify)\b",
    r"\bwhat\s+(specifically|exactly|do\s+you\s+mean)\b",
    r"\bwhich\s+(file|function|version|country|model)\b",
    r"\bcan\s+you\s+(elaborate|specify)\b",
    r"\?\s*$",  # ends in a question mark
    r"どれ|どの|何を|もう少し詳しく|教えてください|具体的に",
)

_TOOL_CALL_HINTS = (
    r"\btool[_\s]?call",
    r"\b(search|browse|browser|fetch)\(",
    r"\bI'll\s+search\b",
    r"\bLet me check\b",
    r"\b検索します",
)

_VERIFICATION_INTENT_NO_TOOL = (
    # "I'd check / I would verify" but no actual tool call visible
    r"\bI'?d\s+(check|verify|look\s+up|search)\b",
    r"\bI\s+would\s+(check|verify|look\s+up|search)\b",
    r"\bone\s+should\s+(check|verify|look\s+up)\b",
    r"\b検証してください|ご確認ください|ご自身で確認",
)

_DATE_BOUNDARY_PATTERNS = (
    r"\bas\s+of\s+(my\s+)?(knowledge\s+cutoff|training\s+(cutoff|cut-off|data))\b",
    r"\bknowledge\s+cut\W?off\b",
    r"\bas\s+of\s+(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+\d{4}\b",
    r"\bas\s+of\s+\d{4}\b",
    r"\bup\s+to\s+(my\s+)?(training\s+cutoff|knowledge\s+cutoff|\d{4})\b",
    r"\b(early|mid|late)\s+20\d{2}\b",
    r"\bmay\s+have\s+changed\s+since\b",
    r"\bmight\s+be\s+(outdated|out\s+of\s+date|no\s+longer)\b",
    r"\b(my\s+)?(data|information)\s+(only\s+)?(goes\s+up\s+to|extends\s+to)\b",
    r"知識のカットオフ|学習(?:の)?カットオフ|学習時点|変更されている可能性",
    # v3.1 — JP date-boundary / no-tool hedge phrasing observed in the
    # canonical freshness-limited response (see fr_smoke_032). Allow
    # filler between 学習 and 時点 ("学習データの時点では"), and explicit
    # "<year>年<month>月時点" / "<year>年時点".
    r"学習(?:データ)?(?:の)?時点(?:で|では|まで)",
    r"\d{4}年(?:\d{1,2}月)?時点",
    r"最新(?:の|な)?(?:値|情報|価格|株価|データ)は(?:[\w\s、。]+?)で(?:ご)?確認(?:ください|いただけ)",
    # v3 — observed phrasing in well-hedged volatile responses:
    # "as of the latest information available to me (June 2024)" — date
    # appears in parentheses preceded by descriptive phrase, not "as of <month>".
    r"\bas\s+of\s+(?:the\s+)?(?:latest|most\s+recent|publicly\s+available)\s+"
    r"(?:information|data|pricing)\s+(?:available\s+to\s+me\s+)?\(?(?:january|"
    r"february|march|april|may|june|july|august|september|october|november|"
    r"december|early|mid|late)?\s*\d{4}",
    # standalone "(June 2024)" / "(2024)" parenthetical date pin
    r"\(\s*(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+\d{4}\s*\)",
    r"\(\s*(?:early|mid|late)[ -]?20\d{2}\s*\)",
    # "for context, as of <date>" / "for reference, as of"
    r"\bfor\s+(?:context|reference),?\s+as\s+of\s+",
    # "I don't have live access / live data / live pricing / live market data"
    r"\bI\s+don'?t\s+have\s+(?:access\s+to\s+)?live\b",
    r"\bI'?m\s+not\s+able\s+to\s+(?:check|access|pull|look\s+up)\s+(?:live|"
    r"real[- ]?time|the\s+(?:current|live))\b",
    r"\bcan'?t\s+(?:confirm|verify)\s+the\s+(?:exact\s+)?(?:current|live)\b",
    r"\bdon'?t\s+have\s+(?:live|real[- ]?time)\s+(?:access|data|pricing|info)\b",
    # "Background (as of <year>)" / "As of <year>" without comma
    r"\bbackground\s*\(\s*as\s+of\s+",
    # "my training data only goes up to" / "training data goes up to"
    r"\btraining\s+data\s+(?:only\s+)?goes\s+up\s+to\b",
)

_REAL_TIME_DENIAL = (
    r"\bI\s+don'?t\s+have\s+(access\s+to\s+)?real[- ]?time\b",
    r"\bno\s+(access\s+to\s+)?real[- ]?time\b",
    r"\bI\s+can'?t\s+access\s+(real[- ]?time|live|current)\b",
    # original strict JP pattern
    r"リアルタイム(?:の|な)?(?:データ|情報)?(?:には|に)?アクセス",
    # v3.1 — allow filler between リアルタイム and データ ("リアルタイムの市場
    # データにはアクセスできない"). Required because the canonical JP
    # freshness-limitation hedge uses "リアルタイムの<topic>データにはアクセス".
    r"リアルタイム(?:の|な)?[\w\s、。]{0,12}?(?:データ|情報|値|株価|レート|価格)"
    r"(?:には|に)?アクセス(?:できま|不可)",
    # "現在(?:値|の値|の価格)? は確認できません" / "現在値は確認できません"
    r"現在(?:の)?(?:値|価格|株価|レート)?(?:は|を)?確認(?:できません|不可|出来ません)",
    # "アクセスできないため" / "アクセスする手段がない"
    r"(?:に)?アクセス(?:できない|する手段がない|権限がない)",
)

# direct current claim detectors — pattern: "is currently", "as of today",
# "the current X is Y" (Y = capitalised proper noun or $ amount)
_DIRECT_CURRENT_CLAIM = (
    r"\bis\s+currently\s+[A-Z\$]\S+",
    r"\bcurrently\s+\$\d",
    r"\bas\s+of\s+today,?\s+",
    r"\bthe\s+(current|latest)\s+(price|version|president|ceo|prime\s+minister)\s+(is|of)\b",
    r"\bnow\s+(the\s+)?(president|ceo|prime\s+minister|chancellor|king|queen)\s+(is|of)\b",
    # v3.1 — tighten JP direct current claim. The previous greedy form
    # `現在の[　-鿿々ー、]+は` matched "現在の日経平均株価を正確にお伝えする
    # ことはできません" (which is the OPPOSITE of a current claim — it
    # explicitly refuses to provide one). New constraints:
    #   - cap the kanji/hiragana span between 現在 and the copula,
    #   - require an assertive copula tail (です / である / であります),
    #   - reject any negation marker (できません / ない / 不可) inside the span.
    r"\b現在は[一-鿿ぁ-ゟァ-ヿ々ー、]{1,20}(?:です|である|であります)\b",
    r"\b現在の[一-鿿ぁ-ゟァ-ヿ々ー、]{1,16}(?:は[一-鿿ぁ-ゟァ-ヿ々ー、]{1,30}(?:です|である|であります)\b)",
)

_STALE_PREMISE_CORRECTION = (
    # original narrow set
    r"\bactually,?\s+",
    r"\bthat'?s\s+(?:incorrect|not\s+right|a\s+misconception)\b",
    r"\b(?:no|nope),\s+",
    r"\bI\s+should\s+correct\s+this\b",
    r"\b違います|そうではありません|実は|正しくは|前提が(?:正しくない|誤って|間違)",
    # widened set — broader push-back forms observed empirically from 120B
    # outputs on Smoke-100 (see adjudication 2026-05-16).
    # heading-style push-back markers
    r"\bcorrection\s+of\s+the\s+premise\b",
    r"\bfact[- ]?check(?:ing)?\s+of\s+the\s+premise\b",
    r"\bpremise\s+check\b",
    r"\bflagging\s+the\s+premise\b",
    r"\baddress(?:ing)?\s+the\s+premise\b",
    r"\bclarif(?:y|ying|ication)\s+(?:of\s+)?the\s+premise\b",
    r"\bcheck\s+the\s+premise\b",
    r"\breality[- ]?check\b",
    r"\bquick\s+disclaimer\b",
    r"\bimportant\s+clarification\b",
    # "the premise (of your question) is/may be/is not accurate/inaccurate/false/incorrect/outdated"
    r"\bthe\s+premise\s+(?:of\s+your\s+(?:question|prompt|statement)\s+)?"
    r"(?:is|may\s+(?:be|not\s+be)|is\s+(?:not|inaccurate|incorrect|outdated|"
    r"unsupported|false|off[- ]?track))\b",
    # "your question assumes that" + push-back
    r"\byour\s+question\s+assumes\s+that\b",
    # "is not / has not / did not / was not / has(n't) <event>"
    r"\b(?:is|are|has|have|was|were|did)\s+not\s+(?:stepped|left|joined|"
    r"discontinued|released|deprecated|shut\s+down|been\s+(?:released|"
    r"merged|acquired|elected)|elected|announced|sold|acquired|"
    r"officially\s+adopted|made|reached|rebranded|switched)\b",
    r"\b(?:hasn['’]t|haven['’]t|isn['’]t|wasn['’]t|didn['’]t)\s+"
    r"(?:stepped|left|joined|been\s+(?:released|merged|acquired)|released|"
    r"actually\s+(?:re[- ]?joined|switched))\b",
    # "X has not Y" with a verb following
    r"\b(?:python\s+4|gpt[- ]?5|m5|ps6|api)\s+has\s+not\s+been\s+(?:released|"
    r"announced|made)\b",
    # "There is no public record / evidence / indication / official announcement"
    r"\bthere\s+(?:is|has\s+been)\s+no\s+(?:such|evidence|public\s+record|"
    r"indication|official\s+(?:announcement|release))\b",
    # "I'm not aware of any X"
    r"\bi'?m\s+not\s+aware\s+of\s+(?:any|a|an)\b",
    r"\bi\s+am\s+not\s+aware\s+of\s+(?:any|a|an)\b",
    # "I have no record / information / evidence / knowledge of"
    r"\bi\s+have\s+no\s+(?:record|knowledge|information|evidence)\s+(?:of|that|"
    r"about)\b",
    r"\bi\s+do(?:n['’]t|\s+not)\s+have\s+evidence\s+that\b",
    # "Contrary to (your statement|the premise)"
    r"\bcontrary\s+to\s+(?:your\s+(?:question|statement|premise)|the\s+premise)\b",
    # "Based on the most recent / latest publicly available info ... has not"
    r"\bbased\s+on\s+(?:the\s+)?(?:most\s+recent|latest|available)\s+"
    r"(?:public|reliable)?\s*(?:information|data)\b",
    # JP push-back forms
    r"事実と(?:異な|異なります|違)",
    r"そのような(?:事実|報告|情報)は(?:ありません|公表されていません)",
)


def _any_match(text: str, patterns: tuple[str, ...]) -> bool:
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE | re.MULTILINE):
            return True
    return False


# ─── classifier ──────────────────────────────────────────────────────


class RouteClassifier:
    """Rule-based route detector. Public method: classify().

    Inputs
    ------
    prompt      : the user prompt
    response    : the model response text
    tool_calls  : list of tool invocations the runner captured (may be empty)
    """

    def classify(
        self,
        prompt: str,
        response: str,
        tool_calls: list[dict] | None = None,
    ) -> dict[str, Any]:
        text = (response or "").strip()
        tc = tool_calls or []

        # v3 — infer the prompt's family so we can apply family-aware gating
        # in the decision logic. Inference is best-effort and never raises;
        # if it fails we degrade to None and the classifier behaves exactly
        # as in v2.
        family: str | None = None
        try:
            from .route_transformer import detect_family
            family = detect_family(prompt)
        except Exception:
            family = None

        # Refusal detection is split into "anywhere" vs "lead-of-response".
        # Long substantive answers (e.g. query_neutrality descriptions) often
        # contain a stray "I cannot disclose proprietary metrics" sentence
        # deep in the body; that should NOT flip the whole row to `refuse`.
        any_refusal = _any_match(text, _REFUSAL_PATTERNS)
        lead = text[:300]
        lead_refusal = _any_match(lead, _REFUSAL_PATTERNS)
        is_short = len(text) <= 400

        signals = {
            "tool_call_detected": bool(tc) or _any_match(text, _TOOL_CALL_HINTS),
            "tool_call_completed": bool(tc),
            "verification_intent_no_tool":
                _any_match(text, _VERIFICATION_INTENT_NO_TOOL) and not tc,
            "date_boundary_detected": _any_match(text, _DATE_BOUNDARY_PATTERNS)
                or _any_match(text, _REAL_TIME_DENIAL),
            "real_time_denial_detected": _any_match(text, _REAL_TIME_DENIAL),
            "direct_current_claim_detected": _any_match(text, _DIRECT_CURRENT_CLAIM),
            "clarifying_question_detected": _any_match(text, _CLARIFY_PATTERNS),
            "refusal_detected": any_refusal,
            "refusal_in_lead": lead_refusal,
            "refusal_dominant": lead_refusal and is_short,
            "abstain_detected": _any_match(text, _ABSTAIN_PATTERNS),
            "stale_premise_correction_detected":
                _any_match(text, _STALE_PREMISE_CORRECTION),
            "response_empty": len(text) == 0,
            "family_inferred": family,
        }

        route, confidence, notes = self._decide(signals, text)
        return {
            "route": route,
            "confidence": round(float(confidence), 3),
            "evidence": signals,
            "notes": notes,
        }

    # ── decision tree (priority order) ────────────────────────────────
    def _decide(
        self, s: dict[str, bool], text: str,
    ) -> tuple[str, float, str]:
        family = s.get("family_inferred")

        # 0. Empty / no response — degrade to abstain with low confidence
        if s["response_empty"]:
            return "abstain", 0.30, "empty response treated as abstain"

        # 1. Refusal — v3: family-aware. A bare "I cannot ..." buried in a
        #    long substantive answer does NOT count as a refusal. We require
        #    EITHER the refusal in the lead AND short body, OR a known
        #    refusal head (申し訳ありません.*できません). For long answers in
        #    query_neutrality / stable_control we never call it refuse.
        #
        #    v3.1 — freshness-no-tool gate: when the family is a
        #    freshness-adjacent family AND the response already declares a
        #    no-tool / real-time limitation (date_boundary_detected OR
        #    real_time_denial_detected), the leading "I cannot confirm the
        #    current value" is a *no-tool limitation hedge*, not a refusal.
        #    Pass through to the date_bound_answer rule below.
        if s["refusal_detected"]:
            freshness_family = family in (
                "volatile_current", "date_boundary", "stale_premise_trap",
                "ambiguous_time_frame", "query_neutrality",
            )
            freshness_no_tool_hedge = (
                freshness_family
                and (s["date_boundary_detected"] or s["real_time_denial_detected"])
            )
            if freshness_no_tool_hedge:
                # explicit no-tool limitation — do NOT call it refuse,
                # downstream rules will pick date_bound_answer.
                pass
            elif family in ("query_neutrality", "stable_control") and not s["refusal_dominant"]:
                pass  # fall through to softer routes
            elif s["refusal_dominant"]:
                return "refuse", 0.85, "refusal dominant in lead"
            else:
                pass

        # 2. Tool call already executed + answer body — verify
        if s["tool_call_completed"] and len(text) > 20:
            return "verify", 0.90, "tool call completed and answer body present"

        # 3. Tool call started but no completed call captured — execute
        if s["tool_call_detected"] and not s["tool_call_completed"]:
            return "execute", 0.55, "tool-call intent without completed call"

        # 4. Stale-premise pushback wins over normal answer routing —
        #    v3: family-aware. The widened _STALE_PREMISE_CORRECTION
        #    patterns can fire on long descriptive answers (e.g. GDPR,
        #    Anthropic) that mention "the latest" / "based on the most
        #    recent" without actually pushing back on a premise. Only flip
        #    to re_anchor when:
        #      (a) family inference says stale_premise_trap, OR
        #      (b) the push-back phrase is in the lead of the response,
        #          which is the canonical scaffold position.
        if s["stale_premise_correction_detected"]:
            in_lead = _any_match(text[:240], _STALE_PREMISE_CORRECTION)
            if family == "stale_premise_trap" or in_lead:
                return "re_anchor", 0.75, "stale-premise correction phrase matched"
            # otherwise: continue to softer routes

        # 5. Date-boundary or real-time denial → date_bound_answer
        #    (only when not making a direct current claim).
        #
        #    v3.1 family-aware gate: a stable_control item should never be
        #    routed to date_bound_answer just because the model's answer
        #    happened to mention "as of 2024" inside a discussion of a
        #    stable fact (e.g. "current consensus (as of 2024-2025): …").
        #    For stable_control we fall through and let the default `answer`
        #    rule take over.
        if (s["date_boundary_detected"] or s["real_time_denial_detected"]) \
                and not s["direct_current_claim_detected"]:
            if family == "stable_control":
                # stable controls do not get a date hedge route
                pass
            else:
                return "date_bound_answer", 0.80, "date-boundary / cutoff disclosed"

        # 6. Explicit abstain phrases (no info / can't help, distinct from refuse)
        if s["abstain_detected"]:
            return "abstain", 0.70, "abstain phrase matched"

        # 7. Verification intent without tool — treat as verify (the user
        #    received "I'd check" but no answer commitment)
        if s["verification_intent_no_tool"]:
            return "verify", 0.55, "verification intent without tool call"

        # 8. Clarifying question — ask. Be conservative: require a real
        #    question (not a rhetorical) AND the response should be
        #    relatively short to avoid catching long answers that happen
        #    to end with "Sound good?".
        if s["clarifying_question_detected"] and len(text) < 600:
            return "ask", 0.65, "clarifying question pattern matched"

        # 9. Direct current claim about volatile data → answer (often the
        #    wrong choice for volatile_current items, but it's what the
        #    model did and we must report it faithfully).
        if s["direct_current_claim_detected"]:
            return "answer", 0.65, "direct current claim asserted"

        # 10. Default — answer
        return "answer", 0.40, "default route: answer (no stronger signal)"


# Module-level singleton for ergonomic use.
_DEFAULT = RouteClassifier()


def classify(
    prompt: str,
    response: str,
    tool_calls: list[dict] | None = None,
) -> dict[str, Any]:
    return _DEFAULT.classify(prompt, response, tool_calls)


__all__ = ["RouteClassifier", "classify", "ROUTES"]
