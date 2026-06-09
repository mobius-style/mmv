"""Small Routing Stabilizer — MMV-S-RC3.3 (Routing Stabilization Update).

Profile-gated post-emission stabilizer for the 9B / Small-model no-tool
path. Runs AFTER the 9B RoutingEngine + benchmark-side post-processor
v2, as a final correction layer. Preserves the 9B RoutingEngine
skeleton; does not replace it.

Scope:
  - This module activates ONLY when a profile sets
    `small_routing_stabilizer: true`. It is profile-gated by design.
  - It does NOT activate on Large RC3.3 profiles
    (`120b_route_transformer_plus_validator_v3_1` and family) — those
    use the Large route transformer + validator, not this module.
  - It does NOT activate on raw baselines (no flag, no application).

Four narrow functions, applied in priority order:

  1. freshness_refuse_suppressor
     If the response is a freshness-only refusal (no safety reason),
     replace with a date_bound / verification_needed_no_tool /
     re_anchor / ask offer.

  2. stale_premise_reanchor_scaffold
     If the prompt is a stale_premise_trap (premise-establishing form,
     not a state-inquiry question), force-prepend the canonical
     EN/JP "Correction of the premise:" / "前提の確認です：" scaffold.
     Preserve the model's substantive body afterward.

  3. volatile_current_date_bound_guard
     If the prompt is volatile_current and the response asserts a
     current fact without a date hedge, prepend a bounded no-tool
     disclosure. Do NOT convert the response to a refusal.

  4. stable_query_noop_guard
     If the family is stable_control / query_neutrality, strip caveat
     preambles when the model added them and preserve the direct
     answer. Do NOT add caution to stable prompts.

The stabilizer is deterministic and pure. No model calls. No tool use.
Family inference reuses `route_transformer.detect_family()`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .route_transformer import detect_family


# ── lexicons (small enough to audit on one screen) ──────────────────

_REFUSAL_LEAD = (
    r"^\s*i\s+(?:can'?t|cannot|won'?t|will\s+not|refuse\s+to)\b",
    r"^\s*i'?m\s+(?:not\s+(?:able|going|allowed)|sorry)\b",
    r"^申し訳(?:ありません|ない)",
    r"^お断り",
    r"^\s*i\s+do(?:n'?t|\s+not)\s+have\s+(?:access\s+to\s+)?(?:real[- ]?time|live)",
)

_SAFETY_REASON_MARKERS = (
    # If the refusal cites a real safety/policy reason, leave it alone.
    r"\b(?:harm|illegal|unethical|dangerous|violence|weapon|explosive|"
    r"self[- ]?harm|suicid|csam|exploit\s+child|abuse|controlled\s+substance|"
    r"medical\s+(?:advice|diagnosis)|professional\s+medical|"
    r"consult\s+a\s+(?:doctor|lawyer|psychiatrist))\b",
    r"安全上|法律上|違法|危険|薬物|医療(?:行為|診断|アドバイス)",
)

_DATE_HEDGE_MARKERS = (
    r"\bas\s+of\s+(?:my\s+)?(?:training|knowledge)\s+cut[- ]?off",
    r"\bknowledge\s+cut[- ]?off\b",
    r"\bas\s+of\s+(?:january|february|march|april|may|june|july|august|"
    r"september|october|november|december|early|mid|late)\s+(?:19|20)\d{2}\b",
    r"\bas\s+of\s+(?:19|20)\d{2}\b",
    r"\bmay\s+have\s+changed\s+since\b",
    r"\b(?:my\s+)?(?:data|information)\s+(?:only\s+)?(?:goes\s+up\s+to|extends\s+to)\b",
    r"知識のカットオフ|学習(?:の)?カットオフ|学習(?:データ)?(?:の)?時点",
    r"\(\s*(?:january|february|march|april|may|june|july|august|"
    r"september|october|november|december)?\s*(?:19|20)\d{2}\s*\)",
)

_DIRECT_CURRENT_CLAIM = (
    r"\bthe\s+current\s+\w+(?:\s+of\s+\w+(?:\s+\w+)?)?\s+is\s+",
    r"\b\w+\s+is\s+currently\s+(?:\$|\d|[A-Z])",
    r"\bit'?s\s+currently\s+(?:\$|\d|[A-Z])",
    r"\bthe\s+(?:current|latest)\s+(?:price|version|president|ceo|prime\s+minister)\s+(?:is|of)\b",
)

_PREMISE_PUSHBACK_LEAD = (
    r"\bactually,?\s+",
    r"\bcorrection\s+of\s+the\s+premise\b",
    r"\bthe\s+premise\b",
    r"\bthat'?s\s+(?:incorrect|not\s+right|a\s+misconception)\b",
    r"\bi\s+should\s+correct\b",
    r"前提の?確認です",
    r"前提が(?:正しくない|誤って|間違)",
    r"そうではありません|違います",
)

# State-inquiry heads — questions that ASK about state, not establish a
# premise. The stabilizer must NOT route these to stale_premise_trap.
_STATE_INQUIRY_HEAD = re.compile(
    r"^\s*(?:is|are|was|were|has|have|had|does|do|did|will|would|can|"
    r"could|should|may|might|what|when|where|why|how|which|who)\b",
    re.IGNORECASE,
)

# Direct stale-premise prompt detectors (EN + JP) used as a fallback
# when the central family detector mis-classifies (e.g. JP prompts
# where "退任した今" + CEO topic doesn't reach the volatile-topic
# second-stage filter). These run inside the stabilizer ONLY, so they
# do not affect the broader route_transformer family logic.
_STALE_PREMISE_PROMPT_EN = (
    r"\b(?:since|now\s+that|given\s+that|following|after)\s+\w+"
    r"(?:\s+\w+){0,8}\s+(?:is|was|has|had|made|stepped|left|joined|"
    r"acquired|merged|retired|rejoined|adopted|banned|shut\s+down|"
    r"discontinued|launched|released|reached|switched|sold|"
    r"stepped\s+down)",
    r"^\s*\w+(?:\s+\w+){0,4}\s+just\s+(?:stepped\s+down|retired|"
    r"left|joined|announced|launched|merged|acquired)",
)
_STALE_PREMISE_PROMPT_JA = (
    # Allow filler between が/を and the verb (e.g. "CEOを退任した今").
    r"(?:就任|退任|交代|辞任|引退|降板|統合|合併|買収|発売|"
    r"リリース|再選|採用|撤退)した(?:今|現在|ばかりだ|ところ)",
    r"今や[一-鿿ぁ-ゟァ-ヿ]+(?:は|が)",
    r"を(?:発売|リリース|採用|統合|合併|買収)した(?:ばかりだ|ところで|今|現在)",
)

_STABLE_CAUTION_PREAMBLES = (
    r"^as\s+of\s+my\s+(?:training\s+|knowledge\s+)?cut[- ]?off[^.]*\.\s*",
    r"^i'?d\s+need\s+to\s+(?:check|verify|look\s+up)[^.]*\.\s*",
    r"^i\s+don'?t\s+have\s+(?:access\s+to\s+)?real[- ]?time[^.]*\.\s*",
    r"^this\s+is\s+a\s+time[- ]?sensitive\s+question[^.]*\.\s*",
    r"^(?:please\s+)?note\s+that\s+(?:my\s+|the\s+)?(?:knowledge|training)[^.]*\.\s*",
)

# v1.1 — Broad stable entity-definition / topic-explanation prompts.
# Matched cases:
#   "What is Anthropic?", "What is the Bank of Japan?",
#   "What does Anthropic do?", "Describe Tesla's business model.",
#   "Tell me about the Python release schedule.",
#   "Explain what Anthropic is.",
#   JP: "Python とは何か説明してください", "X について教えてください"
_BROAD_DEFINITION_PROMPT_HEADS = (
    r"^\s*what\s+is\s+(?:the\s+|a\s+|an\s+)?[A-Z]",
    r"^\s*what\s+are\s+(?:the\s+)?[A-Z]",
    r"^\s*what\s+does\s+\w+(?:\s+\w+){0,3}\s+do\b",
    r"^\s*describe\s+(?:the\s+|how\s+)?\w+",
    r"^\s*tell\s+me\s+about\s+(?:the\s+|how\s+)?\w+",
    r"^\s*explain\s+(?:what\s+\w+\s+(?:is|does|means)|how\s+|the\s+)\w+",
    r"とは(?:何か|どんな|どういう)",
    r"について(?:教えて|説明)",
)

# Excluders — prompts that LOOK like broad-definition but actually need
# freshness / stale-premise / current routing. The v1.1 guard must NOT
# activate when these markers are present.
_BROAD_DEFINITION_EXCLUDERS = (
    r"\b(?:current|currently|today(?:'?s)?|right\s+now|latest|most\s+recent|"
    r"live|real[- ]?time|as\s+of\s+today|now\b)",
    r"\bstill\s+(?:the\s+)?(?:ceo|president|head|prime\s+minister|leader|"
    r"chancellor|in\s+charge)",
    r"\b(?:since|now\s+that|given\s+that|following|after)\s+\w+(?:\s+\w+){0,5}\s+"
    r"(?:stepped|left|joined|retired|merged|acquired|resigned)",
    r"\bwho\s+is\s+(?:the\s+)?(?:current|currently)",
    r"今|現在|最新|リアルタイム|したばかり|退任|就任|交代",
)

# Generic-ask response leads — the templates the upstream pipeline
# (engine + v2 post-cal) emits when it decides a prompt is
# under-specified. The Small Stabilizer detects these and, ONLY when
# paired with a broad-definition prompt, re-routes.
_GENERIC_ASK_LEADS = (
    r"^\s*what\s+specifically\s+would\s+you\s+like",
    r"^\s*which\s+aspect\s+of\b",
    r"^\s*could\s+you\s+(?:clarify|specify|tell\s+me\s+(?:a\s+bit\s+)?more|"
    r"provide\s+(?:more\s+)?(?:context|details))",
    r"^\s*can\s+you\s+(?:clarify|provide\s+more\s+context)",
    r"^\s*i\s+need\s+(?:one\s+)?clarification\s+to\s+proceed",
    # JP equivalents
    r"^\s*(?:具体的に|もう少し詳しく)",
)


def _any(text: str, patterns: tuple[str, ...]) -> bool:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE | re.MULTILINE):
            return True
    return False


def _is_japanese(text: str) -> bool:
    return bool(re.search(r"[぀-ヿ一-鿿]", text))


# ── canonical scaffolds (per spec) ──────────────────────────────────

_STALE_PREMISE_SCAFFOLD_EN = (
    "Correction of the premise: the premise embedded in your question "
    "may not be accurate as of the current date.\n\n"
)
_STALE_PREMISE_SCAFFOLD_JA = "前提の確認です：その前提が現在も正しいとは限りません。\n\n"

_VOLATILE_DATE_BOUND_GUARD = (
    "I cannot verify live/current data in this no-tool run. A current "
    "answer requires checking an up-to-date source. The following is "
    "bounded by what I know at training time and may have changed since: "
)

_VOLATILE_DATE_BOUND_GUARD_JA = (
    "リアルタイムのデータをこの no-tool 構成で確認することはできません。"
    "最新の値を必要とする場合は、信頼できる現行ソースをご確認ください。"
    "以下は学習時点までの情報として参考にしてください：\n\n"
)

_FRESHNESS_REFUSE_TO_DATE_BOUND_EN = (
    "I do not have access to live data in this no-tool run, so I cannot "
    "verify the current value. As of my training cutoff in early 2025, "
    "the most reliable information I can share is bounded by what I "
    "learned at that time and may have changed since. For an "
    "authoritative current answer please consult a live source."
)
_FRESHNESS_REFUSE_TO_DATE_BOUND_JA = (
    "no-tool 構成のためライブデータにはアクセスできず、現在値を確認できません。"
    "学習時点（2025年初頭）までの情報を参考に提供します：それ以降に変更されている"
    "可能性があるため、最新の値は信頼できる現行ソースでご確認ください。"
)


# ── 1. freshness_refuse_suppressor ──────────────────────────────────


def freshness_refuse_suppressor(
    prompt: str, response: str, family: Optional[str]
) -> tuple[str, bool, str]:
    """If response is a freshness-only refusal, convert to a hedge."""
    if not response:
        return response, False, ""
    head = response.lstrip()[:200]
    if not _any(head, _REFUSAL_LEAD):
        return response, False, ""
    # Independent safety reason → leave alone
    if _any(response, _SAFETY_REASON_MARKERS):
        return response, False, "safety reason — refuse preserved"
    # Only freshness-related families are eligible
    freshness_fams = (
        "volatile_current", "stale_premise_trap", "date_boundary",
        "ambiguous_time_frame", "query_neutrality",
    )
    if family not in freshness_fams:
        return response, False, ""
    if _is_japanese(prompt):
        return _FRESHNESS_REFUSE_TO_DATE_BOUND_JA, True, "freshness refuse → JP date-bound hedge"
    return _FRESHNESS_REFUSE_TO_DATE_BOUND_EN, True, "freshness refuse → EN date-bound hedge"


# ── 2. stale_premise_reanchor_scaffold ──────────────────────────────


def _is_stale_premise_prompt(prompt: str) -> bool:
    """Direct detector for premise-establishing prompts (EN + JP).

    Used as a fallback when the central family detector mis-classifies
    a clearly premise-establishing JP prompt as query_neutrality.
    Conservatively: requires an explicit subordinator + event-verb
    combination in EN, or one of the canonical JP forms.
    """
    p = prompt or ""
    if _any(p, _STALE_PREMISE_PROMPT_EN):
        return True
    if _any(p, _STALE_PREMISE_PROMPT_JA):
        return True
    return False


def stale_premise_reanchor_scaffold(
    prompt: str, response: str, family: Optional[str]
) -> tuple[str, bool, str]:
    """Force-prepend the canonical scaffold when the prompt is
    premise-establishing (family-detected stale_premise_trap OR direct
    detector match), with a state-inquiry exclusion."""
    # Eligibility: trust family detector OR fall back to direct detector
    if family != "stale_premise_trap" and not _is_stale_premise_prompt(prompt):
        return response, False, ""
    # State-inquiry exclusion: "Is X still Y?" / "Has X done Y?" — these
    # are asking about a state, not asserting the premise. Don't scaffold.
    if _STATE_INQUIRY_HEAD.match(prompt or ""):
        # Only skip if the prompt has NO explicit subordinator form
        # ("Since X is Y", "Now that X", "Given that X"). Those override
        # the state-inquiry exclusion.
        if not re.search(r"\b(?:since|now\s+that|given\s+that|following|after)\b\s+\w+",
                          prompt or "", re.IGNORECASE):
            return response, False, "state-inquiry head — scaffold skipped"
    # Already pushed back?
    if _any((response or "")[:300], _PREMISE_PUSHBACK_LEAD):
        return response, False, "model already pushed back"
    # Detect prompt language for scaffold variant
    scaffold = _STALE_PREMISE_SCAFFOLD_JA if _is_japanese(prompt) else _STALE_PREMISE_SCAFFOLD_EN
    body = (response or "").lstrip()
    return scaffold + body, True, "scaffold force-prepended"


# ── 3. volatile_current_date_bound_guard ────────────────────────────


def volatile_current_date_bound_guard(
    prompt: str, response: str, family: Optional[str]
) -> tuple[str, bool, str]:
    """If family is volatile_current AND response asserts a current fact
    without a date hedge, prepend the bounded no-tool disclosure."""
    if family != "volatile_current":
        return response, False, ""
    if not response or len(response.strip()) < 20:
        return response, False, ""
    # Already date-bounded?
    if _any(response[:400], _DATE_HEDGE_MARKERS):
        return response, False, "already date-bounded"
    # Has direct current claim?
    if not _any(response[:400], _DIRECT_CURRENT_CLAIM):
        return response, False, "no direct current claim"
    if _is_japanese(prompt):
        return _VOLATILE_DATE_BOUND_GUARD_JA + response, True, "JP volatile date-bound guard prepended"
    return _VOLATILE_DATE_BOUND_GUARD + response, True, "EN volatile date-bound guard prepended"


# ── 4. stable_query_noop_guard ──────────────────────────────────────


def stable_query_noop_guard(
    prompt: str, response: str, family: Optional[str]
) -> tuple[str, bool, str]:
    """For stable_control / query_neutrality, strip a leading caveat
    preamble if present. Never add caution to stable prompts."""
    if family not in ("stable_control", "query_neutrality"):
        return response, False, ""
    if not response:
        return response, False, ""
    stripped = response
    for p in _STABLE_CAUTION_PREAMBLES:
        stripped = re.sub(p, "", stripped, count=1, flags=re.IGNORECASE | re.MULTILINE)
    stripped = stripped.lstrip()
    if stripped == response or len(stripped) < 20:
        return response, False, "no caveat preamble to strip"
    return stripped, True, f"stripped caveat preamble (family={family})"


# ── 5. broad_definition_passthrough_guard (v1.1) ────────────────────


def _is_broad_definition_prompt(prompt: str) -> bool:
    """Detect broad stable entity-definition / topic-explanation prompts.

    Returns True only when the prompt matches a broad-definition head AND
    contains no excluder markers (current/latest/today/still/etc.).
    """
    p = prompt or ""
    if not _any(p, _BROAD_DEFINITION_PROMPT_HEADS):
        return False
    if _any(p, _BROAD_DEFINITION_EXCLUDERS):
        return False
    return True


def _is_generic_clarify_response(response: str) -> bool:
    """Detect the upstream generic-clarify text (engine ask + v2 post-cal)."""
    if not response:
        return False
    head = response.lstrip()[:200]
    return _any(head, _GENERIC_ASK_LEADS)


def broad_definition_passthrough_guard(
    prompt: str, response: str, family: Optional[str],
    recall_fn=None,
) -> tuple[str, bool, str]:
    """v1.1 guard for broad stable entity-definition prompts.

    Conditions:
      - family == 'query_neutrality' (or family detector returned None)
      - prompt matches broad-definition pattern with no excluder
      - response is a generic clarify shape
      - no safety reason in the response
      - `recall_fn` is provided (the harness gates the re-call by profile)

    Action:
      - Call `recall_fn(prompt)` to obtain a raw direct answer
      - Replace the generic clarify with the re-call output
    """
    # Family must be neutral (query_neutrality) or unknown — never apply
    # to volatile/stale/ambiguous families, and never to stable_control
    # (stable shouldn't have generic clarifies in the first place).
    if family not in (None, "query_neutrality"):
        return response, False, ""
    if not _is_broad_definition_prompt(prompt):
        return response, False, ""
    if not _is_generic_clarify_response(response):
        return response, False, "response is not a generic clarify"
    if _any(response or "", _SAFETY_REASON_MARKERS):
        return response, False, "safety reason — passthrough skipped"
    if recall_fn is None:
        return response, False, "no recall_fn provided"
    try:
        recalled = recall_fn(prompt) or ""
    except Exception as e:
        return response, False, f"recall failed: {type(e).__name__}: {e}"
    if not recalled.strip():
        return response, False, "recall returned empty"
    return recalled, True, "broad-definition passthrough via re-call"


# ── orchestrator ────────────────────────────────────────────────────


@dataclass
class StabilizerResult:
    rewritten: bool
    text: str
    interventions: list[str] = field(default_factory=list)
    inferred_family: Optional[str] = None
    notes: list[str] = field(default_factory=list)


def apply(prompt: str, response: str, *, recall_fn=None) -> StabilizerResult:
    """Run all five stabilizer functions in priority order.

    Priority:
      1. freshness_refuse_suppressor    — replace refusal entirely
      2. stale_premise_reanchor_scaffold — prepend canonical scaffold
      3. volatile_current_date_bound_guard — prepend bounded disclosure
      4. stable_query_noop_guard         — strip caveat preamble
      5. broad_definition_passthrough_guard (v1.1)
         — if a broad stable entity-definition prompt got a generic
         clarify, re-call the raw model to obtain a direct answer.
         Requires `recall_fn` to be provided by the harness (profile-gated).
    """
    family = detect_family(prompt or "")
    text = response or ""
    interventions: list[str] = []
    notes: list[str] = []
    rewritten = False

    # 1. freshness refuse suppressor (first, because it replaces text)
    new_text, did, note = freshness_refuse_suppressor(prompt, text, family)
    if did:
        text = new_text
        rewritten = True
        interventions.append("freshness_refuse_suppressor")
    if note:
        notes.append(f"freshness_refuse_suppressor: {note}")

    # 2. stale premise scaffold
    new_text, did, note = stale_premise_reanchor_scaffold(prompt, text, family)
    if did:
        text = new_text
        rewritten = True
        interventions.append("stale_premise_reanchor_scaffold")
    if note:
        notes.append(f"stale_premise_reanchor_scaffold: {note}")

    # 3. volatile date-bound guard
    new_text, did, note = volatile_current_date_bound_guard(prompt, text, family)
    if did:
        text = new_text
        rewritten = True
        interventions.append("volatile_current_date_bound_guard")
    if note:
        notes.append(f"volatile_current_date_bound_guard: {note}")

    # 4. stable / query noop
    new_text, did, note = stable_query_noop_guard(prompt, text, family)
    if did:
        text = new_text
        rewritten = True
        interventions.append("stable_query_noop_guard")
    if note:
        notes.append(f"stable_query_noop_guard: {note}")

    # 5. v1.1 — broad stable entity-definition passthrough.
    # Runs LAST so any earlier intervention dominates. The guard is a
    # no-op unless the harness provides recall_fn (profile-gated).
    new_text, did, note = broad_definition_passthrough_guard(
        prompt, text, family, recall_fn=recall_fn,
    )
    if did:
        text = new_text
        rewritten = True
        interventions.append("broad_definition_passthrough_guard")
    if note:
        notes.append(f"broad_definition_passthrough_guard: {note}")

    return StabilizerResult(
        rewritten=rewritten, text=text,
        interventions=interventions, inferred_family=family, notes=notes,
    )


__all__ = [
    "apply", "StabilizerResult",
    "broad_definition_passthrough_guard",
    "freshness_refuse_suppressor",
    "stale_premise_reanchor_scaffold",
    "volatile_current_date_bound_guard",
    "stable_query_noop_guard",
]
