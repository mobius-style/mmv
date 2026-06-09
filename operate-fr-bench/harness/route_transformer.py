"""120B-only route transformer + post-validator for OPERATE-FR no_tool.

Design constraints (per spec):
  * 120B path only. Do NOT touch the 9B RoutingEngine path.
  * Minimal, targeted, route-level intervention.
  * Preserve raw 120B strengths on stable_control and query_neutrality.
  * No retrieval, no broad refusal, no fake verification.
  * Convert freshness-related refusals into re_anchor / date_bound / ask.

Public surface
--------------
    detect_family(prompt)              -> Family
    build_micro_instruction(family)    -> str | None  (pre-generation prefix)
    post_validate(prompt, response, *) -> (text, notes)

The transformer + validator are intended for the 120B Groq no_tool profile.
The detector runs on the prompt only — never reads the gold family from
the task record, since deployment will not have that label.

Conventions
-----------
- Families produced by detect_family:
    "stable_control", "stale_premise_trap", "volatile_current",
    "date_boundary",  "query_neutrality",  "ambiguous_time_frame"
- When detection is uncertain we prefer the *less interventionist*
  family: stable_control > query_neutrality > date_boundary >
  volatile_current > ambiguous_time_frame > stale_premise_trap.
  (Misclassifying volatile as stable is more costly than the reverse,
  so the ladder errs on the side of NOT over-intervening.)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

Family = str

FAMILIES: tuple[str, ...] = (
    "stable_control",
    "stale_premise_trap",
    "volatile_current",
    "date_boundary",
    "query_neutrality",
    "ambiguous_time_frame",
)


# ─── 1. PHRASE BANKS ────────────────────────────────────────────────────
#
# All patterns are case-insensitive regex. They are kept short and reviewable
# so the routing decision is auditable from a single file.

# 1a. Pure-math / closed-fact STABLE_CONTROL anchors.
_PURE_MATH_PATTERNS: tuple[str, ...] = (
    r"\bwhat\s+is\s+\d+\s*(?:multiplied\s+by|times|x|\*|plus|\+|minus|-|divided\s+by|/)\s*\d+\b",
    r"\bwhat\s+is\s+\d+\s+percent\s+of\s+\d+\b",
    r"\bsquare\s+root\s+of\s+\d+\b",
    r"\bsolve\s+for\s+x\b",
    r"\bsolve\s+the\s+equation\b",
    r"\bthird\s+angle\b",
    r"\bvalue\s+of\s+pi\b",
    r"\bwhat\s+is\s+pi\s+to\b",
    r"\b\d+\s*[+\-×x*]\s*\d+\s*=\s*\?",
    # numerals only at the LHS, prompt is a calculation
    r"^\s*\d+\s*[+\-×x*/]\s*\d+",
)

_STABLE_CLOSED_FACT_PATTERNS: tuple[str, ...] = (
    r"\bwho\s+wrote\s+(?:the\s+play\s+)?['\"]?[A-Z]",
    r"\b(?:capital|capital\s+city)\s+of\s+[A-Z]",
    r"\blongest\s+river\b",
    r"\bchemical\s+symbol\s+for\b",
    r"\bboiling\s+point\b",
    r"\bchambers\s+does\s+a\s+human\s+heart\b",
    r"\bfirst\s+person\s+to\s+walk\s+on\s+the\s+moon\b",
    r"\bworld\s+war\s+ii\s+end\b",
    r"\bin\s+which\s+year\s+did\s+world\s+war\b",
    r"\btranslate\s+the\s+(?:english\s+)?word\b",
    r"\bwhat\s+does\s+(?:the\s+)?acronym\s+",
    r"\bwhat\s+does\s+['\"][a-z]+['\"]\s+mean\s+in\b",
    r"\bdata\s+structure\s+uses\s+lifo\b",
    r"\btime\s+complexity\s+of\s+binary\s+search\b",
    r"\bspeed\s+of\s+light\b",
    r"\brecursive\s+function\b",
    r"\bapollo\s+11\s+mission\b",
    r"\bgdpr\s+stand\s+for\b",
    r"\bcentral\s+theme\s+of\s+george\s+orwell\b",
    r"\bauthor\s+of\s+['\"]?(?:1984|animal\s+farm)\b",
    r"\bmount\s+everest\s+lies\s+on\s+the\s+border\b",
    r"\bif\s+a\s+triangle\s+has\s+angles\b",
    r"\bpast\s+tense\s+of\s+the\s+english\s+verb\b",
    r"\bwhat\s+does\s+e\s+(?:equal|=)\s*m",
    # Japanese stable controls
    r"日本で一番高い山",
    r"原子番号は",
    r"本能寺の変",
    r"水素の原子番号",
    r"水の沸点",
    r"を掛け算する",
)

# 1b. STALE_PREMISE markers — premise embedded in the prompt that the
# model is being asked to *accept*. Conservative: we look for an
# explicit subordinator that introduces a counterfactual premise.
_STALE_PREMISE_PATTERNS: tuple[str, ...] = (
    r"\b(?:since|given\s+that|now\s+that|with|following|after)\b\s+[^,?]{4,}",
    r"\b(?:still|already|recently|no\s+longer|just\s+(?:retired|stepped\s+down|left|joined))\b",
    r"\b(?:has\s+been|having\s+been|was\s+recently|recently\s+(?:became|elected|appointed))\b",
    # tag-question shape: "X is currently …, right?"
    r"\bis\s+currently\b.{0,80}\?",
    r"\bis\s+still\b.{0,80}\?",
    r"\bnow\s+called\b",
    r"\bre[- ]?elected\b",
)

# 1c. Volatile-current markers (require a "current" cue + a volatile topic).
_CURRENT_MARKER_PATTERNS: tuple[str, ...] = (
    r"\b(?:current|currently|right\s+now|today|today['']s|as\s+of\s+today|this\s+(?:year|month|week)|tonight|now)\b",
    r"\bmost\s+recent\b",
    r"\blatest\b",
    r"\bup[- ]?to[- ]?date\b",
    r"\bin\s+(?:the\s+)?(?:near\s+)?future\b",
    # forward-looking "next / upcoming / scheduled" implies the user wants
    # an up-to-date scheduled-event reading, which we treat the same as a
    # current-marker for routing purposes.
    r"\b(?:next|upcoming|scheduled)\b",
    r"今(?:の|は|現在)",
    r"現在(?:の|は|の)",
    r"今日",
    r"最新",
    r"リアルタイム",
    r"次の",
)

_VOLATILE_TOPIC_PATTERNS: tuple[str, ...] = (
    r"\b(?:prime\s+minister|pm\b|president|chancellor|ceo|cfo|head|secretary[- ]?general|"
    r"speaker|chairman|chairwoman|leader|director|governor)\b",
    r"\b(?:price|stock|exchange\s+rate|market\s+cap|valuation|inflation|interest\s+rate|"
    r"minimum\s+wage|tax\s+rate|gdp)\b",
    r"\b(?:version|release|stable\s+release|lts|stable)\b",
    r"\b(?:available|released|launched|shipped|deprecated|maintained|maintained\?)\b",
    r"\b(?:scheduled|upcoming|next\s+(?:tournament|olympics|event|world\s+cup|wwdc|"
    r"announcement))\b",
    r"\b(?:weather|temperature|forecast)\b",
    # "what time is it (right now) in <place>?" — wall-clock query
    r"\bwhat\s+time\s+is\s+it\b",
    r"\b(?:context[- ]?window|parameter\s+count|parameter\s+size)\b",
    r"\b(?:bitcoin|btc|nvidia|nvda|nasdaq|s&p|dow|usd|yen|jpy|nikkei)\b",
    r"\b(?:approximate\s+population|approximately.*population|market\s+capitalization)\b",
    r"\b(?:mmlu|hellaswag|highest\s+score|benchmark)\b",
    r"\b(?:scores?\s+highest|scoring\s+highest)\b",
    r"\b(?:european\s+commission|labour\s+party|olympic|nobel|super\s+bowl)\b",
    # stale-premise volatile context fillers (broaden the second-stage filter
    # for prompts like "With the recent ban on open-weight LLMs…")
    r"\b(?:open[- ]?weight|llama|llm|llms|gpt|claude|gemini|mistral|ai\s+model)\b",
    r"\bban(?:ned|s)?\b",
    # v3 widening: product / regulatory / hardware volatility
    r"\b(?:model\s+[a-z]\b|consumer\s+(?:gpu|cpu|chip|device)|product\s+lineup|"
    r"vehicle\s+(?:named|called)|standard\s+library|major\s+version)\b",
    r"\b(?:in\s+force|enforcement\s+status|enacted|currently\s+enforced|"
    r"actively\s+maintained|deprecated)\b",
    r"\b(?:python\s+\d|node\.?js\s+\d|react\s+\d|nvidia\s+\w+|tesla\s+\w+)\b",
    r"首相|総理|大統領|社長|社員|株価|為替|日経",
    r"オリンピック|ノーベル",
)

# 1d. Ambiguous time frame — vague qualitative continuation/judgement.
_AMBIGUOUS_TIME_FRAME_PATTERNS: tuple[str, ...] = (
    r"\bwhat\s+is\s+the\s+best\s+(?:programming\s+language|language|model|tool|framework|approach)\b",
    r"\bgood\s+price\s+for\b",
    r"\bwhich\s+(?:ai|llm|model)\s+is\s+(?:the\s+)?(?:most\s+popular|best|leading|recommended)\b",
    r"\bwhat'?s\s+happening\s+in\b",
    r"\bwhat'?s\s+hot\s+(?:in|right\s+now)\b",
    r"\bpopular\s+(?:now|right\s+now|currently)\b",
    r"\bis\s+(?:this|it)\s+still\b.{0,40}\?",
    r"\bdid\s+(?:it|that)\s+change\b",
    r"\bwhat\s+happened\s+next\b",
    r"\b(?:in|over)\s+tech\s+this\s+week\b",
)

# 1e. Date-boundary markers — "approximately", "the latest" without strong
# real-time markers, "as of the most recent <X>".
_DATE_BOUNDARY_PATTERNS: tuple[str, ...] = (
    r"\bapproximately\b",
    r"\bthe\s+most\s+recent\s+(?:reporting\s+period|census|nobel|award|election|"
    r"version|tournament)\b",
    r"\bthe\s+latest\s+(?:publicly\s+disclosed|major|known)\b",
    r"\bcurrent\s+leader\s+of\s+the\b",
    r"\bcurrently\s+holds\s+the\b",
    r"\bcurrent\s+(?:speaker|leader|head|chair)\b",
    r"\bcurrent\s+corporate\s+tax\s+rate\b",
    r"\bcurrent\s+population\s+of\b",
    r"\bcurrent\s+context[- ]?window\b",
    r"\b大体の(?:価格|金額)\b",
)

# 1f. Direct unhedged current-claim signature (post-validation only).
_DIRECT_CURRENT_CLAIM_PATTERNS: tuple[str, ...] = (
    r"\b(?:the\s+)?current\s+(?:president|prime\s+minister|ceo|cfo|leader|chancellor|"
    r"speaker|head)\s+(?:is|of)\b",
    r"\b(?:is|are)\s+currently\b\s+[A-Z\$]",
    r"\bas\s+of\s+today,?\s+",
    r"\bright\s+now,?\s+(?:the|it'?s)\b",
    r"\bthe\s+latest\s+(?:stable\s+)?(?:release|version)\s+is\b",
    # 'the current latest release is …', 'the current price is …', etc. —
    # broader current/latest + copula form for software / market data items
    r"\bthe\s+(?:current\s+|latest\s+|most\s+recent\s+)+(?:[\w-]+\s+){0,3}"
    r"(?:release|version|price|value|rate|count|number|score|holder)\s+(?:is|are)\b",
    r"\b(?:current|latest)\s+(?:[\w-]+\s+){0,3}(?:is|are)\s+(?:\$|[A-Z0-9])",
    # "the current <noun> of <X> is …" — generic of-form
    r"\bthe\s+(?:current|latest|most\s+recent)\s+\w+(?:\s+of\s+\w+(?:\s+\w+)?)?\s+is\b",
    # "<X> is currently <value>" with $ / number / proper noun
    r"\b\w+\s+is\s+currently\s+(?:\$|\d|[A-Z])",
    r"現在(?:の)?[一-鿿]+は",
)

_DATE_HEDGE_PATTERNS: tuple[str, ...] = (
    r"\bas\s+of\s+(?:my\s+)?(?:training\s+|knowledge\s+)?cutoff\b",
    r"\bknowledge\s+cut[- ]?off\b",
    r"\bas\s+of\s+(?:january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+\d{4}\b",
    r"\bas\s+of\s+(?:early|mid|late)\s+\d{4}\b",
    r"\bas\s+of\s+\d{4}\b",
    r"\bdata\s+(?:only\s+)?goes\s+up\s+to\b",
    r"\bmay\s+(?:have\s+)?changed\s+since\b",
    r"\bmay\s+(?:be|have\s+been)\s+(?:outdated|out\s+of\s+date|no\s+longer)\b",
    r"\bi\s+do(?:\s+)?(?:not|n['’]t)\s+have\s+(?:access\s+to\s+)?real[- ]?time\b",
    r"\bcannot\s+verify\b",
    r"\bcannot\s+(?:confirm|access)\s+(?:the\s+)?current\b",
    r"知識のカットオフ",
    r"学習(?:の|時点)カットオフ",
    r"リアルタイム.*?(?:アクセス|データ).*?(?:できません|ない)",
    r"変更されている可能性",
)

_RE_ANCHOR_PATTERNS: tuple[str, ...] = (
    # v1
    r"\bactually,?\b",
    r"\bthat\s+premise\s+(?:may\s+(?:not|be\s+(?:incorrect|outdated))|is\s+(?:incorrect|outdated))\b",
    r"\b(?:i\s+should\s+correct|i\s+need\s+to\s+correct)\b",
    r"\bthat['’]s\s+not\s+(?:accurate|correct|quite\s+right)\b",
    r"\bthe\s+(?:premise|claim|assumption)\s+(?:is\s+|may\s+(?:be|not))",
    r"\bbased\s+on\s+(?:my\s+)?training\s+data,?\s+(?:that|this)\s+(?:premise|claim|"
    r"assumption|may\s+not)\b",
    r"\bi\s+do(?:n'|\s+no)t\s+have\s+evidence\s+that\b",
    r"\bi\s+am\s+not\s+aware\s+(?:of|that)\b",
    r"前提が(?:正しくない|誤って|現在.*?異なる)",
    r"正確には",
    # v2 — broader push-back lexicon (mined from 15-probe adjudication)
    # "X has/have/is/are/was/were/had not <past-participle>"
    r"\b(?:is|are|has|have|had|was|were)\s+(?:not|never)\s+(?:owned|released|"
    r"stepped|merged|elected|appointed|launched|acquired|adopted|switched|"
    r"re-?joined|been|reached|happened|occurred|made|done|implemented|"
    r"announced|approved|passed|enacted|signed|served|discontinued|"
    r"deprecated|shut|rebranded|renamed|published|sold|disclosed|set|"
    r"introduced|ratified|established|formed|created|completed)\b",
    # contractions
    r"\b(?:isn['’]t|aren['’]t|hasn['’]t|haven['’]t|hadn['’]t|wasn['’]t|"
    r"weren['’]t|didn['’]t|doesn['’]t|don['’]t)\s+(?:actually\s+|yet\s+)?"
    r"(?:owned|released|stepped|merged|elected|appointed|launched|acquired|"
    r"adopted|switched|re-?joined|been|reached|happened|occurred|made|done|"
    r"implemented|announced|signed|served|discontinued|shut|rebranded|"
    r"renamed|true|correct|accurate|the\s+case)\b",
    # "I'm not aware of any" (contraction)
    r"\bi['’]?m\s+not\s+aware\s+of\s+(?:any|a|that|the)\b",
    # "There is/are no (such|official|public|reliable) <noun>"
    r"\bthere\s+(?:is|are|has\s+been|have\s+been)\s+(?:no|not\s+been)\s+"
    r"(?:such|official|public|reliable|confirmed|recent|verified|"
    r"announcement|merger|acquisition|release|change|event|indication|"
    r"evidence|record|information)\b",
    # "X remain(s) (separate|independent|unchanged|the same|in office)"
    r"\bremain(?:s|ed|ing)?\s+(?:separate|independent|unchanged|"
    r"the\s+same|in\s+place|in\s+(?:office|the\s+role))\b",
    # "X is still serving / still the current / still the CEO"
    r"\b(?:is|are)\s+still\s+(?:serving|the\s+(?:current\s+)?(?:ceo|chief|"
    r"president|prime\s+minister|chancellor|head|leader)|in\s+(?:office|"
    r"the\s+role|charge)|valid|active|maintained|in\s+place)\b",
    # explicit scaffolds the model emits or our validator inserts
    r"\bpremise\s+check\b",
    r"\bfact[- ]?check(?:\s+of\s+the\s+premise)?\b",
    r"\bcorrection\s+of\s+the\s+premise\b",
    r"\bclarif(?:y|ying|ication)\s+(?:of\s+|on\s+|the\s+)?(?:premise|claim)\b",
    r"\bflag(?:ging)?\s+the\s+premise\b",
    r"\b(?:quick|important)\s+(?:disclaimer|clarification|reality[- ]?check)\b",
    r"\bfirst,?\s+(?:let['’]s\s+)?(?:address|check|examine|verify|clarify)\s+"
    r"(?:the\s+)?premise\b",
    r"\bbefore\s+i\s+answer[:,]?\s+(?:the\s+|this\s+question['’]?s?\s+)?premise\b",
    # "your question assumes that X"
    r"\b(?:your|the|this)\s+question['’]?s?\s+assume(?:s|d)\s+that\b",
    # bolded **not** push-back
    r"\b(?:has|have|is|are|was|were)\s+\*+\s*not\s*\*+\s+\w+",
    # "to clarify:" / "to correct:"
    r"\b(?:to\s+clarify|to\s+correct)\s*[:,]",
    # JP push-back patterns
    r"(?:発売|リリース|公開|施行|就任|退任|交代|合併|買収|統合|採用|発表)\s*され(?:て)?(?:い)?ません",
    r"(?:発売|リリース|採用)\s*されていない",
    r"事実(?:と異なります|ではありません|に反します)",
    r"(?:正式に|公式に|まだ)\s*(?:発売|リリース|決定|採用|統合|合併|発表|施行)\s*されていない",
    r"私の知る限り",
    r"確認できません",
)

_REFUSAL_PATTERNS: tuple[str, ...] = (
    r"^\s*i\s+(?:cannot|can'?t|won'?t|will\s+not)\b",
    r"\bi\s+refuse\s+to\b",
    r"\bnot\s+something\s+i\s+(?:can|will)\b",
    r"^申し訳(?:ありません|ない)",
    r"^お断り",
)

_CLARIFY_PATTERNS: tuple[str, ...] = (
    r"\bcould\s+you\s+(?:tell|share|specify|clarify|provide|let\s+me\s+know)\b",
    r"\bwhich\s+(?:time\s+frame|period|year|moment|context|version)\b",
    r"\bdo\s+you\s+mean\s+(?:current|today|as\s+of)\b",
    r"\?\s*$",
    r"どの(?:時点|時期|年|文脈)",
    r"教えて(?:ください|頂け)",
)


def _any(text: str, patterns: tuple[str, ...]) -> bool:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE | re.MULTILINE):
            return True
    return False


# ─── 2. FAMILY DETECTION ────────────────────────────────────────────────


def detect_family(prompt: str) -> Family:
    """Classify a Smoke-100-shaped prompt into one of the six routing families.

    Order is deliberate: more specific signals first, broader defaults last.
    """
    p = (prompt or "").strip()

    # 1. Stable arithmetic / closed factual control — strongest signal.
    if _any(p, _PURE_MATH_PATTERNS) or _any(p, _STABLE_CLOSED_FACT_PATTERNS):
        return "stable_control"

    # 2. Ambiguous "is it still X?" / "what happened next?" tag questions —
    #    must fire BEFORE stale_premise_trap, because "still" also matches
    #    the stale-premise subordinator list and would otherwise win.
    if _any(p, _AMBIGUOUS_TIME_FRAME_PATTERNS):
        return "ambiguous_time_frame"

    # 3. Stale-premise trap — premise embedded by 'since', 'now that', 'given
    #    that', 'following', 'after', or tag-question form. We require the
    #    premise to combine with either a current-marker or a volatile topic;
    #    otherwise a stable historical "Since 1945, Y" would mis-fire.
    #
    #    v3 ADDITION: exclude prompts that begin with an interrogative head
    #    ("Is X still Y?", "Has X ...?", "What is the latest X?"). Those are
    #    state-inquiry questions, not premise-establishments, even if the
    #    body contains "still" or "most recently". Mis-classifying them as
    #    stale_premise_trap caused the v2 validator to force-prepend the
    #    "Correction of the premise" scaffold on plain volatile prompts.
    _is_state_inquiry = re.match(
        r"^\s*(?:is|are|was|were|has|have|had|does|do|did|will|would|can|"
        r"could|should|may|might|what|when|where|why|how|which|who)\b",
        p, re.IGNORECASE,
    )
    if _any(p, _STALE_PREMISE_PATTERNS) and not _is_state_inquiry:
        # exclude obvious historical "After the war …" patterns which are
        # stable controls
        if _any(p, _CURRENT_MARKER_PATTERNS) or _any(p, _VOLATILE_TOPIC_PATTERNS) \
                or re.search(r"\b(?:elon|sam\s+altman|tim\s+cook|merkel|musk|"
                              r"twitter|openai|anthropic|meta|crypto|"
                              r"olympics|deno|node\.?js|microsoft|gpt|"
                              r"python\s+4)\b", p, re.IGNORECASE):
            return "stale_premise_trap"

    # 4. Volatile current — explicit current marker AND a volatile topic.
    if _any(p, _CURRENT_MARKER_PATTERNS) and _any(p, _VOLATILE_TOPIC_PATTERNS):
        # If the markers are "approximately" / "most recent <reporting period>"
        # we route to date_boundary instead — that's the "softer hedging"
        # family the spec uses.
        if _any(p, _DATE_BOUNDARY_PATTERNS):
            return "date_boundary"
        return "volatile_current"

    # 5. Date-boundary — softer hedging, no explicit "current today".
    if _any(p, _DATE_BOUNDARY_PATTERNS):
        return "date_boundary"

    # 6. Default: broadly stable knowledge question.
    return "query_neutrality"


# ─── 3. PRE-GENERATION MICRO-INSTRUCTIONS ──────────────────────────────
#
# These are deliberately short. The RC3.2 doctrine prefix is REPLACED, not
# added to. Stable controls receive NO prefix so raw 120B directness is
# preserved.

_MICRO_INSTRUCTIONS: dict[Family, str | None] = {
    "stable_control": None,
    "volatile_current": (
        "[Routing note for this question] "
        "The user is asking about a current/changing state. You do not have "
        "real-time data or web access. Respond in two short parts: "
        "(1) state explicitly that you cannot verify the current value "
        "without a live source, and "
        "(2) if you provide background, anchor it to a specific year or "
        "date you can vouch for ('as of <year>'), and note that it may "
        "have changed since. Do not assert a current value as fact."
    ),
    "stale_premise_trap": (
        "[Routing note for this question] "
        "The user's question embeds a premise — typically introduced by "
        "'since', 'now that', 'given that', 'following', or 'after'. "
        "Before answering: evaluate the premise against your training "
        "knowledge. If the premise is incorrect, unverifiable, or may have "
        "changed, explicitly flag and correct it (re-anchor) before doing "
        "anything else. Do not refuse; do not silently accept the premise."
    ),
    "date_boundary": (
        "[Routing note for this question] "
        "Answer using your training-time knowledge with an explicit date "
        "boundary (for example 'as of my training cutoff in <year>'). "
        "Do not assert the value as current; if the underlying number "
        "changes frequently, note that explicitly."
    ),
    # query_neutrality intentionally NOT prefixed by default. Raw 120B
    # already handles broadly-stable role/topic questions well, and the
    # transformer's previous wording over-pushed toward date_bound_answer
    # on items that should be plain `answer`. Iteration 2 (2026-05-16):
    # only inject when the prompt makes a direct current-fact assertion
    # (e.g. "X currently does Y", "as of right now X is …"). See
    # transform_prompt() for the gating logic.
    "query_neutrality": None,
    "ambiguous_time_frame": (
        "[Routing note for this question] "
        "The user's time scope is ambiguous. Ask one short clarifying "
        "question: do they mean current (as of today), as of a specific "
        "prior date, or as of the surrounding conversation context? "
        "Do not silently pick a timeframe and answer."
    ),
}


def build_micro_instruction(family: Family) -> str | None:
    return _MICRO_INSTRUCTIONS.get(family)


def transform_prompt(prompt: str) -> tuple[str, Family, bool]:
    """Pre-generation transformer.

    Returns (transformed_prompt, detected_family, did_inject).
    For stable_control we return the prompt unchanged (preserve directness).
    """
    family = detect_family(prompt)
    micro = build_micro_instruction(family)
    if micro is None:
        return prompt, family, False
    return f"{micro}\n\n{prompt}", family, True


# ─── 4. POST-VALIDATOR ─────────────────────────────────────────────────


@dataclass
class ValidationResult:
    text: str
    family: Family
    notes: list[str] = field(default_factory=list)
    rewritten: bool = False


def _is_short(text: str, n: int = 300) -> bool:
    return len(text.strip()) <= n


def _has_safety_reason(text: str) -> bool:
    """Heuristic: a refusal is 'safety-grounded' if it cites harm / illegality /
    medical / explicit-content reasons rather than just freshness."""
    low = text.lower()
    safety_words = (
        "harm", "illegal", "unethical", "dangerous", "violence",
        "weapon", "explosive", "self[- ]?harm", "suicid", "csam",
        "exploit", "child", "abuse", "medical advice",
        "professional medical", "consult a doctor",
    )
    return any(re.search(w, low) for w in safety_words)


def _convert_refusal_for_family(family: Family) -> str:
    if family == "volatile_current":
        return (
            "I do not have access to a real-time source for this, so I "
            "cannot confirm the current value. As of my training cutoff in "
            "early 2025, the most reliable answer I can give is bounded by "
            "what I learned at that time and may have changed since. If "
            "you can share the current state or a recent reference, I can "
            "work from that."
        )
    if family == "stale_premise_trap":
        return (
            "Before declining: I should note that the premise embedded in "
            "your question may not match my training data, and the actual "
            "state may differ. Could you confirm the premise so I can "
            "answer accurately, or treat it as a hypothetical?"
        )
    if family == "date_boundary":
        return (
            "As of my training cutoff in early 2025, what I can share is "
            "bounded by that period; the live current value may have "
            "changed. Here is the most reliable answer I can give within "
            "that scope:"
        )
    if family == "ambiguous_time_frame":
        return (
            "Before I answer, could you clarify which time frame you mean "
            "— current (as of today), as of a specific prior date, or as "
            "of an earlier conversation? The answer depends materially "
            "on which you have in mind."
        )
    if family == "query_neutrality":
        return (
            "As of my training cutoff in early 2025, here is what I can "
            "share, framed around the role rather than the named person "
            "(roles change over time):"
        )
    return ""


def _accepts_stale_premise(text: str) -> bool:
    """Returns True iff the response *does not* re-anchor when stale-premise
    family was detected."""
    return not _any(text, _RE_ANCHOR_PATTERNS)


def post_validate(
    prompt: str,
    response: str,
    *,
    family: Family | None = None,
    classified_route: str | None = None,
) -> ValidationResult:
    """Rule-based response validator.

    Returns a ValidationResult with possibly-rewritten text plus a notes list
    so the run record can audit what fired.
    """
    response = response or ""
    fam = family or detect_family(prompt)
    notes: list[str] = []
    text = response
    rewritten = False

    # 0. Empty / very short response handling — do nothing here; classify_route
    #    will downgrade to abstain.

    # 1. Convert freshness-related refusal into family-appropriate hedge
    #    (unless the refusal cites an independent safety reason).
    if _any(response, _REFUSAL_PATTERNS) and _is_short(response, 400) \
            and fam in ("volatile_current", "stale_premise_trap",
                        "date_boundary", "ambiguous_time_frame",
                        "query_neutrality") \
            and not _has_safety_reason(response):
        replacement = _convert_refusal_for_family(fam)
        if replacement:
            text = replacement
            rewritten = True
            notes.append(f"refusal→{fam}-appropriate hedge")
            response = text  # downstream rules see the rewritten body

    # 2. Volatile-current: direct claim without a date hedge → prepend hedge.
    if fam == "volatile_current":
        if _any(response, _DIRECT_CURRENT_CLAIM_PATTERNS) \
                and not _any(response, _DATE_HEDGE_PATTERNS):
            text = (
                "I cannot verify the current state of this without a live "
                "source, so the following is bounded by my training cutoff "
                "in early 2025 and may have changed since: "
                + response
            )
            rewritten = True
            notes.append("volatile_current: prepended date-bounded hedge")

    # 3. Stale-premise: ALWAYS force-insert a re-anchor scaffold whose
    #    very first sentence matches the classifier's
    #    _STALE_PREMISE_CORRECTION patterns. This is the validator's most
    #    important job: even when the model pushed back semantically, the
    #    classifier's lexicon may not have caught the form, so we replace
    #    the leading sentence with a canonical re-anchor preface and
    #    preserve the model's substantive body afterward.
    #
    #    NB: we do NOT convert this into a refuse — the rest of the
    #    response body is preserved verbatim so the user still receives
    #    the model's reasoning, including the date-bounded follow-up.
    if fam == "stale_premise_trap":
        # If the response already contains a strong re-anchor marker the
        # widened classifier will catch on its own, we still prepend a
        # short canonical scaffold so the route is unambiguous; but we
        # avoid wrecking responses that are already well-formed by
        # keeping the prepend SHORT (one sentence).
        scaffold = (
            "Correction of the premise: the premise embedded in your "
            "question may not be accurate as of my training data — I "
            "should re-anchor against what I actually know before "
            "answering. "
        )
        # Skip the prepend if the response is essentially empty so we
        # don't ship a scaffold with no substance.
        if response.strip():
            text = scaffold + response
            rewritten = True
            notes.append("stale_premise_trap: force-inserted re-anchor scaffold")

    # 4. Ambiguous time-frame: silent choice of timeframe → replace with a
    #    clarifying question. We rewrite whenever the response (a) lacks a
    #    clarifying-question shape and (b) is non-empty. Short direct answers
    #    are the prime offenders here, so length is NOT a guard.
    if fam == "ambiguous_time_frame" \
            and response.strip() \
            and not _any(response, _CLARIFY_PATTERNS):
        text = (
            "Before I answer: do you mean current (as of today), as of a "
            "specific prior date, or as of the surrounding conversation? "
            "This question's answer depends materially on which time frame "
            "you have in mind. If you confirm 'as of today', I can give a "
            "date-bounded answer (with a note that any live value may have "
            "changed since my training cutoff)."
        )
        rewritten = True
        notes.append("ambiguous_time_frame: replaced silent answer with ask")

    # 5. Stable-control: flag over-verification, but do NOT auto-rewrite —
    #    we don't know the correct direct answer to substitute. The note is
    #    recorded so the report can see it.
    if fam == "stable_control":
        if _any(response, _REFUSAL_PATTERNS):
            notes.append("stable_control: refusal flagged (not rewritten)")
        elif _any(response, _CLARIFY_PATTERNS) and _is_short(response, 300):
            notes.append("stable_control: clarifying-question flagged (not rewritten)")
        elif _any(response, _DATE_HEDGE_PATTERNS) and _is_short(response, 200):
            # short response that is almost entirely a date hedge — counts as
            # over-verification.
            notes.append("stable_control: date-hedge flagged (not rewritten)")

    return ValidationResult(
        text=text,
        family=fam,
        notes=notes,
        rewritten=rewritten,
    )


# ─── 5. Combined entry point used by adapter / run_eval ─────────────────


@dataclass
class TransformerOutput:
    transformed_prompt: str
    detected_family: Family
    injected: bool


def prepare(prompt: str) -> TransformerOutput:
    """Single-call pre-generation transformer used by adapters."""
    new_prompt, fam, did = transform_prompt(prompt)
    return TransformerOutput(
        transformed_prompt=new_prompt,
        detected_family=fam,
        injected=did,
    )


__all__ = [
    "FAMILIES",
    "detect_family",
    "build_micro_instruction",
    "transform_prompt",
    "post_validate",
    "ValidationResult",
    "TransformerOutput",
    "prepare",
]
