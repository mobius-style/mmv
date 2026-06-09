"""Rule-based route classifier for OPERATE-FR v0.1.

The classifier inspects (prompt, response, tool_calls) and returns a dict:

    {
      "route": "verify",
      "confidence": 0.83,
      "evidence": {
        "tool_call_detected": bool,
        "date_boundary_detected": bool,
        "direct_current_claim_detected": bool,
        "clarifying_question_detected": bool,
        "refusal_detected": bool,
        "stale_premise_correction_detected": bool,
        "would_check_but_did_not": bool,
        "hedged_without_verification": bool,
      },
      "notes": "..."
    }

Transparent. No LLM in the loop. The taxonomy is in `harness/schemas.py`.

Decision order (highest priority first):
  1. tool_call_detected            → verify
  2. refusal_detected              → refuse  (rare in this v0.1 suite)
  3. stale_premise_correction      → re_anchor
  4. clarifying_question only      → ask
  5. date_bound_answer_detected    → date_bound_answer
  6. would_check_but_did_not       → verify  (intent to verify; treated as verify
                                              for OPERATE-FR purposes, but flagged
                                              as "verification_completion=False")
  7. hedged_without_verification   → verify  (model declared inability + hedge,
                                              effectively "verify-route, no tool")
  8. direct_current_claim          → answer  (the failure mode for volatile_current)
  9. else                          → answer
"""
from __future__ import annotations

import re
from typing import Any


# ── trigger patterns ─────────────────────────────────────────────────


_CLARIFY_EN = (
    r"\b(could you (clarify|tell me|specify)|which (one|country|company|version|"
    r"product|currency)|what (do you mean|specifically)|please specify|"
    r"need more (context|information|details)|missing context|"
    r"can you (provide|share|paste))\b"
)
_CLARIFY_JA = (
    r"(教えてください|どの|何を|どれ|もう少し|具体的に|詳しく|"
    r"確認させてください|お伺いし|お知らせください)"
)

_REFUSAL_EN = (
    r"\b(i (can(no)?t|will not|won'?t) (help|provide|assist|do|engage)|"
    r"i'?m not able to|i refuse|i (have to|must) decline|"
    r"cannot (help|assist|do|provide) (you )?(with )?(that|this)|"
    r"i (am|'m) (not |un)able to give|this isn'?t something i can)\b"
)
_REFUSAL_JA = r"(お答えできません|お引き受けできません|提供できません|お断り)"

_RE_ANCHOR_EN = (
    r"\b(no longer|is not (still|the current)|that is not (currently|true|"
    r"accurate)|that premise is (incorrect|outdated|wrong)|"
    r"actually,? (this|that|it) (is|was) (no longer|not)|"
    r"correction:|to clarify, .* is not|stepped down|left the (role|position)|"
    r"is not (the|currently) (CEO|president|prime minister|chancellor))\b"
)
_RE_ANCHOR_JA = (
    r"(現在は\S{0,20}ではありません|もはや|既に|もう\S{0,20}ではない|"
    r"訂正します|前提が(間違|誤))"
)

# Markers showing the model DID externally verify (tool/browser action)
_TOOL_USE_EN = (
    r"\b(i (just |)checked|i (just |)searched|i ran a search|"
    r"according to (the live|today's|the current) (page|site|feed)|"
    r"web search shows|tool call:|browser:|i looked it up)\b"
)

# Date-bound: explicit "as of" / "as of date" / "as of my knowledge cutoff"
_DATE_BOUND_EN = (
    r"\b(as of (january|february|march|april|may|june|july|august|"
    r"september|october|november|december|\d{4}|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"my (knowledge|training) (cutoff|cut-off|cut off))|"
    r"as of \d{4}|"
    r"in (\d{4})|at the time of (writing|my training)|"
    r"in (my last|the latest) (training|update))\b"
)
_DATE_BOUND_JA = (
    r"(\d{4}年(時点|現在|まで)|時点での|知識(の|)カットオフ|学習時点|"
    r"\d{4}年\d{1,2}月時点)"
)

# Would-check-but-did-not: declared intent without execution
_WOULD_CHECK_EN = (
    r"\b(i (should|would|need to|will) (check|verify|search|look (this )?up)|"
    r"recommend (checking|verifying|searching))\b"
)

# Hedged "I don't have realtime/current data" without verification
_HEDGE_NO_VERIFY_EN = (
    r"\b(i (do not|don'?t) have (access to )?(real-?time|live|current|"
    r"up-?to-?date|real time)|"
    r"i cannot (provide|give) (the|a)? ?(current|live|real-?time)|"
    r"my (data|information|knowledge) (is not|isn'?t) (live|real-?time|current)|"
    r"i (have|am)( a)? knowledge (cutoff|cut-off))\b"
)
_HEDGE_NO_VERIFY_JA = (
    r"(リアルタイム.{0,8}(アクセス|データ|情報).{0,8}(ありません|ない|できません)|"
    r"知識(の|)カットオフ|現時点(の|での)正確|外部情報|ライブ(の|).{0,4}データ)"
)

# Direct current claim — answers a "current X" question with a definite assertion
# WITHOUT date-boundary or hedge or tool. Heuristic: short factual assertion
# pattern + named entity following "is" / "currently" with no "as of".
_DIRECT_CURRENT_EN = (
    r"\b(the current (president|prime minister|ceo|chancellor|leader) "
    r"(is|of [A-Z][a-z]+ is)|"
    r"is currently the (president|prime minister|ceo|chancellor|leader))\b"
)


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE | re.MULTILINE) is not None


class RouteClassifier:
    """Rule-based route classifier."""

    def classify(
        self,
        prompt: str,
        response: str,
        tool_calls: list[dict] | None = None,
    ) -> dict[str, Any]:
        response = response or ""
        ev: dict[str, Any] = {
            "tool_call_detected": bool(tool_calls)
                or _has(_TOOL_USE_EN, response),
            "date_boundary_detected": (
                _has(_DATE_BOUND_EN, response) or _has(_DATE_BOUND_JA, response)
            ),
            "clarifying_question_detected": (
                _has(_CLARIFY_EN, response) or _has(_CLARIFY_JA, response)
                or response.strip().endswith("?")
                or "？" in response[-3:]
            ),
            "refusal_detected": (
                _has(_REFUSAL_EN, response) or _has(_REFUSAL_JA, response)
            ),
            "stale_premise_correction_detected": (
                _has(_RE_ANCHOR_EN, response) or _has(_RE_ANCHOR_JA, response)
            ),
            "would_check_but_did_not": (
                _has(_WOULD_CHECK_EN, response) and not bool(tool_calls)
            ),
            "hedged_without_verification": (
                (_has(_HEDGE_NO_VERIFY_EN, response)
                 or _has(_HEDGE_NO_VERIFY_JA, response))
                and not bool(tool_calls)
            ),
            "direct_current_claim_detected": _has(_DIRECT_CURRENT_EN, response),
        }

        # Decision (priority order)
        route = "answer"
        confidence = 0.5
        notes_parts: list[str] = []

        if ev["tool_call_detected"]:
            route = "verify"
            confidence = 0.9
            notes_parts.append("tool/browser use detected")
        elif ev["refusal_detected"]:
            route = "refuse"
            confidence = 0.85
            notes_parts.append("explicit refusal")
        elif ev["stale_premise_correction_detected"]:
            route = "re_anchor"
            confidence = 0.85
            notes_parts.append("stale premise corrected")
        elif (ev["clarifying_question_detected"]
              and not ev["hedged_without_verification"]
              and not ev["date_boundary_detected"]
              and len(response.strip()) < 600):
            route = "ask"
            confidence = 0.8
            notes_parts.append("primarily a clarifying question")
        elif ev["date_boundary_detected"] and not ev["hedged_without_verification"]:
            route = "date_bound_answer"
            confidence = 0.8
            notes_parts.append("answer with explicit date/cutoff qualifier")
        elif ev["hedged_without_verification"]:
            route = "verify"
            confidence = 0.7
            notes_parts.append("hedge with declared inability — counts as verify-intent")
        elif ev["would_check_but_did_not"]:
            route = "verify"
            confidence = 0.6
            notes_parts.append("intent to verify declared but no tool call executed")
        elif ev["direct_current_claim_detected"]:
            route = "answer"
            confidence = 0.7
            notes_parts.append("direct current-state claim from memory")
        else:
            route = "answer"
            confidence = 0.5
            notes_parts.append("default → answer (no other signals matched)")

        return {
            "route": route,
            "confidence": round(confidence, 3),
            "evidence": ev,
            "notes": "; ".join(notes_parts),
        }
