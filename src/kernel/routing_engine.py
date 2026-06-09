from __future__ import annotations
import time as _time
import sys as _sys
import os as _os
from pathlib import Path as _Path

# ── Audit Log (Phase D) ───────────────────────────────────────────────────
_audit_dir = str(_Path(__file__).parent.parent / "audit")
if _audit_dir not in _sys.path:
    _sys.path.insert(0, _audit_dir)
try:
    from audit_emitter import AuditEmitter
    from audit_sampler import AuditSampler
    from audit_schema  import QKSnapshot, KVSScoreRecord, DecisionTrace, AUDIT_MODE_SHADOW
    from audit_store   import AuditStore
    _AUDIT_AVAILABLE = True
    _audit_mode    = _os.environ.get("MOBIUS_AUDIT_MODE", AUDIT_MODE_SHADOW)
    _audit_store   = AuditStore("logs")
    _audit_sampler = AuditSampler(audit_mode=_audit_mode)
    _audit_emitter = AuditEmitter(
        store=_audit_store, sampler=_audit_sampler, audit_mode=_audit_mode
    )
    _audit_emitter.open()
except ImportError:
    _AUDIT_AVAILABLE = False
    _audit_emitter   = None

# ── Memory Capsule (Phase E) ──────────────────────────────────────────────────
# Session-in-memory only: no disk load at startup, no disk save at exit.
# Capsules accumulate during the session and are searchable for prompt injection.
# This preserves audit/memory phase separation (audit=accountability, memory=continuity).
_memory_dir = str(_Path(__file__).parent.parent / "memory")
if _memory_dir not in _sys.path:
    _sys.path.insert(0, _memory_dir)
try:
    from memory_capsule import generate_capsule as _generate_capsule
    from memory_indexer  import MemoryIndexer   as _MemoryIndexer
    _MEMORY_AVAILABLE  = True
    _memory_indexer    = _MemoryIndexer()
    _memory_indexer.open()
    # Session-in-memory: no atexit disk persistence
except ImportError:
    _MEMORY_AVAILABLE  = False
    _memory_indexer    = None

from dataclasses import dataclass, field
from typing import List, Optional

from .appraisal import Appraiser, AppraisalState
from .dynamic_kvs import compute_dynamic_kvs
from .answer_shaping import select_answer_shape
from .language_policy import detect_language
from .route_decision import RouteDecision, select_route
from .trace_serializer import build_trace
from ..state.session_state import SessionState
from ..adapters.inference_adapter import AdapterResponse, InferenceAdapter, KernelRequest
from ..adapters.web_search_adapter import WebSearchAdapter
from ..retrieval.rag_pipeline import LocalRAGPipeline, RAGResult
from ..retrieval.retrieval_selector import choose_retrieval_plan
from ..retrieval.web_result_normalizer import normalize_search_response
from ..adjudication.evidence_adjudicator import adjudicate_evidence
from ..retrieval.query_reformulator import reformulate_query, ReformulatedQuery
from ..adapters.eal import TVS_HIGH_THRESHOLD
from ..compose.halfstep_composer import compose_halfstep, HalfStepType
from ..compose.response_composer import compose_non_answer_response
from ..compose.verify_synthesizer import synthesize_verify_response


import random as _random


def _select_halfstep_chain_type(
    appraisal: "AppraisalState",
    decision: "RouteDecision",
    memory_fit: object = None,
) -> str:
    """Select HalfStep chain_type from appraisal/decision context.

    Returns: "deepening" | "broadening" | "challenging"

    Phase E (optional): If a MemoryFitState is provided and indicates
    cold_start=True or a suppressive halfstep_policy, deepening is forced.
    When memory_fit is None (default), behavior is identical to pre-Phase-E
    (all existing tests still pass on the 2-arg signature).
    """
    # Phase E cold-start / over-leading guard (only when memory_fit passed).
    if memory_fit is not None:
        _cold = bool(getattr(memory_fit, "cold_start", False))
        _policy = getattr(memory_fit, "halfstep_policy", "")
        if _cold or _policy in ("deepening_only", "none_or_clarify", "standard_deepening"):
            return "deepening"

    # user_correction → challenging (前提を疑う)
    if getattr(appraisal, "user_correction", False):
        return "challenging"

    # self_referential → broadening (関連角度から展開)
    if getattr(appraisal, "self_referential", False):
        return "broadening"

    # Low intent_clarity or high uncertainty → challenging may help
    if (getattr(appraisal, "intent_clarity", 1.0) < 0.5
            and getattr(appraisal, "uncertainty", 0.0) > 0.6):
        return _random.choice(["deepening", "challenging"])

    # admissible_reframing_answer → broadening
    if getattr(decision, "answer_shape", None) == "admissible_reframing_answer":
        return "broadening"

    return "deepening"


# Phase G.9 — reason codes that suppress the generic reflective tail.
# These are contexts where a "why do you think so?" follow-up feels
# intrusive rather than enriching: stable-fact answers, definitional
# queries, evidence-grounded verify answers, continuity save-intent.
_TAIL_SUPPRESSION_REASON_CODES = frozenset({
    "LOW_STAKES_STABLE",
    "DEFINITIONAL_QUERY",
    "DEFINITIONAL_NEEDS_EVIDENCE",
    "WIKI_EVIDENCE",
    "CONTINUITY_INTENT_DETECTED",
})


def _should_suppress_reflective_tail(decision) -> bool:
    """Phase G.9 — True iff the current decision carries any reason
    code that marks the answer as technical / factual / verify-grounded
    / continuity-save, in which case the generic reflective tail
    directive is suppressed."""
    if decision is None:
        return False
    codes = getattr(decision, "reason_codes", None) or []
    return bool(set(codes) & _TAIL_SUPPRESSION_REASON_CODES)


def _halfstep_frame(halfstep_note: str, lang: str,
                    chain_type: str = "deepening",
                    *, decision=None) -> str:
    """Language-aware framing for HalfStep instruction.

    Args:
        halfstep_note: Content hint from compose_halfstep().
        lang: "ja" | "en" | "zh"
        chain_type: "deepening" | "broadening" | "challenging"
        decision: Optional RouteDecision. When provided and its reason
                  codes indicate a technical/factual/verify-grounded
                  context, the reflective-tail directive is suppressed
                  (Phase G.9). The `halfstep_note` itself (content hint
                  within the answer) is preserved.
    """
    # Phase G.9 — suppress the generic reflective tail for technical /
    # factual contexts. We still return the halfstep content hint so
    # the answer structure guidance is preserved; only the outer "ask
    # a follow-up question" directive is dropped.
    #
    # Phase G.10 — in addition to dropping the reflective prompt, emit
    # an explicit directive telling the model NOT to close with a
    # rhetorical question. This closes the residual "why...でしょうか？"
    # tails the model still adds on its own even when the prompt no
    # longer asks for one.
    if _should_suppress_reflective_tail(decision):
        _close_guard = {
            "ja": "回答を問いかけで締めないでください。",
            "en": "Do not end the response with a rhetorical question.",
            "zh": "不要以反问句结束回答。",
        }.get(lang, "Do not end the response with a rhetorical question.")
        if halfstep_note:
            # Preserve content hint; strip outer template; append guard.
            return f"{halfstep_note} {_close_guard}"
        return _close_guard
    _TEMPLATES = {
        "deepening": {
            "ja": "回答の後、この話題をさらに掘り下げる問いを一つだけ、自然に提示してください。「なぜ」「どのように」「何が」で始まる問いが望ましい。",
            "en": "After answering, pose one natural follow-up question that goes deeper into this topic. Prefer questions starting with 'why', 'how', or 'what'.",
            "zh": "回答后，自然地提出一个深入此话题的问题。优先使用「为什么」「如何」「什么」开头的问题。",
        },
        "broadening": {
            "ja": "回答の後、関連するが異なる角度からの問いを一つだけ、自然に提示してください。「では〜はどうか」「〜との関連は」のような展開が望ましい。",
            "en": "After answering, pose one natural question that explores a related but different angle. Prefer questions like 'what about...', 'how does this relate to...'.",
            "zh": "回答后，自然地提出一个从相关但不同角度探讨的问题。优先使用「那么…呢」「与…的关系」类型的问题。",
        },
        "challenging": {
            "ja": "回答の後、この問い自体の前提や枠組みを問い直す視点を一つだけ、自然に提示してください。「そもそも」「果たして」「本当に〜だろうか」のような構造が望ましい。",
            "en": "After answering, pose one natural question that challenges an assumption or reframes the premise. Prefer questions starting with 'but does...actually', 'is it really...', 'what if the premise...'.",
            "zh": "回答后，自然地提出一个质疑前提或重新审视框架的问题。优先使用「真的…吗」「其实…」类型的问题。",
        },
    }
    ct = chain_type if chain_type in _TEMPLATES else "deepening"
    lang_key = lang if lang in _TEMPLATES[ct] else "en"
    frame = _TEMPLATES[ct][lang_key]
    return f"{frame} {halfstep_note}"


# ── Stage 4 — response-layer helpers ─────────────────────────────────────────
# Kept compact and language-branched. Do NOT touch route taxonomy; these
# only shape the output text after the route has been decided.

_STAGE4_SAVE_ACK_BY_LANG: dict[str, str] = {
    "en": "Noted — I'll remember this. ",
    "ja": "記録しました — 覚えておきます。",
    "zh": "已记录 — 会记住的。",
}

_STAGE4_EMPTY_FALLBACK_BY_LANG: dict[str, str] = {
    "en": (
        "I wasn't able to produce a response for this query. "
        "Could you rephrase or share a bit more context so I can try again?"
    ),
    "ja": (
        "申し訳ありません、この質問に対する応答を作れませんでした。"
        "もう少し詳しく教えていただけますか？"
    ),
    "zh": (
        "抱歉，我暂时无法就此问题给出回答。"
        "请您换个说法或补充一些背景信息。"
    ),
}


def _stage4_save_ack_prefix(active_language: str) -> str:
    """Return a short, honest save-intent acknowledgement prefix.

    Language-branched. Exposed as a module-level pure function so the
    pattern strings remain inspectable and testable. Only applied when
    `appraisal.continuity_save_intent` is True (see _dispatch).
    """
    key = (active_language or "").lower()
    if key.startswith("ja"):
        return _STAGE4_SAVE_ACK_BY_LANG["ja"]
    if key.startswith("zh"):
        return _STAGE4_SAVE_ACK_BY_LANG["zh"]
    return _STAGE4_SAVE_ACK_BY_LANG["en"]


def _stage4_empty_fallback(active_language: str) -> str:
    """Return a bounded, honest fallback string for empty adapter output.

    Not synthetic content — explicitly states we couldn't produce a
    response and asks the user to rephrase. Only triggered when the
    real response text came back empty on an answer/verify path.
    """
    key = (active_language or "").lower()
    if key.startswith("ja"):
        return _STAGE4_EMPTY_FALLBACK_BY_LANG["ja"]
    if key.startswith("zh"):
        return _STAGE4_EMPTY_FALLBACK_BY_LANG["zh"]
    return _STAGE4_EMPTY_FALLBACK_BY_LANG["en"]


# ── Casual greeting detection (cyc_20260423_production_failure_deep_fix_2) ──
#
# Production symptom: first-turn chit-chat queries ("こんにちは",
# "今日は良い天気ですね") fall through to factual_query → Box W retrieval
# → Wikipedia content (Yorushika song about weather, history of the word
# こんにちは, etc.) leaks into the response.
#
# The existing CONV_OVERRIDE flag in appraisal.notes only fires when the
# PRIOR assistant turn contained game markers. It does not detect that
# the CURRENT user turn is itself a greeting, so first-turn greetings
# are unprotected. This helper fills that gap — it inspects the current
# user input only, so it's orthogonal to CONV_OVERRIDE.
#
# Detection rule: short query (≤ 20 chars) that matches one of the
# greeting/acknowledgement/pleasantry patterns below AND does not contain
# a question mark (?/？) followed by substantive content. Mixed queries
# like "こんにちは、Answer Entitlement とは？" retain the question and
# therefore do NOT match — they route normally.

import re as _re_greeting

_CASUAL_GREETING_PATTERNS = [
    # Japanese — time-of-day, thanks, farewells, social acknowledgements
    _re_greeting.compile(
        r"^\s*(こんにちは|こんばんは|おはよう(ございます)?|おやすみ(なさい)?|"
        r"ありがとう(ございます|ございました|ね)?|"
        r"どうも(ありがとう)?|"
        r"よろしく(お願いします|お願いいたします|ね)?|"
        r"はじめまして|初めまして|"
        r"さようなら|さよなら|またね|また明日|また今度|また後で|"
        r"お疲れ(様|さま)(です|でした)?|お元気ですか|元気ですか|"
        r"いただきます|ごちそうさま(でした)?|"
        r"おかえり(なさい)?|ただいま|"
        r"今日は(いい|良い|すごい|素晴らしい)(天気|日|一日)です?(ね|よ)?"
        r")[\s。！!~〜ー\.]*$"
    ),
    # English — greetings, thanks, farewells, pleasantries
    _re_greeting.compile(
        r"^\s*(hello|hi|hey|hiya|"
        r"good\s+(morning|afternoon|evening|night)|"
        r"thanks?(\s+(a\s+lot|so\s+much|very\s+much))?|"
        r"thank\s+you(\s+very\s+much)?|"
        r"thx|ty|cheers|"
        r"goodbye|bye|bye-bye|see\s+you(\s+(later|soon|tomorrow))?|"
        r"nice\s+to\s+meet\s+you|pleased\s+to\s+meet\s+you|"
        r"how\s+are\s+you(\s+doing)?|how's\s+it\s+going|"
        r"have\s+a\s+(nice|good|great)\s+(day|one|weekend)|"
        r"take\s+care"
        r")[\s\.!?~]*$",
        _re_greeting.IGNORECASE,
    ),
    # Chinese — greetings, thanks, farewells, pleasantries
    _re_greeting.compile(
        r"^\s*(你好|您好|大家好|"
        r"早上好|上午好|中午好|下午好|晚上好|晚安|"
        r"谢谢(你|您|大家)?|多谢|感谢|"
        r"再见|拜拜|回头见|明天见|"
        r"请多关照|请多指教|初次见面|"
        r"辛苦了|辛苦您了|"
        r"你最近怎么样|你好吗|最近好吗"
        r")[\s。！!~〜.]*$"
    ),
]


def _is_casual_greeting(query: str) -> bool:
    """Return True when `query` is a self-contained casual greeting or
    social pleasantry with no substantive question embedded.

    - Short query (≤ 20 characters after strip) is required as a first
      gate, so substantive queries that start with a greeting
      ("こんにちは、Answer Entitlement とは？") do not match.
    - Question marks (?/？) short-circuit to False even when under the
      length cap, so "お元気ですか？" is NOT treated as casual — it
      routes through the normal factual path and lets downstream
      logic decide. This is intentional: we want a very high-precision
      detector, not a high-recall one.
    """
    if not query:
        return False
    q = query.strip()
    if len(q) > 20:
        return False
    if "?" in q or "？" in q:
        return False
    for pat in _CASUAL_GREETING_PATTERNS:
        if pat.match(q):
            return True
    return False


def _casual_greeting_prompt(user_input: str, active_language: str) -> str:
    """Build a brief-acknowledgement prompt for casual_greeting intent.

    Instructs the model to respond warmly but briefly in the active
    language, without dumping factual / encyclopedic / self-reference
    content. Deliberately short and free of any retrieved grounding —
    this is the whole point of the casual_greeting branch.
    """
    key = (active_language or "").lower()
    if key.startswith("ja"):
        instruction = (
            "User から挨拶または社交的なやり取りが届きました。"
            "日本語で、短く自然に、一文〜二文で応答してください。"
            "Wikipedia 等の外部情報を持ち出さないでください。"
            "自己紹介や長い説明は不要です。"
        )
    elif key.startswith("zh"):
        instruction = (
            "用户发来的是问候或寒暄。"
            "请用中文简短自然地回应，一到两句话即可。"
            "不要引用维基百科等外部资料，也不需要长篇自我介绍。"
        )
    else:
        instruction = (
            "The user sent a greeting or short social pleasantry. "
            "Respond briefly and warmly in English, in one or two "
            "sentences. Do not bring in Wikipedia or other external "
            "content, and do not launch into a self-introduction or "
            "long explanation."
        )
    return f"User: {user_input}\n\n{instruction}"


# ── Box 0 persona-drift post-filter (cyc_20260423_production_failure_deep_fix_2) ─
#
# Production symptom: Box 0 retrieval for self-reference queries like
# "貴方の特徴を教えてください" returns top-3 chunks of which 1–2 are
# v8.2 add-on example JSON (medical_support_non_diagnostic "clinical
# note helper", K-12 learner feedback, chronic disease management
# adherence, etc.) rather than MOBIUS identity content. The LLM then
# drifts into counselor / clinician / tutor persona.
#
# Mitigation: retrieve a wider pool (top_k * 2), demote chunks that
# contain add-on-example markers by a factor of 0.5, and take the
# top_k after re-sort. Markers are specific to v8.2 add-on example
# JSON blocks; they do not appear in canonical identity sections.
#
# Demotion (not exclusion) means a legitimately relevant add-on chunk
# can still surface when no canonical chunk outranks it; it just
# doesn't beat canonical content on tied semantic similarity.

_PERSONA_MARKER_SUBSTRINGS = (
    # Add-on example JSON structural markers
    '"trigger_phrases"',
    '"Q3_longterm"',
    # medical_support_non_diagnostic example strings
    "clinical note helper",
    "diagnose and prescribe",
    "chronic disease management",
    "Encourage adherence",
    # K-12 tutoring example strings
    "K-12 learner",
    "learner repeated",
    "a bit hard, or very hard to follow",
    # Other persona-addon example markers
    "Q_meta_frame",
    "unhelpful meta-frames",
)

_PERSONA_DEMOTION_FACTOR = 0.5


def _looks_like_persona_addon_chunk(text: str) -> bool:
    """Return True when a Box 0 chunk appears to be a v8.2 persona /
    domain add-on example rather than canonical identity content.
    """
    if not text:
        return False
    for marker in _PERSONA_MARKER_SUBSTRINGS:
        if marker in text:
            return True
    return False


@dataclass
class RoutingResult:
    appraisal:     AppraisalState
    decision:      RouteDecision
    session_state: SessionState
    response_text: str = ""
    sources:       List[str] = field(default_factory=list)
    trace:         dict = field(default_factory=dict)

    # Phase G.8 — convenience accessors for real-path observability.
    @property
    def route(self) -> str:
        """Primary route name (delegates to decision.route)."""
        return getattr(self.decision, "route", "")

    @property
    def reason_code(self) -> str:
        """Primary reason code from the route decision. Empty string
        signals "no reason code recorded" — a diagnostic flag, not a
        valid default."""
        return getattr(self.decision, "reason_code", "")

    @property
    def reason_codes(self) -> List[str]:
        """Full list of reason codes recorded on the route decision."""
        return list(getattr(self.decision, "reason_codes", []) or [])


class RoutingEngine:
    """Möbius Kernel — routes, retrieves, composes, and logs every turn.

    Phase 2 additions over Phase 1:
    - Optional InferenceAdapter for answer / verify synthesis.
    - Optional LocalRAGPipeline for verify route.
    - SessionState is updated with route record and sources each turn.
    - Trace is built and attached to the result.
    """

    def __init__(
        self,
        adapter:            Optional[InferenceAdapter] = None,
        rag_pipeline:       Optional[LocalRAGPipeline] = None,
        web_search_adapter: Optional[WebSearchAdapter] = None,
        kiwix_adapter:      Optional[WebSearchAdapter] = None,
        box_0_adapter       = None,
        wiki_adapter        = None,
        box_a_manager       = None,
        # Phase G.11 — real Box B / Box C reserved document-slot backends. Optional;
        # when both are None, behavior is identical to pre-G.11. When
        # supplied, contribution is still gated by the active
        # AuthorityProfile's `reserved_boxes_allowed` flag, so the
        # balanced_default profile keeps B/C inert even with backends.
        box_b_manager       = None,
        box_c_manager       = None,
        # Stage 6 — Box X (curated external durable knowledge) store.
        # Bounded supplemental layer consulted only on technical /
        # reference-like queries when upstream Box W/A/0 produced no
        # sufficient evidence and the query is NOT freshness-sensitive.
        # When None or empty, behavior is identical to pre-Stage-6.
        # Disabled with MOBIUS_BOX_X=0.
        box_x_store         = None,
        verify_preset:      str = "general",
    ) -> None:
        self.appraiser          = Appraiser()
        self.adapter            = adapter
        self.rag_pipeline       = rag_pipeline
        self.web_search_adapter = web_search_adapter
        self.kiwix_adapter      = kiwix_adapter
        self.box_0_adapter      = box_0_adapter
        self.wiki_adapter       = wiki_adapter
        self.box_a_manager      = box_a_manager
        self.box_b_manager      = box_b_manager
        self.box_c_manager      = box_c_manager
        self.box_x_store        = box_x_store
        # Env override: MOBIUS_BOX_X=0 disables consultation regardless
        # of whether a store was injected.
        import os as _os_for_bx
        self._box_x_enabled = (
            _os_for_bx.environ.get("MOBIUS_BOX_X", "1").strip().lower()
            not in ("0", "false", "no", "off")
        )
        self.verify_preset      = verify_preset

        # ── Phase B Pattern Library (advisory only in Phase 1) ──────
        # Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 3.5 (Hybrid
        # Decision). When MOBIUS_PATTERN_LIBRARY=1 is set, each
        # evaluate() call runs the library lookup and trace_recorder
        # side-effectfully — the routing decision itself is untouched.
        # Default: OFF (zero overhead for the 33-scenario harness, unit
        # tests, and any caller that hasn't opted in). Tests and
        # production toggles can set the env var or attach the objects
        # directly to the instance after construction.
        self.pattern_library = None
        self.trace_recorder = None
        import os as _os_for_pl
        if _os_for_pl.environ.get(
            "MOBIUS_PATTERN_LIBRARY", "0",
        ).strip().lower() in ("1", "true", "yes", "on"):
            try:
                from pathlib import Path as _PLPath
                _repo_root = _PLPath(__file__).resolve().parent.parent.parent
                _idx = _repo_root / "data" / "pattern_library" / "index.faiss"
                _meta = _repo_root / "data" / "pattern_library" / "index_metadata.jsonl"
                _conf = _repo_root / "config" / "pattern_library"
                _thr = _conf / "thresholds.yaml"
                if _idx.exists() and _meta.exists() and _conf.exists():
                    from src.retrieval.pattern_lookup import PatternLibrary
                    self.pattern_library = PatternLibrary.from_disk(
                        _conf, _idx, _meta,
                        thresholds_path=_thr if _thr.exists() else None,
                    )
                    from src.kernel.trace_recorder import TraceRecorder
                    self.trace_recorder = TraceRecorder(
                        traces_dir=_repo_root / "data" / "pattern_library" / "traces",
                    )
            except Exception:
                # Advisory hook is fail-safe — swallow any setup error.
                self.pattern_library = None
                self.trace_recorder = None

        # ── Box M context processor (hybrid ambiguity resolution) ────
        self._context_processor = None
        try:
            if _MEMORY_AVAILABLE and _memory_indexer is not None:
                from src.memory.context_processor import ContextProcessor
                # Share ME5 model from wiki_adapter (Box W) if available
                _me5 = None
                if wiki_adapter and hasattr(wiki_adapter, '_model'):
                    _me5 = wiki_adapter._model
                if _me5 is not None:
                    self._context_processor = ContextProcessor(
                        memory_indexer=_memory_indexer,
                        me5_model=_me5,
                    )
                    self._context_processor.start()
        except Exception:
            self._context_processor = None

    # ── ISM intent heuristic (pre-ISMProfile fallback) ────────────────────────

    @staticmethod
    def _infer_intent_type(
        query: str, appraisal: "AppraisalState",
    ) -> str:
        """Lightweight intent detection until ISMProfile is available.

        Returns an ISM intent_type string. Branches in order:
          1. self_referential → meta_question  (Fix 1 / kanji self-ref
             priority — must outrank ism so kanji self-ref queries don't
             get reclassified as clarification / topic_continuation)
          2. casual greeting / social pleasantry → casual_greeting
             (cyc_20260423_production_failure_deep_fix_2; high-precision
             detector — placed before ism because ism misclassifies
             short non-English greetings like "谢谢" as
             topic_continuation, defeating the Box W skip fix)
          3. ISMProfile-assigned intent if present
          4. creative regex → creative_request
          5. default → factual_query

        Rationale: _is_casual_greeting is high-precision (length ≤ 20,
        no '?' / '？', strict pattern match per language) so placing it
        before ism does NOT risk swallowing substantive queries. The
        self-ref branch precedes it because the casual_greeting detector
        doesn't match self-ref queries (verified) and keeping self-ref
        first preserves Fix 1 semantics in the intent return value even
        when ism misclassifies.
        """
        if getattr(appraisal, "self_referential", False):
            return "meta_question"

        if _is_casual_greeting(query):
            return "casual_greeting"

        # If ISMProfile already classified, use that
        ism = getattr(appraisal, "ism", None)
        if ism is not None and hasattr(ism, "intent_type"):
            return ism.intent_type

        import re
        _CREATIVE_RE = re.compile(
            r"(?:もし.{1,20}(?:たら|なら|とき|場合))"  # hypothetical
            r"|(?:物語|ストーリー|小説|詩|歌詞|脚本).*(?:書|作|考|創)"
            r"|(?:書いて|作って|考えて|創って|描いて)"
            r"|(?:想像して|空想して|妄想して)"
            r"|(?:write\s+(?:a\s+)?(?:story|poem|tale|fable))",
            re.IGNORECASE,
        )
        if _CREATIVE_RE.search(query):
            return "creative_request"

        return "factual_query"

    # ── Phase B Pattern Library advisory hook ───────────────────────────────
    #
    # Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 3.5.
    # In Phase 1, library lookup is observed but does NOT alter the
    # routing decision — legacy regex / appraisal continues to drive
    # `evaluate()`. The hook records a trace per call so behavior can
    # be evaluated against the golden set and against real production
    # routing without any production-route risk.
    #
    # Fail-safe: any exception in the lookup or trace path is silently
    # swallowed — the advisory hook MUST NOT break routing.
    def _advisory_pattern_library_lookup(
        self, query: str, state,
    ) -> None:
        if not self.pattern_library:
            return
        try:
            from src.retrieval.pattern_lookup import (
                route_via_pattern_library,
            )
            decision = route_via_pattern_library(
                query, state, self.pattern_library,
            )

            # Phase 2 Commit 20 + Phase 3 Commit 30: primary mode framework.
            # Two opt-in env vars layered on top of the advisory hook:
            #   - MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF=1 → stamp
            #     state._pattern_library_primary only when the library
            #     returns a high-confidence match for self_reference
            #     (Phase 2 selective scope).
            #   - MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY=1 → stamp
            #     state._pattern_library_primary when the library
            #     returns a high-confidence match for ANY of the 6
            #     supported topics (Phase 3 full scope). Takes
            #     precedence over the selective var when both are set.
            # The metadata is consumed downstream; the legacy regex /
            # appraisal path remains a parallel evaluator for trace
            # observation. Default OFF — production opt-in per
            # deployment.
            import os as _os_for_pl
            selective_enabled = _os_for_pl.environ.get(
                "MOBIUS_PATTERN_LIBRARY_PRIMARY_SELF_REF", "0",
            ).strip().lower() in ("1", "true", "yes", "on")
            full_enabled = _os_for_pl.environ.get(
                "MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY", "0",
            ).strip().lower() in ("1", "true", "yes", "on")
            any_primary_enabled = selective_enabled or full_enabled

            primary_used = False
            primary_mode = None  # 'full' | 'selective' | None
            if decision is not None and decision.confidence == "high":
                if full_enabled:
                    primary_used = True
                    primary_mode = "full"
                elif (selective_enabled
                      and decision.pattern.topic == "self_reference"):
                    primary_used = True
                    primary_mode = "selective"

            if primary_used:
                state._pattern_library_primary = {
                    "pattern_id": decision.pattern.id,
                    "score": decision.score,
                    "topic": decision.pattern.topic,
                    "intent": decision.pattern.intent,
                    "primary_box": decision.pattern.route.primary_box,
                    "exclude_boxes": list(
                        decision.pattern.route.exclude_boxes or []
                    ),
                    "synthesis_mode": decision.pattern.route.synthesis_mode,
                    "mode": primary_mode,
                }

            if self.trace_recorder is not None:
                lib_lookup = {}
                if decision is not None:
                    lib_lookup = {
                        "matched_pattern_id": decision.pattern.id,
                        "match_score": decision.score,
                        "confidence": decision.confidence,
                        "warning": decision.warning,
                        "topic": decision.pattern.topic,
                    }
                hybrid_selected = (
                    "library" if primary_used else "legacy"
                )
                if primary_used:
                    hybrid_reason = (
                        f"full_primary_{decision.pattern.topic}"
                        if primary_mode == "full"
                        else "selective_primary_self_ref"
                    )
                elif not any_primary_enabled:
                    hybrid_reason = "advisory_only"
                else:
                    hybrid_reason = "low_confidence_or_other_topic"
                self.trace_recorder.record(
                    query=query,
                    library_lookup=lib_lookup,
                    legacy_routing={"selected": "legacy",
                                     "reasoning": "regex_appraisal"},
                    hybrid_decision={"selected": hybrid_selected,
                                      "reasoning": hybrid_reason},
                )
        except Exception:
            return

    # ── Box 0 filtered retrieval (L8 persona-drift mitigation) ───────────────
    #
    # Wraps `box_0_adapter.retrieve(query, top_k)` with a post-retrieval
    # demotion filter that down-weights chunks carrying v8.2 add-on
    # example markers (see `_looks_like_persona_addon_chunk`). Widens the
    # underlying retrieve to top_k * 2 so canonical identity chunks have
    # a real chance of rising to the top_k after demotion.
    #
    # Returns the (possibly reconstructed) RetrievalResult, or None when
    # the adapter is unavailable or the retrieve itself errored. The
    # caller handles None identically to "no sources" from the raw
    # adapter — the filter is a drop-in replacement for the previous
    # direct `.retrieve()` call.
    def _retrieve_box_0_filtered(
        self,
        query: str,
        top_k: int = 3,
    ):
        """Retrieve from Box 0 with persona-addon demotion.

        This is a narrow, self-contained helper to keep the two call
        sites (_prepare_answer_stream and _handle_answer) identical —
        both short-circuit on self_referential=True and the filtering
        needs to stay in lockstep between the streaming and non-
        streaming paths.
        """
        if self.box_0_adapter is None:
            return None
        try:
            wide_k = max(top_k, top_k * 2)
            raw = self.box_0_adapter.retrieve(query, top_k=wide_k)
        except Exception:
            return None
        if not raw.sources:
            return raw

        # Raw.synthesis is "\n\n".join of the per-source chunk texts, in
        # the same order as raw.sources. Rebuild source+text pairs so we
        # can apply demotion and then resort jointly.
        texts = raw.synthesis.split("\n\n") if raw.synthesis else []
        # Defensive: if the join shape was altered elsewhere, do not try
        # to reorder — return raw unchanged to preserve legacy behavior.
        if len(texts) != len(raw.sources):
            return raw

        pairs = []
        for src, txt in zip(raw.sources, texts):
            base_score = src.relevance_score or 0.0
            if _looks_like_persona_addon_chunk(txt):
                effective = base_score * _PERSONA_DEMOTION_FACTOR
                demoted = True
            else:
                effective = base_score
                demoted = False
            pairs.append((effective, src, txt, demoted))

        # Stable sort by effective score, descending. Ties preserve
        # original order (which preserves FAISS order within ties).
        pairs.sort(key=lambda p: p[0], reverse=True)
        kept = pairs[:top_k]

        # Reconstruct a result-shaped object using the existing
        # RetrievalResult type from the adapter that returned raw. That
        # type is duck-type compatible across CustomRagAdapter and
        # WikiAdapter (dataclass with .sources, .outcome, .synthesis).
        result_cls = raw.__class__
        new_sources = [p[1] for p in kept]
        new_texts = [p[2] for p in kept]
        # outcome reuses raw.outcome semantics: success if we filled top_k
        outcome = "success" if len(new_sources) >= top_k else (
            "partial" if new_sources else "failed"
        )
        return result_cls(
            sources   = new_sources,
            outcome   = outcome,
            synthesis = "\n\n".join(new_texts),
        )

    # ── Stage 6 — Box X (curated external durable knowledge) ────────────────
    #
    # Bounded supplemental consultation. Activates only when:
    #   - a Box X store is wired AND non-empty
    #   - MOBIUS_BOX_X is enabled
    #   - the query is technical / reference-like, OR caller flags
    #     reference_intent / technical_hint
    #   - the query is NOT freshness-sensitive
    # Box X CANNOT override Box W/A/0 results that were already
    # sufficient; callers must invoke this only after upstream stages
    # produced no usable evidence.

    def _box_x_consult(
        self,
        *,
        query: str,
        appraisal: AppraisalState,
        state: SessionState,
        top_k: int = 3,
    ) -> Optional[dict]:
        """Run a single bounded Box X consultation.

        Returns a dict shaped like
            {"hit": bool, "reason": str, "hits": [...], "notes": [...]}
        or None when consultation was suppressed (env disabled, no store,
        freshness-sensitive). Pure with respect to Box X store; never
        raises.
        """
        if not self._box_x_enabled or self.box_x_store is None:
            return None
        # Freshness-sensitive queries must reach Box S / verify path.
        if getattr(appraisal, "freshness_sensitive", False):
            return None
        # Optional caller hints from appraisal notes.
        technical_hint = False
        reference_intent = False
        try:
            notes = list(getattr(appraisal, "notes", []) or [])
        except Exception:
            notes = []
        if "TECHNICAL_QUERY" in notes or "REFERENCE_INTENT" in notes:
            technical_hint = True
        try:
            from ..retrieval.box_x_consultation import consult_box_x
        except Exception:
            return None
        try:
            out = consult_box_x(
                query=query,
                store=self.box_x_store,
                top_k=top_k,
                reference_intent=reference_intent,
                technical_hint=technical_hint,
            )
        except Exception:
            return None
        record = {
            "consulted":    bool(out.consulted),
            "hit":          bool(out.has_hit()),
            "reason":       out.reason,
            "hits":         list(out.hits),
            "notes":        list(out.notes),
        }
        # Stash for trace serialization.
        try:
            state._last_box_x = record
        except Exception:
            pass
        return record

    @staticmethod
    def _box_x_evidence_block(record: dict, max_chars: int = 1500) -> str:
        """Build a compact terminology-hint block from Box X consultation
        hits. Stage 9 polish: hints are phrased as neutral, trailing
        notes (not a "reference block") so the answering model keeps
        its natural voice. Still includes title + domain + canonical
        terms + source_uri for inspectability and trace.
        """
        if not record or not record.get("hits"):
            return ""
        lines: list[str] = []
        for hit in record["hits"]:
            title = hit.get("title", "(untitled)")
            domain = hit.get("domain", "")
            terms = hit.get("canonical_terms") or []
            uri = hit.get("source_uri", "")
            head = f"- {title}"
            if domain:
                head += f" (domain: {domain})"
            if terms:
                head += f" — canonical: {', '.join(terms)}"
            if uri:
                head += f" [source: {uri}]"
            lines.append(head)
        joined = "\n".join(lines)
        return joined[:max_chars]

    # ── Box M: session memory retrieval ──────────────────────────────────────

    @staticmethod
    def _retrieve_memory_context(query: str, top_k: int = 2) -> str:
        """Search session memory capsules for relevant context.

        Returns a formatted context string, or empty string if nothing found.
        """
        if not _MEMORY_AVAILABLE or _memory_indexer is None:
            return ""
        try:
            if _memory_indexer.count() == 0:
                return ""
            hits = _memory_indexer.search(query, top_k=top_k, min_salience=0.3)
            if not hits:
                return ""
            lines = []
            for h in hits:
                text = h.get("memory_text", "")
                if text:
                    lines.append(f"[Session memory] {text}")
            return "\n".join(lines)
        except Exception:
            return ""

    # ── Box B / C: Phase G.11 reserved document-slot retrieval ───────────────

    def _search_box_bc(self, query: str, state) -> tuple:
        """Phase G.11 — combined Box B / Box C reserved-slot retrieval.

        Returns (context, hits) where:
          - context: newline-joined top snippets prefixed with [Box B]/[Box C]
          - hits: list of {box, text, score, doc_id, filename} for trace.

        Governance rules (ALL must be True for B or C to contribute):
          - the manager exists on this engine (box_b_manager / box_c_manager)
          - the manager has active documents (no fake content on empty stores)
          - the active AuthorityProfile's `reserved_boxes_allowed` is True
            (balanced_default profile keeps B/C inert; wide_recall enables)
        """
        # Resolve the active authority profile. Missing → treat as no B/C.
        try:
            from .profiles import get_authority_profile
            _auth_id = getattr(state, "selected_authority_profile_id", "") or ""
            _eff_id = getattr(state, "effective_authority_profile_id", "") or _auth_id
            _auth = get_authority_profile(_eff_id or _auth_id or None)
        except Exception:   # noqa: BLE001
            return "", []
        if not getattr(_auth, "reserved_boxes_allowed", False):
            return "", []

        hits: list = []
        context_parts: list = []
        for label, mgr in (("B", self.box_b_manager),
                            ("C", self.box_c_manager)):
            if mgr is None:
                continue
            try:
                if not mgr.has_active_documents():
                    continue
                results = mgr.search(query, top_k=2)
            except Exception:   # noqa: BLE001
                continue
            for r in results:
                hits.append({
                    "box": label,
                    "text": r.get("text", ""),
                    "score": r.get("score", 0.0),
                    "doc_id": r.get("doc_id", ""),
                    "filename": r.get("filename", ""),
                })
                snippet = (r.get("text") or "")[:400]
                if snippet:
                    context_parts.append(
                        f"[User workspace Box {label}] {snippet}"
                    )
        return "\n\n".join(context_parts), hits

    # ── Box A: governance document retrieval & mode detection ─────────────────

    def _search_box_a(self, query: str) -> tuple:
        """Search Box A for governance documents.
        Returns (context_str, mode, results, few_shot) or (None, None, [], "").
        """
        if self.box_a_manager is None or not self.box_a_manager.has_active_documents():
            return None, None, [], ""

        results = self.box_a_manager.search(query, top_k=3)
        if not results or results[0]["score"] < 0.35:
            return None, None, results, ""

        context = "\n".join([r["text"] for r in results[:2]])
        mode = self._determine_box_a_mode(query, context)

        few_shot = ""
        if mode == "RULE" and self.adapter is not None:
            few_shot = self._generate_box_a_few_shot(context, query)

        return context, mode, results, few_shot

    def _determine_box_a_mode(self, query: str, context: str) -> str:
        """Use LLM to determine how Box A document should be used."""
        if self.adapter is None:
            return "REFERENCE"

        prompt = (
            "Given this user query and document excerpt, determine how "
            "the document should be used. Answer with exactly one word.\n\n"
            "RULE — The document contains rules, game rules, procedures, or behavioral "
            "instructions that the AI must FOLLOW (act according to), not just describe.\n"
            "REFERENCE — The document contains facts, data, or information to CITE in the answer.\n"
            "TEMPLATE — The document contains a format or structure to USE as output format.\n"
            "CRITERIA — The document contains standards or thresholds to APPLY for judgment.\n\n"
            f"Query: {query}\n"
            f"Document excerpt: {context[:400]}\n\n"
            "Answer (one word):"
        )
        try:
            req = KernelRequest(user_input=query, prompt=prompt)
            resp = self.adapter.generate(req)
            mode = (resp.text or "").strip().upper().split()[0] if resp.text else "REFERENCE"
            if mode not in ("RULE", "REFERENCE", "TEMPLATE", "CRITERIA"):
                mode = "REFERENCE"
            return mode
        except Exception:
            return "REFERENCE"

    def _generate_box_a_few_shot(self, context: str, query: str) -> str:
        """Generate few-shot behavioral examples for RULE mode."""
        if self.adapter is None:
            return ""
        prompt = (
            f"Based on these rules, generate exactly 2 example exchanges "
            f"showing correct behavior (NOT rule explanation).\n\n"
            f"Rules:\n{context[:500]}\n\n"
            f"Format each example as:\n"
            f"User: [example input]\n"
            f"AI: [correct response following the rules]\n\n"
            f"Keep responses SHORT — the AI response should demonstrate rule-following "
            f"behavior, not rule description. Generate examples now:"
        )
        try:
            req = KernelRequest(user_input=query, prompt=prompt)
            resp = self.adapter.generate(req)
            return (resp.text or "").strip()
        except Exception:
            return ""

    def _check_box_a_compliance(self, context: str, response: str,
                                mode: str) -> tuple:
        """Check if response complies with Box A rules/criteria.
        Returns (is_compliant: bool, corrected_text: str).
        """
        if self.adapter is None or mode not in ("RULE", "CRITERIA"):
            return True, response

        if mode == "RULE":
            check_prompt = (
                f"You are reviewing an AI response for rule compliance.\n\n"
                f"RULES the AI was supposed to follow:\n{context[:500]}\n\n"
                f"AI's response:\n{response}\n\n"
                f"Question: Did the AI FOLLOW the rules (act according to them), "
                f"or did it merely DESCRIBE/CITE them?\n\n"
                f"If the AI followed the rules correctly, respond: COMPLIANT\n"
                f"If the AI described rules instead of following them, respond: VIOLATION\n"
                f"Then on the next line, write the corrected response that follows the rules.\n\n"
                f"Answer:"
            )
        else:  # CRITERIA
            check_prompt = (
                f"You are reviewing an AI response.\n"
                f"The user asked a question that should be judged against specific criteria.\n\n"
                f"CRITERIA:\n{context[:500]}\n\n"
                f"AI's response:\n{response}\n\n"
                f"Did the AI APPLY the criteria to reach a conclusion, "
                f"or did it merely DESCRIBE the criteria?\n\n"
                f"If applied correctly: COMPLIANT\n"
                f"If only described: VIOLATION — rewrite with conclusion first, then reasoning.\n\n"
                f"Answer:"
            )

        try:
            req = KernelRequest(user_input="compliance_check", prompt=check_prompt)
            resp = self.adapter.generate(req)
            result_text = (resp.text or "").strip()

            if "VIOLATION" in result_text:
                lines = result_text.split("\n", 1)
                corrected = lines[1].strip() if len(lines) > 1 else response
                return False, corrected
            return True, response
        except Exception:
            return True, response

    # ── Main entry point ─────────────────────────────────────────────────────

    def evaluate(
        self,
        user_input:    str,
        session_state: Optional[SessionState] = None,
        *,
        profile_override: Optional[object] = None,
    ) -> RoutingResult:
        """
        Main entry point.

        Phase G.3: `profile_override` is an optional per-call
        `ProfileOverrideRequest` (internal). When supplied, its valid IDs
        take precedence over `session_state.selected_*` for this single
        call WITHOUT mutating SessionState. Invalid overrides fall back
        safely and are recorded in `state.profile_selection_notes`. The
        default `None` means "no override" → session selection is used.
        This scaffold exists for future UI / API surfaces; no public
        endpoint is added in this pass.
        """

        state = session_state or SessionState()
        # Phase G.3: stash per-call override on state (private attr) so the
        # decision-layer helper can read it without altering its signature.
        # Cleared on every evaluate() invocation; never persisted across turns.
        state._phase_g3_override_request = profile_override
        _t_start = _time.time()  # Audit フック1 (Phase D)
        if _AUDIT_AVAILABLE and _audit_emitter:
            _audit_emitter.start_session(getattr(state, "session_id", "unknown"))

        # 1. Language detection (kernel responsibility, B-lite)
        state.active_language = detect_language(
            user_input, previous_language=state.active_language
        )

        # 1a. Phase B Pattern Library advisory hook (no-op when library
        #     not configured). Spec 3.5 advisory mode: trace recorded
        #     side-effectfully, routing decision unchanged.
        self._advisory_pattern_library_lookup(user_input, state)

        # 1b. Phase F v2: feed the user turn into UserMap so cold_start
        # decays naturally on the normal governed path. Captures explicit
        # cues (concise/detailed/gentle/…), themes, abstraction baseline,
        # and frame-adoption relative to the prior assistant turn.
        try:
            from src.memory.user_map import observe_user_turn as _observe_um
            _prev_assistant_frame = ""
            _prior_turns_for_frame = getattr(state, "conversation_turns", []) or []
            for _pt in reversed(_prior_turns_for_frame):
                if isinstance(_pt, dict) and _pt.get("role") == "assistant":
                    _prev_assistant_frame = (_pt.get("content", "") or "")[:400]
                    break
            _um_obs = state.ensure_user_map()
            _observe_um(
                _um_obs, user_input,
                assistant_previous_frame=_prev_assistant_frame or None,
                turn_fit_score=None,
            )
        except Exception:
            pass

        # 2. Appraisal (with Box M context for ambiguity resolution)
        model_name = getattr(self.adapter, 'model_name', 'phi4-mini:latest')
        _prev_assistant = ""
        _prev_user = ""
        if state.conversation_turns:
            for _turn in reversed(state.conversation_turns):
                if _turn.get("role") == "assistant" and not _prev_assistant:
                    _prev_assistant = _turn.get("content", "")
                elif _turn.get("role") == "user" and not _prev_user:
                    _prev_user = _turn.get("content", "")
                if _prev_assistant and _prev_user:
                    break

        # Box M context search (for hybrid ambiguity resolution)
        _box_m_context = []
        if hasattr(self, '_context_processor') and self._context_processor is not None:
            try:
                _box_m_context = self._context_processor.search_context(
                    user_input, top_k=3,
                )
            except Exception:
                pass

        _meta = {}
        if _prev_assistant:
            _meta["prev_assistant"] = _prev_assistant
        if _prev_user:
            _meta["prev_user"] = _prev_user
        if _box_m_context:
            _meta["box_m_context"] = _box_m_context

        # cyc_20260426_c2_context_aware_self_ref (Phase 2 Commit 12):
        # Pass the last 3 user-side queries so the appraiser can detect
        # context-dependent self-ref (bare aspect-question after a
        # self-ref turn). Empty list when no prior turns exist.
        _recent_user: list[str] = []
        for _t in reversed(state.conversation_turns or []):
            if isinstance(_t, dict) and _t.get("role") == "user":
                _recent_user.append(_t.get("content", "") or "")
                if len(_recent_user) >= 3:
                    break
        if _recent_user:
            _meta["recent_user_queries"] = _recent_user

        appraisal = self.appraiser.evaluate(
            user_input, model_name=model_name,
            metadata=_meta if _meta else None,
        )

        # 3. Route decision
        decision = select_route(appraisal, query=user_input)
        if decision.route == "answer":
            decision.answer_shape = select_answer_shape(appraisal)

        # Phase 3 Stab Commit 44 — full primary mode downstream consumer.
        # The advisory hook (step 1a above) stamps state._pattern_library_primary
        # when MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY=1 + library returns a
        # high-confidence match for any of the 6 topics. Here we read that
        # metadata and (a) record a reason_code for trace observability,
        # (b) set a hint flag that downstream Box 0 retrieval consults
        # alongside `appraisal.self_referential` — covering legacy regex
        # blind spots when the library identifies a query as self-ref-like
        # but the appraiser did not. Selective primary (mode="selective")
        # is unchanged from Phase 2 framework behavior.
        try:
            primary_meta = getattr(state, "_pattern_library_primary", None)
            if primary_meta and primary_meta.get("mode") == "full":
                topic = (primary_meta.get("topic") or "unknown").upper()
                decision.reason_codes.append(f"FULL_PRIMARY_LIBRARY_{topic}")
                if primary_meta.get("primary_box") == "box_0":
                    state._library_primary_box_0_hint = True
                if primary_meta.get("synthesis_mode"):
                    decision.reason_codes.append(
                        f"FULL_PRIMARY_SYNTH_"
                        f"{primary_meta['synthesis_mode'].upper()}"
                    )
        except Exception:
            pass  # consumer is fail-safe; never block routing

        # 4. Dispatch to route handler
        response_text, sources, verify_outcome = self._dispatch(
            user_input, decision, appraisal, state
        )

        # 4b. Record turns in Box M Layer 0 (for context processor)
        if _MEMORY_AVAILABLE and _memory_indexer is not None:
            try:
                _sid = getattr(state, "session_id", "")
                _memory_indexer.add_turn(user_input, "user", _sid)
                if response_text:
                    _memory_indexer.add_turn(response_text[:500], "assistant", _sid)
            except Exception:
                pass

        # 5. Record in SessionState
        state.record_route({
            "route":          decision.route,
            "reason_codes":   decision.reason_codes,
            "answer_shape":   decision.answer_shape,
            "verify_outcome": verify_outcome,
            "sources":        sources,
            "confidence_posture": decision.confidence_posture,
        })

        # 6. Build trace (include EAL detail if verify path was taken)
        eal_detail = getattr(state, "_last_eal", None)
        box_a_detail = getattr(state, "_last_box_a", None)
        box_x_detail = getattr(state, "_last_box_x", None)
        trace = build_trace(
            route=decision.route,
            reason_codes=decision.reason_codes,
            verify_outcome=verify_outcome,
            sources=sources,
            active_language=state.active_language,
            explanation=response_text,
            eal_detail=eal_detail,
            phi_t=getattr(state, '_last_rgc_phi', None),
            rgc_band=getattr(state, '_last_rgc_band', None),
            rgc_pi=getattr(state, '_last_rgc_pi', None),
            box_a_detail=box_a_detail,
            box_x_detail=box_x_detail,
        )
        # Clear ephemeral EAL state
        if hasattr(state, "_last_eal"):
            del state._last_eal
        if hasattr(state, "_last_box_x"):
            del state._last_box_x

        # ── Audit フック2: emit (Phase D) ───────────────────────────────
        if _AUDIT_AVAILABLE and _audit_emitter:
            _t_total = int((_time.time() - _t_start) * 1000)
            _sess_id = getattr(state, "session_id", "unknown")
            _turn    = len(getattr(state, "route_history", [])) or 0
            _phi_t   = getattr(state, "_last_rgc_phi", 0.0) or 0.0
            _clamped = any(c in decision.reason_codes
                           for c in ("SAFETY_CRITICAL","POLICY_VIOLATION","VREGEN_UNSTABLE"))
            _tid = _audit_emitter.emit_minimum_header(
                session_id=_sess_id, turn=_turn, route_decision=decision.route)
            _qk = QKSnapshot.from_appraisal(
                intent_clarity=appraisal.intent_clarity,
                uncertainty=appraisal.uncertainty,
                freshness_sensitive=appraisal.freshness_sensitive,
                safety_relevant=appraisal.safety_relevant)
            _dt = DecisionTrace(
                primary_reason=decision.reason_codes[0] if decision.reason_codes else "",
                primary_seat="kernel", notes=list(decision.reason_codes))
            _kvs = KVSScoreRecord(
                tvs=0.8 if appraisal.freshness_sensitive else 0.2,
                mkr=0.5, computed=False)
            _eal  = getattr(state, "_last_eal", None)
            _eal_adm = _eal.get("Admissibility","") if _eal else ""
            _ret_src = ("C" if appraisal.freshness_sensitive else "B") if sources else ""
            _audit_emitter.emit_turn_record(
                session_id=_sess_id, turn=_turn, route_decision=decision.route,
                user_input=user_input, output_text=response_text,
                clamped=_clamped,
                clamp_reasons=[r for r in decision.reason_codes
                               if r in ("SAFETY_CRITICAL","POLICY_VIOLATION")],
                reason_codes=list(decision.reason_codes),
                oracle_used=self.adapter is not None,
                total_ms=_t_total, qk=_qk, decision_trace=_dt, kvs=_kvs,
                eal_admissibility=_eal_adm, retrieval_source=_ret_src,
                phi_t=_phi_t, turn_id=_tid)

        # ── Memory Capsule フック (Phase E) ─────────────────────────────
        if _MEMORY_AVAILABLE and _memory_indexer and _AUDIT_AVAILABLE:
            try:
                _capsule = _generate_capsule(
                    audit           = type("_A", (), {
                        "turn_id":           _tid or "",
                        "session_id":        getattr(state, "session_id", "unknown"),
                        "turn":              len(getattr(state, "route_history", [])) or 0,
                        "route_decision":    decision.route,
                        "clamped":           _clamped,
                        "clamp_reasons":     [r for r in decision.reason_codes
                                              if r in ("SAFETY_CRITICAL","POLICY_VIOLATION")],
                        "reason_codes":      list(decision.reason_codes),
                        "qk":                _qk,
                        "decision_trace":    _dt,
                        "kvs":               _kvs,
                        "eal_admissibility": _eal_adm,
                        "retrieval_source":  _ret_src,
                    })(),
                    response_summary = response_text[:200] if response_text else "",
                )
                if _capsule:
                    _memory_indexer.add(_capsule)
            except Exception as _mem_exc:
                import logging as _log
                _log.getLogger(__name__).warning(
                    f"[MemoryCapsule] generation failed: {_mem_exc}"
                )

        return RoutingResult(
            appraisal=appraisal,
            decision=decision,
            session_state=state,
            response_text=response_text,
            sources=sources,
            trace=trace,
        )

    # ── Streaming evaluation ────────────────────────────────────────────────

    def evaluate_stream(
        self,
        user_input: str,
        session_state=None,
    ):
        """Streaming version of evaluate().

        Evidence retrieval and EAL adjudication run synchronously,
        then the final LLM generation is streamed token-by-token
        via adapter.generate_stream().
        Yields str tokens. After completion, stores RoutingResult
        on state._last_eval_result for UI trace display.
        """
        state = session_state or SessionState()
        state.active_language = detect_language(
            user_input, previous_language=state.active_language)

        model_name = getattr(self.adapter, 'model_name', 'phi4-mini:latest')
        _prev = ""
        if state.conversation_turns:
            for t in reversed(state.conversation_turns):
                if t.get("role") == "assistant":
                    _prev = t.get("content", "")
                    break

        appraisal = self.appraiser.evaluate(
            user_input, model_name=model_name,
            metadata={"prev_assistant": _prev} if _prev else None,
        )
        decision = select_route(appraisal, query=user_input)
        if decision.route == "answer":
            decision.answer_shape = select_answer_shape(appraisal)

        # For non-answer/verify routes, yield static response
        if decision.route in ("ask", "abstain"):
            text = compose_non_answer_response(decision, state.active_language)
            yield text
            return

        # ── Phase 1: EAL evidence retrieval + prompt build (sync) ────────
        sources: List[str] = []
        verify_outcome: Optional[str] = None
        prompt: Optional[str] = None
        fallback_text: Optional[str] = None

        if decision.route == "answer":
            prompt, fallback_text, sources = self._prepare_answer_stream(
                user_input, decision, appraisal, state
            )

        if decision.route == "verify" or prompt is None:
            # verify route, or answer escalated to verify (wiki_escalate)
            vctx = self._prepare_verify_stream(
                user_input, appraisal, state
            )
            prompt = vctx["prompt"]
            fallback_text = vctx.get("fallback_text")
            sources = vctx.get("sources", [])
            verify_outcome = vctx.get("verify_outcome")

        # ── Phase 2: Stream final LLM generation ────────────────────────
        full_text = ""
        if prompt and self.adapter and hasattr(self.adapter, 'generate_stream'):
            req = KernelRequest(user_input=user_input, prompt=prompt)
            audit: dict = {}
            for token in self.adapter.generate_stream(req, audit):
                full_text += token
                yield token
        elif prompt and self.adapter:
            req = KernelRequest(user_input=user_input, prompt=prompt)
            resp = self.adapter.generate(req)
            full_text = resp.text
            yield full_text
        elif fallback_text:
            full_text = fallback_text
            yield fallback_text
        else:
            full_text = compose_non_answer_response(decision, state.active_language)
            yield full_text

        # ── Phase 3: Post-stream V_regen guard (answer route only) ───────
        if (
            decision.route == "answer"
            and "KVS_PASS" in " ".join(decision.reason_codes)
            and self.adapter is not None
            and full_text
        ):
            dkvs = compute_dynamic_kvs(
                query=user_input,
                model_name=getattr(self.adapter, 'model_name', 'phi4-mini:latest'),
                original_answer=full_text,
                adapter=self.adapter,
                rgc_state=state.rgc_state,
            )
            if dkvs.rgc is not None:
                state._last_rgc_phi  = dkvs.rgc.phi_next
                state._last_rgc_band = dkvs.rgc.band
                state._last_rgc_pi   = dkvs.pi_total
            if dkvs.rgc is not None and dkvs.rgc.band == "verify":
                decision.reason_codes.append("RGC_BAND_ESCALATE_VERIFY")
            elif dkvs.vregen.triggered and not dkvs.vregen.stable:
                decision.reason_codes.append("RGC_ESCALATE_VERIFY")
                decision.reason_codes.append("VREGEN_UNSTABLE")
            elif dkvs.vregen.triggered:
                decision.reason_codes.append("VREGEN_STABLE")

        # ── Phase 4: Record, trace, store result ─────────────────────────
        state.record_route({
            "route":          decision.route,
            "reason_codes":   decision.reason_codes,
            "answer_shape":   decision.answer_shape,
            "verify_outcome": verify_outcome,
            "sources":        sources,
            "confidence_posture": decision.confidence_posture,
        })

        eal_detail = getattr(state, "_last_eal", None)
        box_x_detail = getattr(state, "_last_box_x", None)
        trace = build_trace(
            route=decision.route,
            reason_codes=decision.reason_codes,
            verify_outcome=verify_outcome,
            sources=sources,
            active_language=state.active_language,
            explanation=full_text,
            eal_detail=eal_detail,
            phi_t=getattr(state, '_last_rgc_phi', None),
            rgc_band=getattr(state, '_last_rgc_band', None),
            rgc_pi=getattr(state, '_last_rgc_pi', None),
            box_x_detail=box_x_detail,
        )
        if hasattr(state, "_last_eal"):
            del state._last_eal
        if hasattr(state, "_last_box_x"):
            del state._last_box_x

        state._last_eval_result = RoutingResult(
            appraisal=appraisal,
            decision=decision,
            session_state=state,
            response_text=full_text,
            sources=sources,
            trace=trace,
        )

    # ── Stream helpers (evidence retrieval + prompt build) ──────────────

    def _prepare_answer_stream(
        self,
        user_input: str,
        decision:   RouteDecision,
        appraisal:  AppraisalState,
        state:      SessionState,
    ):
        """Gather evidence and build prompt for answer-route streaming.

        Returns (prompt, fallback_text, sources).
        prompt=None signals wiki_escalate → caller should fall through to verify.
        """
        is_self_ref = getattr(appraisal, "self_referential", False)
        # Phase 3 Stab Commit 44: full primary mode hint from library
        # metadata stamp. When MOBIUS_PATTERN_LIBRARY_FULL_PRIMARY=1 and
        # the library returned a high-confidence box_0 primary, treat as
        # self-ref-equivalent for Box 0 retrieval purposes.
        library_box_0_hint = bool(
            getattr(state, "_library_primary_box_0_hint", False)
        )
        should_retrieve_box_0 = is_self_ref or library_box_0_hint
        sources: List[str] = []

        # ── Intent (early: determines casual_greeting fast path) ─────────
        # cyc_20260423_production_failure_deep_fix_2: first-turn chit-chat
        # leaked Wikipedia content into responses because it classified as
        # factual_query and Box W ran unconditionally. Compute intent up
        # front so we can short-circuit the Box 0 / Box W stack.
        _intent = self._infer_intent_type(user_input, appraisal)

        # Halfstep
        shape_to_halfstep: dict = {
            "low_movement_answer":         "hidden_assumption",
            "admissible_reframing_answer": "adjacent_contrast",
        }
        halfstep_kind: HalfStepType = shape_to_halfstep.get(
            decision.answer_shape or "", "hidden_assumption"
        )
        halfstep_note = compose_halfstep(halfstep_kind, state.active_language)
        _chain_type = _select_halfstep_chain_type(appraisal, decision)

        if not self.adapter:
            return None, halfstep_note, sources

        # ── Casual greeting fast path ────────────────────────────
        # Brief-acknowledgement prompt, no Box 0 / W / A grounding.
        # Reason code marks the path for trace/eval inspection.
        if _intent == "casual_greeting":
            decision.reason_codes.append("CASUAL_GREETING_FAST_PATH")
            prompt = _casual_greeting_prompt(user_input, state.active_language)
            return prompt, None, sources

        # ── Query Reformulation (Sprint 2) ──────────────────────
        _reformulated = None
        try:
            _reformulated = reformulate_query(
                user_input, state.active_language, adapter=self.adapter)
        except Exception:
            pass

        # ── Box 0 context for self-referential queries ───────────
        # L8 persona-drift mitigation: retrieve via the filtered helper
        # so v8.2 add-on example chunks are demoted below canonical
        # identity chunks before the top-3 are taken as prompt context.
        # Phase 3 Stab Commit 44: also fires on full-primary library hint.
        box0_context = ""
        if should_retrieve_box_0 and self.box_0_adapter is not None:
            _r = self._retrieve_box_0_filtered(user_input, top_k=3)
            if _r is not None and _r.sources:
                box0_context = _r.synthesis

        if should_retrieve_box_0 and box0_context:
            prompt = (
                f"Reference (canonical MOBIUS documentation):\n{box0_context}\n\n"
                f"User: {user_input}\n\n"
                f"Respond in {state.active_language}. "
                f"Answer based on the reference above. "
                f"Answer the specific question only. "
                f"Do not dump full specifications unless explicitly asked. "
                f"Keep the response concise and authoritative."
            )
            return prompt, None, sources

        # ── Box W: Wikipedia FAISS evidence lookup ───────────────
        _skip_wiki = (
            "CONV_OVERRIDE" in (getattr(appraisal, 'notes', []) or [])
            or _intent == "casual_greeting"  # defense-in-depth: fast path
                                             # should have returned above,
                                             # this is a belt-and-braces
                                             # guarantee at the Box W gate.
        )
        WIKI_CONFIDENCE_THRESHOLD = 0.75
        wiki_context  = ""
        wiki_escalate = False

        if not _skip_wiki and (
            self.wiki_adapter is not None
            and hasattr(self.wiki_adapter, 'is_available')
            and self.wiki_adapter.is_available()
        ):
            try:
                _wiki_q = (_reformulated.en_keywords
                           if _reformulated else user_input)
                # Phase G.12 — fetch a slightly wider pool when domain
                # rerank will run, so the boost has room to reorder.
                _wiki_top_k = 4 if (
                    _reformulated is not None
                    and getattr(_reformulated, "canonical_hits", None)
                ) else 2
                _wb = self.wiki_adapter.retrieve(_wiki_q, top_k=_wiki_top_k)
                if _wb.sources:
                    # Phase G.12 — domain-aware rerank when a canonical
                    # domain hint is available. Inspectable; bounded.
                    try:
                        from ..retrieval.query_reformulator import (
                            canonical_term_domain_hint,
                        )
                        from ..retrieval.domain_rerank import (
                            rerank_with_domain_anchor,
                        )
                        _domain = canonical_term_domain_hint(
                            getattr(_reformulated, "canonical_hits", None)
                            if _reformulated is not None else None
                        )
                        if _domain:
                            _rr = rerank_with_domain_anchor(
                                _wb.sources, _wb.synthesis, _domain,
                            )
                            # Attach rerank outcome on state for trace.
                            try:
                                state._last_box_w_rerank = {
                                    "domain": _domain,
                                    "notes": list(_rr.notes),
                                    "boosts": _rr.boosts_applied,
                                }
                            except Exception:   # noqa: BLE001
                                pass
                            # Reassemble a RetrievalResult view with the
                            # reranked ordering.
                            from ..adapters.retrieval_selector import RetrievalResult
                            _wb = RetrievalResult(
                                sources=_rr.sources,
                                outcome=_wb.outcome,
                                synthesis=_rr.synthesis,
                            )
                            for _n in _rr.notes:
                                if _n not in decision.reason_codes:
                                    decision.reason_codes.append(_n)
                    except Exception:   # noqa: BLE001
                        pass
                    top_score = _wb.sources[0].relevance_score or 0.0
                    if top_score >= WIKI_CONFIDENCE_THRESHOLD:
                        wiki_context = _wb.synthesis
                    else:
                        wiki_escalate = True
                        decision.reason_codes.append("WIKI_LOW_CONFIDENCE")
            except Exception:
                pass

        # Low confidence Wiki hit → signal verify escalation
        if wiki_escalate:
            state._wiki_escalate = True
            return None, None, sources

        if wiki_context:
            # Phase G.10 — canonical-term synthesis bridge. When the query
            # reformulator produced a canonical English mapping (e.g.
            # "ユニット射 = unit morphism"), surface that as a short
            # glossary line so the LLM does not drift on the raw Japanese
            # surface form during answer synthesis. Gated on technical
            # context (wiki_context present AND canonical_hits produced).
            _canon_block = ""
            if _reformulated is not None and getattr(_reformulated, "canonical_hits", None):
                try:
                    from ..retrieval.query_reformulator import canonical_term_hint_from_hits
                    _hint = canonical_term_hint_from_hits(_reformulated.canonical_hits)
                    if _hint:
                        _canon_block = (
                            f"Canonical glossary (use the canonical English "
                            f"term where relevant): {_hint}\n\n"
                        )
                        decision.reason_codes.append("CANONICAL_TERM_HINT_APPLIED")
                except Exception:
                    pass
            prompt = (
                f"{_canon_block}"
                f"Evidence from Wikipedia (authoritative):\n"
                f"{wiki_context}\n\n"
                f"User: {user_input}\n\n"
                f"Respond in {state.active_language}. "
                f"Answer based on the evidence above. "
                f"If the evidence conflicts with your training "
                f"knowledge, the evidence takes priority. "
                f"Keep the response concise. "
                f"Do not add rhetorical questions within the answer body. "
                f"{_halfstep_frame(halfstep_note, state.active_language, _chain_type, decision=decision)}"
            )
            decision.reason_codes.append("WIKI_EVIDENCE")
        else:
            # Stage 6 — Box X (curated external durable knowledge)
            # supplemental fallback. Activates only on technical /
            # reference-like queries when Wikipedia produced no
            # sufficient evidence and the query is not freshness-
            # sensitive. Box X does NOT outrank Wikipedia; it only
            # contributes when Wikipedia returned nothing usable.
            _box_x_record = self._box_x_consult(
                query=user_input, appraisal=appraisal, state=state, top_k=3,
            )
            _box_x_block = ""
            if _box_x_record and _box_x_record.get("hit"):
                _box_x_block = self._box_x_evidence_block(_box_x_record)
                decision.reason_codes.append("BOX_X_CONSULTED")
                if _box_x_block:
                    decision.reason_codes.append("BOX_X_HIT")
                    decision.reason_codes.append("BOX_X_USED")
            elif _box_x_record is not None:
                # Consulted but no hit — record only the consult event.
                decision.reason_codes.append("BOX_X_CONSULTED")
                decision.reason_codes.append("BOX_X_MISS")
            # else: box_x_record is None → consultation suppressed
            #       (env disabled, no store, freshness-sensitive). No
            #       reason code added; absence is itself the signal.
            if _box_x_block:
                prompt = (
                    f"User: {user_input}\n\n"
                    f"Respond in {state.active_language}. "
                    f"Answer the user directly in natural prose. "
                    f"Keep the response concise and grounded. "
                    f"Do not add rhetorical questions within the answer body. "
                    f"{_halfstep_frame(halfstep_note, state.active_language, _chain_type, decision=decision)}\n\n"
                    f"Terminology hints (background only — do not quote as a "
                    f"reference block; use only if they improve canonical-term "
                    f"accuracy):\n{_box_x_block}"
                )
                return prompt, None, sources

            # Box M: inject session memory if available
            _mem_ctx = self._retrieve_memory_context(user_input)
            if _mem_ctx:
                prompt = (
                    f"Session context:\n{_mem_ctx}\n\n"
                    f"User: {user_input}\n\n"
                    f"Respond in {state.active_language}. "
                    f"Use the session context if relevant. "
                    f"Keep the response concise and grounded. "
                    f"Do not add rhetorical questions within the answer body. "
                    f"{_halfstep_frame(halfstep_note, state.active_language, _chain_type, decision=decision)}"
                )
                decision.reason_codes.append("MEMORY_CONTEXT")
            else:
                prompt = (
                    f"User: {user_input}\n\n"
                    f"Respond in {state.active_language}. "
                    f"Keep the response concise and grounded. "
                    f"Do not add rhetorical questions within the answer body. "
                    f"{_halfstep_frame(halfstep_note, state.active_language, _chain_type, decision=decision)}"
                )

        return prompt, None, sources

    def _prepare_verify_stream(
        self,
        user_input: str,
        appraisal:  AppraisalState,
        state:      SessionState,
    ) -> dict:
        """Gather evidence, run EAL adjudication, build prompt for verify streaming.

        Returns dict with keys: prompt, fallback_text, sources, verify_outcome.
        When adapter is available, prompt is set for streaming generation.
        When not, fallback_text is set for direct yield.
        """
        from ..compose.verify_synthesizer import (
            _outcome_from_admissibility as _vs_outcome,
            _sources_for_trace          as _vs_sources,
            _build_evidence_block       as _vs_evidence,
            _build_prompt               as _vs_prompt,
            _fallback_text              as _vs_fallback,
        )
        from ..adjudication.verify_presets import get_preset as _get_preset

        sources: List[str] = []
        why_local_insufficient = ""

        # ── Guard: ask-before-verify ─────────────────────────────────────
        if appraisal.completeness < 0.6 or appraisal.intent_clarity < 0.6:
            text = compose_non_answer_response(
                type("D", (), {"route": "ask"})(), state.active_language
            )
            return {"fallback_text": text, "sources": [], "verify_outcome": "ask_redirected"}

        # ── M-1: Coreference resolution ──────────────────────────────────
        search_query = user_input
        if hasattr(state, 'instant_memory') and state.instant_memory.entity_map:
            search_query = state.instant_memory.resolve_query(user_input)

        # ── Query Reformulation (Sprint 2) ──────────────────────────────
        _reformulated = None
        try:
            _reformulated = reformulate_query(
                search_query, state.active_language, adapter=self.adapter)
        except Exception:
            pass

        # ── M-3: Verified stable facts ───────────────────────────────────
        local_context_text = ""
        local_used = False
        if hasattr(state, 'verified_facts'):
            m3_hits = state.verified_facts.retrieve(user_input)
            if m3_hits:
                local_context_text = "\n".join(
                    f"[Verified fact] {f.claim} (source: {f.source_label})"
                    for f in m3_hits[:3]
                )
                local_used = True
                sources = [f.source_label for f in m3_hits]

        # ── Stage 1: Local RAG ───────────────────────────────────────────
        local_hits_available = local_used
        if self.rag_pipeline and not self.rag_pipeline.is_empty:
            rag_result: RAGResult = self.rag_pipeline.query(search_query)
            local_hits_available = rag_result.sufficient
            if local_hits_available and rag_result.chunks:
                local_context_text = "\n\n".join(c.text for c in rag_result.chunks[:3])
                sources            = rag_result.sources
                local_used         = True
            if not rag_result.sufficient:
                why_local_insufficient = "Local corpus did not return sufficient evidence."

        plan = choose_retrieval_plan(
            freshness_sensitive=appraisal.freshness_sensitive,
            local_hits_available=local_hits_available,
        )

        # ── Stage 1b: Kiwix local fallback ───────────────────────────────
        if (
            not local_used
            and self.kiwix_adapter
            and plan.use_kiwix_fallback
        ):
            _kiwix_q = (_reformulated.en_keywords
                        if _reformulated else search_query)
            raw_response  = self.kiwix_adapter.search(
                query=_kiwix_q, max_results=5,
                freshness_hint=None, preset=self.verify_preset,
            )
            normalized    = normalize_search_response(raw_response)
            adjudicated   = adjudicate_evidence(
                normalized, user_input, preset=self.verify_preset
            )
            if normalized.success:
                outcome     = _vs_outcome(adjudicated.admissibility)
                trace_src   = _vs_sources(adjudicated)
                source_urls = [s["url"] for s in trace_src] or sources

                state._last_eal = {
                    "UsedLocalEvidence":              local_used,
                    "UsedWebSearch":                  False,
                    "UsedKiwix":                      True,
                    "WhyWebSearchWasTriggered":       "",
                    "WhyLocalEvidenceWasInsufficient": why_local_insufficient,
                    "SearchProvider":                 raw_response.provider,
                    "Admissibility":                  adjudicated.admissibility,
                    "ConflictState":                  adjudicated.conflict_state,
                    "FreshnessState":                 adjudicated.freshness_state,
                    "Sources":                        trace_src,
                }

                if self.adapter and adjudicated.items:
                    preset_obj     = _get_preset(self.verify_preset)
                    evidence_block = _vs_evidence(adjudicated)
                    prompt = _vs_prompt(
                        user_input, outcome, evidence_block, adjudicated,
                        state.active_language, preset_tone=preset_obj.tone_note,
                    )
                    return {
                        "prompt": prompt, "sources": source_urls,
                        "verify_outcome": outcome,
                    }
                else:
                    return {
                        "fallback_text": _vs_fallback(outcome, adjudicated),
                        "sources": source_urls, "verify_outcome": outcome,
                    }

        # ── Stage 1.5: Box X (curated external durable knowledge) ────────
        # Bounded supplemental fallback when local evidence (M-3 + RAG +
        # Kiwix) is insufficient AND the query is NOT freshness-sensitive.
        # Box X never displaces the freshness-sensitive Web/Box S path.
        if (
            not local_used
            and not appraisal.freshness_sensitive
        ):
            _box_x_record = self._box_x_consult(
                query=user_input, appraisal=appraisal, state=state, top_k=3,
            )
            if _box_x_record and _box_x_record.get("hit"):
                _bx_block = self._box_x_evidence_block(_box_x_record)
                if _bx_block:
                    decision = type("D", (), {"reason_codes": []})()
                    # decision is local-only here for compatibility with
                    # the rest of the verify path. We surface reason
                    # codes via state._last_box_x notes instead.
                    state._last_eal = {
                        "UsedLocalEvidence":              True,
                        "UsedWebSearch":                  False,
                        "UsedBoxX":                       True,
                        "WhyWebSearchWasTriggered":       "",
                        "WhyLocalEvidenceWasInsufficient": why_local_insufficient,
                        "SearchProvider":                 "box_x_curated",
                        "Admissibility":                  "supplemental",
                        "ConflictState":                  "none",
                        "FreshnessState":                 "static",
                        "Sources":                        [
                            {"url": h.get("source_uri",""),
                             "title": h.get("title",""),
                             "snippet": ""}
                            for h in _box_x_record.get("hits", [])
                        ],
                    }
                    bx_source_urls = [
                        h.get("source_uri","")
                        for h in _box_x_record.get("hits", [])
                    ]
                    if self.adapter:
                        prompt = (
                            f"User: {user_input}\n\n"
                            f"Respond in {state.active_language}. "
                            f"Answer the user directly in natural prose. "
                            f"Keep the response concise.\n\n"
                            f"Terminology hints (background only — do not quote "
                            f"as a reference block; use only if they improve "
                            f"canonical-term accuracy):\n{_bx_block}"
                        )
                        return {
                            "prompt": prompt,
                            "sources": bx_source_urls or sources,
                            "verify_outcome": "box_x_supplemental",
                        }
                    else:
                        return {
                            "fallback_text": _bx_block,
                            "sources": bx_source_urls or sources,
                            "verify_outcome": "box_x_supplemental",
                        }

        # ── Stage 2: Web fallback via EAL ────────────────────────────────
        if self.web_search_adapter and (
            not local_used or appraisal.freshness_sensitive
        ):
            why_web = (
                "Freshness-sensitive query requires current external evidence."
                if appraisal.freshness_sensitive
                else "Local evidence insufficient."
            )
            # RCB_1 (Reformulation Entitlement): revoke reformulation privilege
            # when TVS >= TVS_HIGH_THRESHOLD (L0 v8.2 §9.1) to prevent stale
            # knowledge contamination from reformulator. freshness_sensitive
            # (threshold 0.6) is the behavioral gate for date-stamp anchoring;
            # TVS_HIGH_THRESHOLD (0.70) is the declarative marker for
            # reformulation revocation per CC_16/RCB design.
            if appraisal.freshness_sensitive:
                from datetime import datetime as _dt
                # RCB_2 (Date-Stamp Anchoring) — already implemented, retained as-is
                _web_q = f"{search_query} {_dt.now().strftime('%Y-%m-%d')}"
            else:
                _web_q = (_reformulated.native_keywords
                          if _reformulated else search_query)
            raw_response  = self.web_search_adapter.search(
                query=_web_q, max_results=5,
                freshness_hint="recent" if appraisal.freshness_sensitive else None,
                preset=self.verify_preset,
            )
            normalized    = normalize_search_response(raw_response)
            adjudicated   = adjudicate_evidence(
                normalized, user_input, preset=self.verify_preset
            )

            outcome     = _vs_outcome(adjudicated.admissibility)
            trace_src   = _vs_sources(adjudicated)
            source_urls = [s["url"] for s in trace_src] or sources

            state._last_eal = {
                "UsedLocalEvidence":              local_used,
                "UsedWebSearch":                  normalized.success,
                "WhyWebSearchWasTriggered":       why_web,
                "WhyLocalEvidenceWasInsufficient": why_local_insufficient,
                "SearchProvider":                 raw_response.provider,
                "Admissibility":                  adjudicated.admissibility,
                "ConflictState":                  adjudicated.conflict_state,
                "FreshnessState":                 adjudicated.freshness_state,
                "Sources":                        trace_src,
            }

            if self.adapter and adjudicated.items:
                preset_obj     = _get_preset(self.verify_preset)
                evidence_block = _vs_evidence(adjudicated)
                prompt = _vs_prompt(
                    user_input, outcome, evidence_block, adjudicated,
                    state.active_language, preset_tone=preset_obj.tone_note,
                )
                return {
                    "prompt": prompt, "sources": source_urls,
                    "verify_outcome": outcome,
                }
            else:
                return {
                    "fallback_text": _vs_fallback(outcome, adjudicated),
                    "sources": source_urls, "verify_outcome": outcome,
                }

        # ── Stage 3: Local-only synthesis ────────────────────────────────
        if self.adapter:
            if local_context_text:
                prompt = (
                    f"Evidence:\n{local_context_text}\n\n"
                    f"Question: {user_input}\n\n"
                    f"Respond in {state.active_language}. "
                    f"Give a bounded answer based only on the evidence above. "
                    f"State clearly if the evidence is incomplete."
                )
                return {
                    "prompt": prompt, "sources": sources,
                    "verify_outcome": "verify_partial",
                }
            else:
                # Box M: inject session memory into verify fallback
                _mem_ctx = self._retrieve_memory_context(user_input)
                if _mem_ctx:
                    prompt = (
                        f"Session context:\n{_mem_ctx}\n\n"
                        f"Question: {user_input}\n\n"
                        f"Respond in {state.active_language}. "
                        f"You do not have external evidence but session context "
                        f"is available. Use it if relevant. "
                        f"State clearly what you cannot confirm and why."
                    )
                else:
                    prompt = (
                        f"Question: {user_input}\n\n"
                        f"Respond in {state.active_language}. "
                        f"No external evidence was found for this question. "
                        f"If you have relevant knowledge, answer using your own knowledge "
                        f"and note that external verification was not available. "
                        f"Do not refuse to answer just because no sources were retrieved."
                    )
                return {
                    "prompt": prompt, "sources": sources,
                    "verify_outcome": "verify_failed",
                }

        # No adapter available
        if local_context_text:
            return {
                "fallback_text": (
                    f"[verify:partial] "
                    f"Sources: {', '.join(sources) or 'local corpus'}. "
                    f"Evidence found but model not connected."
                ),
                "sources": sources, "verify_outcome": "verify_partial",
            }
        else:
            return {
                "fallback_text": compose_non_answer_response(
                    type("D", (), {"route": "verify"})(), state.active_language
                ),
                "sources": sources, "verify_outcome": "verify_failed",
            }

    # ── Route handlers ───────────────────────────────────────────────────────

    def _dispatch(
        self,
        user_input: str,
        decision:   RouteDecision,
        appraisal:  AppraisalState,
        state:      SessionState,
    ):
        route = decision.route
        sources: List[str] = []
        verify_outcome: Optional[str] = None

        if route == "answer":
            text = self._handle_answer(user_input, decision, appraisal, state)
            # cyc_20260424_pattern_c_full: if the answer path internally
            # escalated to verify (C.3 branch), pull the sources /
            # outcome that _handle_answer stashed on state. Previously
            # these were discarded at the `return verify_text` boundary
            # inside _handle_answer, leaving RoutingResult.sources empty
            # even when Brave was consulted and cited in the response.
            _escalated = getattr(state, "_last_escalated_verify_sources", None)
            if _escalated is not None:
                sources = _escalated
                _esc_outcome = getattr(
                    state, "_last_escalated_verify_outcome", None,
                )
                if _esc_outcome:
                    verify_outcome = _esc_outcome
                # Clear to avoid leaking into subsequent turns.
                state._last_escalated_verify_sources = None
                state._last_escalated_verify_outcome = None
            # Phase B.1: V_regen escalation check
            if getattr(state, '_vregen_escalate', False):
                state._vregen_escalate = False
                text, sources, verify_outcome = self._handle_verify(
                    user_input, appraisal, state
                )
                verify_outcome = (verify_outcome or '') + '+vregen_escalated'

        elif route == "ask":
            text = compose_non_answer_response(decision, state.active_language)

        elif route == "verify":
            text, sources, verify_outcome = self._handle_verify(
                user_input, appraisal, state
            )

        else:  # abstain
            text = compose_non_answer_response(decision, state.active_language)

        # ── Stage 4 — empty-response bounded fallback ─────────────────────
        # Catches paths where the adapter or synth layer returned empty
        # text despite the route being answer/verify. Honest, bounded,
        # no synthetic filler: we state what happened and invite a
        # rephrase. Applied BEFORE save-ack injection so the ack still
        # surfaces on save-intent + empty cases.
        if not (text or "").strip() and route in ("answer", "verify"):
            text = _stage4_empty_fallback(state.active_language)
            if not verify_outcome:
                verify_outcome = "empty_fallback" if route == "verify" else None
            decision.reason_codes.append("EMPTY_RESPONSE_FALLBACK")

        # ── Stage 4 — save-intent acknowledgement ─────────────────────────
        # Prepend a short, honest ack when the appraisal flagged a
        # save/continuity intent. Only modifies output TEXT — the actual
        # save (carryover/Box P) still happens in the UI post-response
        # hook path, unchanged. Skipped on ask/abstain because those
        # routes already produce deterministic clarification text.
        if (
            getattr(appraisal, "continuity_save_intent", False)
            and route in ("answer", "verify")
            and (text or "").strip()
        ):
            text = _stage4_save_ack_prefix(state.active_language) + text

        return text, sources, verify_outcome

    def _handle_answer(
        self,
        user_input: str,
        decision:   RouteDecision,
        appraisal:  AppraisalState,
        state:      SessionState,
    ) -> str:
        is_self_ref = getattr(appraisal, "self_referential", False)
        # Phase 3 Stab Commit 44: full primary mode hint from library.
        library_box_0_hint = bool(
            getattr(state, "_library_primary_box_0_hint", False)
        )
        should_retrieve_box_0 = is_self_ref or library_box_0_hint

        # ── Phase F v2: Unified Decision Layer (deterministic) ──────────
        # Computed once per turn; result guides Box W cap, presentation
        # profile, and half-step allowance for the rest of this function.
        try:
            from .decision_layer import (
                compute_decision_layer as _compute_dl,
                REGIME_META_RECALL as _REG_META,
                REGIME_FRESHNESS as _REG_FRESH,
                REGIME_SELF_REF as _REG_SELF,
                REGIME_CONTEXT_DEPENDENT as _REG_CTX,
                REGIME_COLD_START as _REG_COLD,
            )
            from .presentation_policy import (
                profile_tone_clause as _profile_tone,
            )
            from .language_anchor import (
                is_vague_continuation as _is_vague_cont,
                is_explicit_language_switch as _is_lang_switch,
                resolve_anchor_language as _resolve_anchor,
                anchor_clause as _anchor_clause,
            )
            from .format_descriptor import (
                is_same_format_request as _is_same_fmt,
                extract_from_session as _extract_fmt,
                format_instruction_clause as _fmt_clause,
            )
            _um = state.ensure_user_map()
            _mf = state.build_memory_fit(
                meta_recall_mode=bool(getattr(appraisal, "meta_recall_intent", False)),
                topic_risk=0.3,
            )
            # Phase G.3: resolve selection via the hardened contract.
            # Blank selections → balanced_default (behavior-preserving).
            # Unknown/malformed inputs → safe fallback + inspectable notes.
            # Optional per-call `profile_override` takes precedence over
            # session selection without mutating SessionState.
            from .profiles import (
                resolve_profile_selection as _resolve_sel,
                get_authority_profile as _get_auth_p,
                get_retrieval_profile as _get_retr_p,
            )
            _sel_auth_id = getattr(state, "selected_authority_profile_id", "") or ""
            _sel_retr_id = getattr(state, "selected_retrieval_profile_id", "") or ""
            _sel_override = getattr(state, "_phase_g3_override_request", None)
            _sel_result = _resolve_sel(
                _sel_auth_id, _sel_retr_id, override=_sel_override,
            )
            _auth_prof = _get_auth_p(_sel_result.normalized_authority_profile_id)
            _retr_prof = _get_retr_p(_sel_result.normalized_retrieval_profile_id)
            # Persist compact selection notes on SessionState for inspection.
            try:
                for _n in _sel_result.notes:
                    state._append_profile_selection_note(_n)
            except Exception:
                # Older SessionState without the helper: tolerate silently.
                pass
            _sup = _compute_dl(
                appraisal,
                user_map=_um,
                memory_fit=_mf,
                authority_profile=_auth_prof,
                retrieval_profile=_retr_prof,
            )
            # Expose effective profile IDs on SessionState for inspection.
            state.effective_authority_profile_id = _sup.effective_authority_profile_id
            state.effective_retrieval_profile_id = _sup.effective_retrieval_profile_id
            state._phase_f_decision_layer = _sup.to_dict()
            # Phase G.3: compact per-turn selection record for trace.
            state._phase_g3_profile_selection = _sel_result.to_dict()
        except Exception as _sup_exc:
            _sup = None
            _mf = None
            _profile_tone = None  # type: ignore
            _is_vague_cont = None  # type: ignore
            _is_lang_switch = None  # type: ignore
            _resolve_anchor = None  # type: ignore
            _anchor_clause = None  # type: ignore
            _is_same_fmt = None  # type: ignore
            _extract_fmt = None  # type: ignore
            _fmt_clause = None  # type: ignore
            _REG_META = _REG_FRESH = _REG_SELF = _REG_CTX = _REG_COLD = None  # type: ignore

        # Determine half-step type from answer_shape
        shape_to_halfstep: dict = {
            "low_movement_answer":        "hidden_assumption",
            "admissible_reframing_answer":"adjacent_contrast",
        }
        halfstep_kind: HalfStepType = shape_to_halfstep.get(
            decision.answer_shape or "", "hidden_assumption"
        )
        halfstep_note = compose_halfstep(halfstep_kind, state.active_language)
        # Phase F: memory_fit-aware half-step selection (cold_start → deepening).
        _chain_type = _select_halfstep_chain_type(appraisal, decision, memory_fit=_mf)

        # ── Phase F v2 wiring: meta-recall fast path ─────────────────────
        # When the decision layer classifies the regime as META_RECALL, bypass
        # external retrieval (Box W/0/A) and synthesize from session-derived
        # recall. This fixes the "Summarize" / "Can you continue?" / "Same
        # format" pollution class on the normal governed path.
        #
        # v2 additions:
        #   - Language anchor: vague continuations preserve user language
        #     (prevents French-drift on "Can you continue?").
        #   - Format descriptor: same-format requests reuse prior assistant
        #     format coarsely (bullets / two-line poem / numbered / prose).
        if _sup is not None and _sup.regime == _REG_META and self.adapter is not None:
            from src.memory.meta_recall import build_meta_recall_summary
            _meta = build_meta_recall_summary(state)
            _topics = "; ".join(_meta.topics_covered) if _meta.topics_covered else "(no prior turns recorded)"
            _corrs  = "; ".join(_meta.user_corrections) if _meta.user_corrections else "(none)"
            _open   = _meta.opening_turn_label or "(unknown)"
            _tone = _profile_tone(_sup.presentation_profile, state.active_language) if _profile_tone else ""

            # ── Language anchor (Phase F v2) ─────────────────────────────
            _lang_line = ""
            if _is_vague_cont is not None and _is_vague_cont(user_input) and \
                    not (_is_lang_switch and _is_lang_switch(user_input)):
                _target_lang = _resolve_anchor(user_input, state, fallback=state.active_language)
                _lang_clause = _anchor_clause(_target_lang) if _target_lang else ""
                if _lang_clause:
                    _lang_line = _lang_clause
                    decision.reason_codes.append(f"LANG_ANCHOR={_target_lang}")

            # ── Format descriptor (Phase F v2) ──────────────────────────
            _fmt_line = ""
            if _is_same_fmt is not None and _is_same_fmt(user_input):
                _descriptor = _extract_fmt(state) if _extract_fmt else None
                if _descriptor is not None:
                    _fmt_line = _fmt_clause(_descriptor) if _fmt_clause else ""
                    decision.reason_codes.append(f"SAME_FORMAT={_descriptor.kind}")
                else:
                    _fmt_line = (_fmt_clause(None) if _fmt_clause else "")
                    decision.reason_codes.append("SAME_FORMAT=unknown")

            # ── Format-anchored continuation reason codes (Phase F v2+) ──
            # When the appraisal's narrow exception fired, expose it in the
            # trace so the bounded-continuation path is inspectable.
            if getattr(appraisal, "format_anchored_continuation", False):
                decision.reason_codes.append("FORMAT_ANCHORED_CONTINUATION")
                decision.reason_codes.append("FORMAT_CONTINUATION_BOUNDED")

            prompt = (
                f"[Session-derived recall — internal conversation state ONLY]\n"
                f"Topics covered: {_topics}\n"
                f"User corrections: {_corrs}\n"
                f"Opening turn snippet: {_open}\n\n"
                f"User: {user_input}\n\n"
                f"Respond in {state.active_language}. "
                f"Answer using ONLY the session-derived recall above. "
                f"If the recall is insufficient for a specific detail, say so "
                f"honestly in one sentence and offer the most useful next step. "
                f"If the question asks for a simple fact that is well outside "
                f"the conversation yet obviously stable, you may provide it "
                f"briefly without treating external retrieval as authoritative. "
                f"Do NOT introduce Wikipedia content or cite external sources. "
                f"{_tone} "
                f"{_lang_line} "
                f"{_fmt_line}"
            )
            decision.reason_codes.append("META_RECALL_SESSION_GROUNDED")
            req = KernelRequest(
                user_input=user_input, prompt=prompt,
                metadata={"intent_type": "meta", "route": "answer"},
            )
            resp = self.adapter.generate(req)
            return resp.text

        # ── Intent detection (early: drives casual_greeting fast path) ───
        # cyc_20260423_production_failure_deep_fix_2: moved up from its
        # previous position inside the prompt-construction block so the
        # casual_greeting branch can short-circuit Box 0 / A / BC / W
        # retrieval before any external lookup runs.
        _intent = self._infer_intent_type(user_input, appraisal)
        _is_creative = _intent == "creative_request"

        # ── Casual greeting fast path ────────────────────────────
        # Brief-acknowledgement response with no Box retrieval. Mirrors
        # the META_RECALL fast path above, and takes precedence over any
        # downstream Box consultation.
        if _intent == "casual_greeting" and self.adapter is not None:
            decision.reason_codes.append("CASUAL_GREETING_FAST_PATH")
            _cg_prompt = _casual_greeting_prompt(user_input, state.active_language)
            req = KernelRequest(
                user_input=user_input,
                prompt=_cg_prompt,
                metadata={"intent_type": "casual_greeting", "route": "answer"},
            )
            resp = self.adapter.generate(req)
            return resp.text

        # ── Box 0 context for self-referential queries ───────────────
        # L8 persona-drift mitigation: retrieve via the filtered helper
        # so v8.2 add-on example chunks are demoted below canonical
        # identity chunks before the top-3 are taken as prompt context.
        # Phase 3 Stab Commit 44: also fires on full-primary library hint.
        box0_context = ""
        if should_retrieve_box_0 and self.box_0_adapter is not None:
            _r = self._retrieve_box_0_filtered(user_input, top_k=3)
            if _r is not None and _r.sources:
                box0_context = _r.synthesis

        # ── Query Reformulation (Sprint 2) ──────────────────────
        _reformulated = None
        try:
            _reformulated = reformulate_query(
                user_input, state.active_language, adapter=self.adapter)
        except Exception:
            pass

        # ── Box A: governance document scan ─────────────────────
        box_a_context, box_a_mode, box_a_results, box_a_few_shot = \
            self._search_box_a(user_input)
        state._last_box_a = {
            "doc_ids": [r["doc_id"] for r in box_a_results] if box_a_results else [],
            "filenames": [r["filename"] for r in box_a_results] if box_a_results else [],
            "mode": box_a_mode,
            "top_score": box_a_results[0]["score"] if box_a_results else None,
            "compliant": None,
        }

        # ── Box B / C: Phase G.11 reserved document-slot scan ─────
        box_bc_context, box_bc_hits = self._search_box_bc(user_input, state)
        state._last_box_bc = {
            "active": bool(box_bc_hits),
            "hit_count": len(box_bc_hits),
            "labels": sorted({h["box"] for h in box_bc_hits}),
            "top_score": box_bc_hits[0]["score"] if box_bc_hits else None,
        }
        if box_bc_hits:
            try:
                decision.reason_codes.append("BOX_BC_REFERENCE_USED")
            except Exception:   # noqa: BLE001
                pass

        # (intent detection was moved up — see `_intent` computed before
        # the Box 0 block above. `_is_creative` flag re-exposed here for
        # downstream use without recomputing.)

        if self.adapter:
            if should_retrieve_box_0 and box0_context:
                prompt = (
                    f"Reference (canonical MOBIUS documentation):\n{box0_context}\n\n"
                    f"User: {user_input}\n\n"
                    f"Respond in {state.active_language}. "
                    f"Answer based on the reference above. "
                    f"Answer the specific question only. "
                    f"Do not dump full specifications unless explicitly asked. "
                    f"Keep the response concise and authoritative."
                )
            else:
                # ── Box W: Wikipedia FAISS evidence lookup ───────────
                # Skip in conversational/game context (M-1 override) or
                # casual_greeting fast path (defense-in-depth — fast path
                # should have returned earlier, but this belt-and-braces
                # gate guarantees Box W cannot be consulted for a
                # greeting even if control flow was restructured).
                _skip_wiki = (
                    "CONV_OVERRIDE" in (getattr(appraisal, 'notes', []) or [])
                    or _intent == "casual_greeting"
                )

                # Phase F v1 + Phase C.5 wiring:
                # Threshold is decision-layer-aware. Stable-fact gear raises the
                # gate so weak Fujinashi-style chunks don't pass. Other gears
                # keep the historical 0.75 default.
                _WIKI_DEFAULT = 0.75
                WIKI_CONFIDENCE_THRESHOLD = _WIKI_DEFAULT
                _cap_from_sup = None
                if _sup is not None:
                    _cap_from_sup = _sup.effective_box_w_cap
                    if getattr(_sup.gear, "wiki_threshold_override", None) is not None:
                        WIKI_CONFIDENCE_THRESHOLD = float(_sup.gear.wiki_threshold_override)

                # If decision layer has declared Box W insufficient, skip retrieve.
                _cap_forbids_retrieve = (_cap_from_sup == "insufficient")

                wiki_context  = ""
                wiki_is_auxiliary = False
                wiki_escalate = False
                _wb = None
                _wb_label = None
                if not _skip_wiki and not _cap_forbids_retrieve and (
                    self.wiki_adapter is not None
                    and hasattr(self.wiki_adapter, 'is_available')
                    and self.wiki_adapter.is_available()
                ):
                    try:
                        _wiki_q = (_reformulated.en_keywords
                                   if _reformulated else user_input)
                        _wb = self.wiki_adapter.retrieve(_wiki_q, top_k=2)
                        if _wb.sources:
                            top_score = _wb.sources[0].relevance_score or 0.0

                            # Phase C.5 calibration (opt-in through decision layer).
                            # Only engaged when decision layer is available and the
                            # cap is not "sufficient" (i.e., this gear wants
                            # genuine semantic admissibility, not just hit).
                            if _sup is not None and _cap_from_sup in ("auxiliary", "sufficient"):
                                try:
                                    from src.adapters.box_w_calibration import (
                                        BoxBCalibrationInputs as _BBI,
                                        calibrate_box_b as _calibrate,
                                        LABEL_SUFFICIENT as _LAB_SUF,
                                        LABEL_AUXILIARY as _LAB_AUX,
                                        LABEL_INSUFFICIENT as _LAB_INS,
                                    )
                                    _title = getattr(_wb.sources[0], "label", "")
                                    _chunk = (_wb.synthesis or "")[:4000]
                                    _top2 = 0.0
                                    if len(_wb.sources) >= 2:
                                        _top2 = float(getattr(_wb.sources[1], "relevance_score", 0.0) or 0.0)
                                    _tvs_val = getattr(getattr(appraisal, "kvs", None), "tvs", 0.0) or 0.0
                                    _tvs_band = (
                                        "HIGH" if _tvs_val >= 0.70
                                        else "MID" if _tvs_val >= 0.30
                                        else "LOW"
                                    )
                                    _calib = _calibrate(_BBI(
                                        query=user_input,
                                        chunk_text=_chunk,
                                        chunk_title=_title,
                                        top1_score=float(top_score),
                                        top2_score=_top2,
                                        self_referential=bool(is_self_ref),
                                        freshness_sensitive=bool(getattr(appraisal, "freshness_sensitive", False)),
                                        context_dependent=bool(getattr(appraisal, "context_dependent", False)),
                                        tvs_band=_tvs_band,
                                        user_correction=bool(getattr(appraisal, "user_correction", False)),
                                        meta_recall_intent=bool(getattr(appraisal, "meta_recall_intent", False)),
                                        route_hint="answer",
                                        active_context_present=bool(len(getattr(state, "conversation_turns", []) or []) >= 2),
                                    ))
                                    _wb_label = _calib.label
                                    state._phase_f_box_w_calibration = _calib.to_dict()
                                    # Resolve effective label under cap.
                                    _cap = _cap_from_sup
                                    _rank = {"insufficient": 0, "auxiliary": 1, "sufficient": 2}
                                    if _rank[_wb_label] > _rank.get(_cap, 2):
                                        _wb_label = _cap
                                    if _wb_label == _LAB_SUF:
                                        wiki_context = _wb.synthesis
                                    elif _wb_label == _LAB_AUX:
                                        wiki_context = _wb.synthesis
                                        wiki_is_auxiliary = True
                                    else:
                                        # Type C.3 fix
                                        # (cyc_20260424_factual_integration_c3_fix):
                                        # Calibration label == insufficient must
                                        # NOT blanket-suppress Brave escalation.
                                        # Forensic (docs/FACTUAL_INTEGRATION_
                                        # FORENSIC_20260424.md) identified this
                                        # branch as the smoking gun for the
                                        # Krillin-class regression — insufficient
                                        # Box W + no escalation = ungrounded LLM
                                        # hallucination (ZH 克林的妻子 → Hillary
                                        # Clinton).
                                        #
                                        # Re-enable escalation when the query
                                        # profile indicates factual / volatile /
                                        # non-meta-query. Exclusion list covers
                                        # the two intents where Brave cannot add
                                        # value:
                                        #   - meta_question: self-ref about
                                        #     MOBIUS itself; Box 0 is canonical.
                                        #   - casual_greeting: fast-path should
                                        #     have already returned; this is
                                        #     defense-in-depth.
                                        # creative_request is NOT in the exclude
                                        # list but is intercepted downstream by
                                        # the existing `not _is_creative` guard
                                        # at the escalation gate — so creative
                                        # queries still avoid verify path.
                                        _escalation_predicate = (
                                            _tvs_val >= 0.3
                                            or bool(getattr(appraisal,
                                                    "freshness_sensitive",
                                                    False))
                                            or _intent not in (
                                                "meta_question",
                                                "casual_greeting",
                                            )
                                        )
                                        # v0.1-rc2 calibration: for stable
                                        # direct-answer queries (LOW_STAKES_
                                        # STABLE + SUFFICIENTLY_SPECIFIED,
                                        # not freshness, low TVS), do NOT
                                        # escalate to verify on a Wikipedia
                                        # FAISS retrieval miss. Instead,
                                        # surface the retrieved chunk as
                                        # auxiliary context — the existing
                                        # WIKI_AUXILIARY prompt already
                                        # permits model-internal knowledge
                                        # fallback. Phase 5C / P9 evidence
                                        # showed the prior unconditional
                                        # escalation produced
                                        # over-verification ("I cannot
                                        # answer based on retrieved
                                        # evidence") on stable conceptual /
                                        # specialized prompts where direct
                                        # answer is appropriate.
                                        # `LOW_STAKES_STABLE` in reason_codes
                                        # already implies the KVS gate
                                        # accepted low-TVS / high-MKR for
                                        # this query (route_decision.py
                                        # only emits it on KVS PASS), so
                                        # we do not duplicate the TVS
                                        # check here. We do still gate on
                                        # `freshness_sensitive` to keep
                                        # volatile-fact queries on the
                                        # verify path.
                                        _rc_set = set(decision.reason_codes)
                                        _stable_direct_answer = (
                                            "LOW_STAKES_STABLE" in _rc_set
                                            and "SUFFICIENTLY_SPECIFIED"
                                                in _rc_set
                                            and not bool(getattr(
                                                appraisal,
                                                "freshness_sensitive",
                                                False))
                                        )
                                        if _stable_direct_answer:
                                            wiki_context = _wb.synthesis
                                            wiki_is_auxiliary = True
                                            wiki_escalate = False
                                            decision.reason_codes.append(
                                                "WIKI_INSUFFICIENT_AUX_FALLBACK"
                                            )
                                        elif _escalation_predicate:
                                            wiki_escalate = True
                                            decision.reason_codes.append(
                                                "WIKI_INSUFFICIENT_ESCALATED"
                                            )
                                        else:
                                            wiki_escalate = False
                                            decision.reason_codes.append(
                                                "WIKI_INSUFFICIENT_STOP"
                                            )
                                except Exception:
                                    # Fall back to legacy threshold gate on calibration error.
                                    if top_score >= WIKI_CONFIDENCE_THRESHOLD:
                                        wiki_context = _wb.synthesis
                                    else:
                                        wiki_escalate = True
                                        decision.reason_codes.append("WIKI_LOW_CONFIDENCE")
                            else:
                                # Legacy path (no decision layer or sup=sufficient gear with no cap limit).
                                if top_score >= WIKI_CONFIDENCE_THRESHOLD:
                                    wiki_context = _wb.synthesis
                                else:
                                    wiki_escalate = True
                                    decision.reason_codes.append("WIKI_LOW_CONFIDENCE")
                    except Exception:
                        pass
                elif _cap_forbids_retrieve:
                    decision.reason_codes.append("WIKI_SKIPPED_BY_SUPERVISOR")

                # Low confidence Wiki hit → escalate to verify route
                # Exception: creative intent — no need to verify, just
                # fall through to creative prompt without evidence
                if wiki_escalate and not _is_creative:
                    state._wiki_escalate = True
                    verify_text, verify_sources, verify_outcome = \
                        self._handle_verify(user_input, appraisal, state)
                    # cyc_20260424_pattern_c_full: propagate escalated
                    # verify_sources / verify_outcome via session state so
                    # _dispatch can surface them in RoutingResult. Fixes
                    # a pre-existing bug where the answer-path escalation
                    # returned verify_text only and lost sources.
                    state._last_escalated_verify_sources = verify_sources
                    state._last_escalated_verify_outcome = verify_outcome
                    return verify_text

                if wiki_context:
                    if _is_creative:
                        # Creative mode: evidence as background, no citation format
                        prompt = (
                            f"Background knowledge (for reference only — "
                            f"do not cite or attribute in your response):\n"
                            f"{wiki_context}\n\n"
                            f"User: {user_input}\n\n"
                            f"You are answering a creative question. "
                            f"Respond in {state.active_language}. "
                            f"Use the background knowledge naturally if helpful, "
                            f"but do not include citation numbers, source attributions, "
                            f"bracketed references, or any academic citation format "
                            f"in your response. "
                            f"Do not mention the background knowledge section or "
                            f"say the sources are irrelevant. "
                            f"Write your response as a natural, flowing text. "
                            f"{_halfstep_frame(halfstep_note, state.active_language, _chain_type, decision=decision)}"
                        )
                    else:
                        # Phase C.5 auxiliary vs sufficient presentation.
                        if wiki_is_auxiliary:
                            _tone_a = _profile_tone(_sup.presentation_profile, state.active_language) if (_profile_tone and _sup) else ""
                            prompt = (
                                f"Auxiliary context (possibly related, possibly not — NOT authoritative):\n"
                                f"{(wiki_context or '')[:1400]}\n\n"
                                f"User: {user_input}\n\n"
                                f"Respond in {state.active_language}. "
                                f"If the auxiliary context above does not directly address the "
                                f"question, rely on your own knowledge. Do NOT treat the context "
                                f"as primary evidence and do NOT cite it as authoritative. "
                                f"Keep the response concise and grounded. "
                                f"{_halfstep_frame(halfstep_note, state.active_language, _chain_type, decision=decision)} "
                                f"{_tone_a}"
                            )
                            decision.reason_codes.append("WIKI_AUXILIARY")
                        else:
                            _tone_p = _profile_tone(_sup.presentation_profile, state.active_language) if (_profile_tone and _sup) else ""
                            prompt = (
                                f"Evidence from Wikipedia (authoritative):\n"
                                f"{wiki_context}\n\n"
                                f"User: {user_input}\n\n"
                                f"Respond in {state.active_language}. "
                                f"Answer based on the evidence above. "
                                f"If the evidence conflicts with your training "
                                f"knowledge, the evidence takes priority. "
                                f"Keep the response concise. "
                                f"Do not add rhetorical questions within the answer body. "
                                f"{_halfstep_frame(halfstep_note, state.active_language, _chain_type, decision=decision)} "
                                f"{_tone_p}"
                            )
                            decision.reason_codes.append("WIKI_EVIDENCE")
                else:
                    if _is_creative:
                        # Creative mode without evidence: pure creative response
                        prompt = (
                            f"User: {user_input}\n\n"
                            f"You are answering a creative question. "
                            f"Respond in {state.active_language}. "
                            f"Write your response as a natural, flowing text. "
                            f"Do not include citation numbers or source attributions. "
                            f"{_halfstep_frame(halfstep_note, state.active_language, _chain_type, decision=decision)}"
                        )
                    else:
                        # ── Stage 6 — Box X (curated external durable
                        # knowledge) supplemental consultation. Activates
                        # only on technical/reference queries when Box W
                        # produced no evidence and the query is NOT
                        # freshness-sensitive.
                        _bx_record = self._box_x_consult(
                            query=user_input, appraisal=appraisal,
                            state=state, top_k=3,
                        )
                        _bx_block = ""
                        if _bx_record and _bx_record.get("hit"):
                            _bx_block = self._box_x_evidence_block(_bx_record)
                            decision.reason_codes.append("BOX_X_CONSULTED")
                            if _bx_block:
                                decision.reason_codes.append("BOX_X_HIT")
                                decision.reason_codes.append("BOX_X_USED")
                        elif _bx_record is not None and _bx_record.get("consulted"):
                            # Consultation actually ran but produced no hit.
                            decision.reason_codes.append("BOX_X_CONSULTED")
                            decision.reason_codes.append("BOX_X_MISS")
                        elif _bx_record is not None:
                            # Helper returned a record but the consult
                            # predicate skipped (non-technical query).
                            decision.reason_codes.append("BOX_X_SKIPPED")

                        if _bx_block:
                            prompt = (
                                f"User: {user_input}\n\n"
                                f"Respond in {state.active_language}. "
                                f"Answer the user directly in natural prose. "
                                f"Keep the response concise and grounded. "
                                f"Do not add rhetorical questions within the answer body. "
                                f"{_halfstep_frame(halfstep_note, state.active_language, _chain_type, decision=decision)}\n\n"
                                f"Terminology hints (background only — do not "
                                f"quote as a reference block; use only if they "
                                f"improve canonical-term accuracy):\n{_bx_block}"
                            )
                        else:
                            # Box M: inject session memory if available
                            _mem_ctx = self._retrieve_memory_context(user_input)
                            if _mem_ctx:
                                prompt = (
                                    f"Session context:\n{_mem_ctx}\n\n"
                                    f"User: {user_input}\n\n"
                                    f"Respond in {state.active_language}. "
                                    f"Use the session context if relevant. "
                                    f"Keep the response concise and grounded. "
                                    f"Do not add rhetorical questions within the answer body. "
                                    f"{_halfstep_frame(halfstep_note, state.active_language, _chain_type, decision=decision)}"
                                )
                                decision.reason_codes.append("MEMORY_CONTEXT")
                            else:
                                prompt = (
                                    f"User: {user_input}\n\n"
                                    f"Respond in {state.active_language}. "
                                    f"Keep the response concise and grounded. "
                                    f"Do not add rhetorical questions within the answer body. "
                                    f"{_halfstep_frame(halfstep_note, state.active_language, _chain_type, decision=decision)}"
                                )
            # ── Box A: prompt injection ──────────────────────────────
            if box_a_context and box_a_mode:
                from src.adapters.box_a_manager import BOX_A_INJECTION_TEMPLATES
                _ba_template = BOX_A_INJECTION_TEMPLATES[box_a_mode]
                _ba_injection = _ba_template.format(
                    context=box_a_context,
                    few_shot_examples=box_a_few_shot,
                )
                prompt = _ba_injection + "\n\n" + prompt
                decision.reason_codes.append(f"BOX_A_{box_a_mode}")

            # ── Box B / C: Phase G.11 reserved document-slot injection ──
            # Only runs when profile permits AND managers have hits; the
            # injection is inspectable and bounded (top 2 per box).
            if box_bc_context:
                prompt = (
                    f"{box_bc_context}\n\n"
                    f"The blocks above are reserved document-slot references "
                    f"(Box B / Box C). Cite them when relevant.\n\n"
                ) + prompt

            # Phase F v1 UX: append a thin, single-line presentation tone hint
            # to the final prompt. Does NOT re-inject governance prose; just
            # adjusts tone to "grounded but warm" (or profile-equivalent).
            # Kept outside Wiki-branch because those already got it inline.
            if (
                _sup is not None
                and _profile_tone is not None
                and "WIKI_EVIDENCE" not in decision.reason_codes
                and "WIKI_AUXILIARY" not in decision.reason_codes
            ):
                _tone_final = _profile_tone(_sup.presentation_profile, state.active_language)
                if _tone_final:
                    prompt = prompt + " " + _tone_final

            req = KernelRequest(
                user_input=user_input, prompt=prompt,
                metadata={"intent_type": _intent, "route": "answer"},
            )
            resp = self.adapter.generate(req)
            answer_text = resp.text

            # ── Box A: compliance check (RULE/CRITERIA) ──────────────
            if box_a_context and box_a_mode in ("RULE", "CRITERIA"):
                is_compliant, corrected = self._check_box_a_compliance(
                    box_a_context, answer_text, box_a_mode
                )
                if not is_compliant:
                    answer_text = corrected
                    decision.reason_codes.append("BOX_A_CORRECTED")
                    # Retry once more if still non-compliant
                    is_compliant2, corrected2 = self._check_box_a_compliance(
                        box_a_context, answer_text, box_a_mode
                    )
                    if not is_compliant2:
                        answer_text = corrected2
                        decision.reason_codes.append("BOX_A_CORRECTED_2")
                state._last_box_a["compliant"] = is_compliant

            # ── Phase B.1: V_regen guard ──────────────────────────────
            # After generating an answer via LOW_STAKES_STABLE,
            # run V_regen to check local instability.
            # If unstable → escalate to verify route.
            if (
                decision.route == "answer"
                and "KVS_PASS" in " ".join(decision.reason_codes)
                and self.adapter is not None
            ):
                model_name = getattr(self.adapter, 'model_name', 'phi4-mini:latest')
                dkvs = compute_dynamic_kvs(
                    query=user_input,
                    model_name=model_name,
                    original_answer=answer_text,
                    adapter=self.adapter,
                    rgc_state=state.rgc_state,
                )
                # Phase B.4: store RGC trace
                if dkvs.rgc is not None:
                    state._last_rgc_phi  = dkvs.rgc.phi_next
                    state._last_rgc_band = dkvs.rgc.band
                    state._last_rgc_pi   = dkvs.pi_total
                # Phase B.4: RGC band escalation
                # phi_t が verify バンド (>0.60) に達したら answer → verify
                if dkvs.rgc is not None and dkvs.rgc.band == "verify":
                    decision.reason_codes.append("RGC_BAND_ESCALATE_VERIFY")
                    state._vregen_escalate = True
                    state._vregen_propositions = getattr(dkvs.vregen, 'propositions', [])
                elif dkvs.vregen.triggered and not dkvs.vregen.stable:
                    # V_regen detected instability — escalate to verify
                    decision.reason_codes.append("RGC_ESCALATE_VERIFY")
                    decision.reason_codes.append("VREGEN_UNSTABLE")
                    # Re-route to verify (will be picked up by caller)
                    # We signal by raising a special attribute
                    state._vregen_escalate = True
                    state._vregen_propositions = dkvs.vregen.propositions
                elif dkvs.vregen.triggered:
                    decision.reason_codes.append("VREGEN_STABLE")

            return answer_text
        else:
            return halfstep_note

    def _handle_verify(
        self,
        user_input: str,
        appraisal:  AppraisalState,
        state:      SessionState,
    ):
        # ── EAL verify flow ──────────────────────────────────────────────────
        # Order: ask-before-verify guard → local RAG → web fallback → EAL → synthesis
        # Rule: retrieval failure must NOT collapse into direct answer.

        sources: List[str] = []
        web_used           = False
        local_used         = False
        why_web_triggered  = ""
        why_local_insufficient = ""

        # Guard: ask-before-verify
        # Under-specified turns should have been caught at route decision.
        # This is a belt-and-suspenders check inside the verify handler.
        if appraisal.completeness < 0.6 or appraisal.intent_clarity < 0.6:
            text = compose_non_answer_response(
                type("D", (), {"route": "ask"})(), state.active_language
            )
            return text, [], "ask_redirected"

        # ── M-1: Coreference resolution for search query ─────────────────
        search_query = user_input
        if hasattr(state, 'instant_memory') and state.instant_memory.entity_map:
            search_query = state.instant_memory.resolve_query(user_input)

        # ── Query Reformulation (Sprint 2) ──────────────────────────────
        # RCB_1 (Reformulation Entitlement + wasted LLM call elimination):
        # Skip reformulate_query when freshness_sensitive is True, since the
        # output will be discarded anyway at the verify path (see the
        # freshness_sensitive branches at lines 1471-1479, 2420-2428 where the
        # original search_query is used instead). Also skip when TVS reaches
        # TVS_HIGH_THRESHOLD (0.70) as a belt-and-suspenders guard against
        # future refactoring that may decouple freshness_sensitive from
        # high-TVS detection. See L0 v8.2 §9.1 and Phase 1 Audit 2026-04-22.
        _tvs_for_skip = (
            getattr(appraisal.kvs, "tvs", 0.0) if appraisal.kvs is not None else 0.0
        )
        _skip_reformulation = (
            appraisal.freshness_sensitive
            or _tvs_for_skip >= TVS_HIGH_THRESHOLD
        )
        _reformulated = None
        if not _skip_reformulation:
            try:
                _reformulated = reformulate_query(
                    search_query, state.active_language, adapter=self.adapter)
            except Exception:
                pass

        # ── M-3: Check verified stable facts ────────────────────────────
        if hasattr(state, 'verified_facts'):
            m3_hits = state.verified_facts.retrieve(user_input)
            if m3_hits:
                local_context_text = "\n".join(
                    f"[Verified fact] {f.claim} (source: {f.source_label})"
                    for f in m3_hits[:3]
                )
                local_used = True
                sources = [f.source_label for f in m3_hits]

        # ── Stage 1: Local RAG ───────────────────────────────────────────────
        local_context_text = local_context_text if local_used else ""
        local_hits_available = local_used
        if self.rag_pipeline and not self.rag_pipeline.is_empty:
            rag_result: RAGResult = self.rag_pipeline.query(search_query)
            local_hits_available = rag_result.sufficient
            if local_hits_available and rag_result.chunks:
                local_context_text = "\n\n".join(c.text for c in rag_result.chunks[:3])
                sources            = rag_result.sources
                local_used         = True
            if not rag_result.sufficient:
                why_local_insufficient = "Local corpus did not return sufficient evidence."
        plan = choose_retrieval_plan(
            freshness_sensitive=appraisal.freshness_sensitive,
            local_hits_available=local_hits_available,
        )

        # ── Stage 1b: Kiwix local fallback ──────────────────────────────────
        # When local RAG is insufficient and the query is NOT freshness-sensitive,
        # try Kiwix (local Wikipedia snapshot) before falling back to web search.
        # This makes the system self-contained without a Brave API key.
        adjudicated = None
        if (
            not local_used
            and self.kiwix_adapter
            and plan.use_kiwix_fallback
        ):
            _kiwix_q = (_reformulated.en_keywords
                        if _reformulated else search_query)
            raw_response  = self.kiwix_adapter.search(
                query=_kiwix_q,
                max_results=5,
                freshness_hint=None,
                preset=self.verify_preset,
            )
            normalized    = normalize_search_response(raw_response)
            adjudicated   = adjudicate_evidence(
                normalized, user_input, preset=self.verify_preset
            )
            kiwix_used = normalized.success

            if kiwix_used:
                # Phase G.10 — canonical-term bridge into verify synthesis.
                _canon_hint = ""
                try:
                    if _reformulated is not None and getattr(_reformulated, "canonical_hits", None):
                        from ..retrieval.query_reformulator import canonical_term_hint_from_hits
                        _canon_hint = canonical_term_hint_from_hits(_reformulated.canonical_hits)
                        if _canon_hint:
                            decision.reason_codes.append("CANONICAL_TERM_HINT_APPLIED")
                except Exception:
                    _canon_hint = ""
                synth = synthesize_verify_response(
                    query=user_input,
                    adjudicated=adjudicated,
                    active_language=state.active_language,
                    preset=self.verify_preset,
                    adapter=self.adapter,
                    canonical_term_hint=_canon_hint,
                )
                text           = synth["response_text"]
                verify_outcome = synth["verify_outcome"]
                sources = [s["url"] for s in synth["sources"]] or sources

                state._last_eal = {
                    "UsedLocalEvidence":           local_used,
                    "UsedWebSearch":               False,
                    "UsedKiwix":                   True,
                    "WhyWebSearchWasTriggered":    "",
                    "WhyLocalEvidenceWasInsufficient": why_local_insufficient,
                    "SearchProvider":              raw_response.provider,
                    "Admissibility":               adjudicated.admissibility,
                    "ConflictState":               adjudicated.conflict_state,
                    "FreshnessState":              adjudicated.freshness_state,
                    "Sources":                     synth["sources"],
                }
                # M-3: Store verified stable fact
                if verify_outcome == "verify_success" and hasattr(state, 'verified_facts'):
                    _kvs = getattr(appraisal, 'kvs', None)
                    _tvs = getattr(_kvs, 'tvs', 1.0) if _kvs else 1.0
                    state.verified_facts.store(
                        claim=f"Q: {user_input} -> {text[:200]}",
                        source_label=sources[0] if sources else "unknown",
                        tvs=_tvs, confidence=0.8,
                    )
                return text, sources, verify_outcome

        # ── Stage 1.5: Box X (curated external durable knowledge) ────────
        # Bounded supplemental fallback when Stage 1 (M-3 + RAG + Kiwix)
        # produced no usable evidence AND the query is NOT
        # freshness-sensitive. Box X never displaces the
        # freshness-sensitive Web/Box S path.
        if (
            not local_used
            and not appraisal.freshness_sensitive
        ):
            _bx_record = self._box_x_consult(
                query=user_input, appraisal=appraisal,
                state=state, top_k=3,
            )
            if _bx_record and _bx_record.get("hit"):
                _bx_block = self._box_x_evidence_block(_bx_record)
                if _bx_block and self.adapter:
                    bx_sources = [
                        h.get("source_uri", "")
                        for h in _bx_record.get("hits", [])
                        if h.get("source_uri")
                    ]
                    state._last_eal = {
                        "UsedLocalEvidence":              True,
                        "UsedWebSearch":                  False,
                        "UsedBoxX":                       True,
                        "WhyWebSearchWasTriggered":       "",
                        "WhyLocalEvidenceWasInsufficient": why_local_insufficient,
                        "SearchProvider":                 "box_x_curated",
                        "Admissibility":                  "supplemental",
                        "ConflictState":                  "none",
                        "FreshnessState":                 "static",
                        "Sources":                        [
                            {"url": h.get("source_uri",""),
                             "title": h.get("title",""),
                             "snippet": ""}
                            for h in _bx_record.get("hits", [])
                        ],
                    }
                    prompt = (
                        f"Question: {user_input}\n\n"
                        f"Respond in {state.active_language}. "
                        f"Answer directly in natural prose. "
                        f"Keep the response concise.\n\n"
                        f"Terminology hints (background only — do not quote "
                        f"as a reference block; use only if they improve "
                        f"canonical-term accuracy):\n{_bx_block}"
                    )
                    req = KernelRequest(user_input=user_input, prompt=prompt)
                    resp = self.adapter.generate(req)
                    text = resp.text or _bx_block
                    return text, bx_sources or sources, "box_x_supplemental"

        # ── Stage 2: Web fallback via EAL ────────────────────────────────────
        adjudicated = None
        if self.web_search_adapter and (
            not local_used
            or appraisal.freshness_sensitive
        ):
            why_web_triggered = (
                "Freshness-sensitive query requires current external evidence."
                if appraisal.freshness_sensitive
                else "Local evidence insufficient."
            )
            # RCB_1 (Reformulation Entitlement): revoke reformulation privilege
            # when TVS >= TVS_HIGH_THRESHOLD (L0 v8.2 §9.1) to prevent stale
            # knowledge contamination from reformulator. freshness_sensitive
            # (threshold 0.6) is the behavioral gate for date-stamp anchoring;
            # TVS_HIGH_THRESHOLD (0.70) is the declarative marker for
            # reformulation revocation per CC_16/RCB design.
            if appraisal.freshness_sensitive:
                from datetime import datetime as _dt
                # RCB_2 (Date-Stamp Anchoring) — already implemented, retained as-is
                _web_q = f"{search_query} {_dt.now().strftime('%Y-%m-%d')}"
            else:
                _web_q = (_reformulated.native_keywords
                          if _reformulated else search_query)
            raw_response  = self.web_search_adapter.search(
                query=_web_q,
                max_results=5,
                freshness_hint="recent" if appraisal.freshness_sensitive else None,
                preset=self.verify_preset,
            )
            normalized    = normalize_search_response(raw_response)
            adjudicated   = adjudicate_evidence(
                normalized, user_input, preset=self.verify_preset
            )
            web_used = normalized.success

            # Phase G.10 — canonical-term bridge into verify synthesis.
            _canon_hint_web = ""
            try:
                if _reformulated is not None and getattr(_reformulated, "canonical_hits", None):
                    from ..retrieval.query_reformulator import canonical_term_hint_from_hits
                    _canon_hint_web = canonical_term_hint_from_hits(_reformulated.canonical_hits)
                    if _canon_hint_web:
                        decision.reason_codes.append("CANONICAL_TERM_HINT_APPLIED")
            except Exception:
                _canon_hint_web = ""
            synth = synthesize_verify_response(
                query=user_input,
                adjudicated=adjudicated,
                active_language=state.active_language,
                preset=self.verify_preset,
                adapter=self.adapter,
                canonical_term_hint=_canon_hint_web,
            )
            text           = synth["response_text"]
            verify_outcome = synth["verify_outcome"]
            # Merge web sources into sources list (as URL strings)
            sources = [s["url"] for s in synth["sources"]] or sources

            # Attach EAL detail to state for trace enrichment
            state._last_eal = {
                "UsedLocalEvidence":           local_used,
                "UsedWebSearch":               web_used,
                "WhyWebSearchWasTriggered":    why_web_triggered,
                "WhyLocalEvidenceWasInsufficient": why_local_insufficient,
                "SearchProvider":              raw_response.provider,
                "Admissibility":               adjudicated.admissibility,
                "ConflictState":               adjudicated.conflict_state,
                "FreshnessState":              adjudicated.freshness_state,
                "Sources":                     synth["sources"],
            }
            # M-3: Store verified stable fact
            if verify_outcome == "verify_success" and hasattr(state, 'verified_facts'):
                _kvs = getattr(appraisal, 'kvs', None)
                _tvs = getattr(_kvs, 'tvs', 1.0) if _kvs else 1.0
                state.verified_facts.store(
                    claim=f"Q: {user_input} -> {text[:200]}",
                    source_label=sources[0] if sources else "unknown",
                    tvs=_tvs, confidence=0.8,
                )
            return text, sources, verify_outcome

        # ── Stage 3: Local-only synthesis (no web adapter) ───────────────────
        if self.adapter:
            if local_context_text:
                prompt = (
                    f"Evidence:\n{local_context_text}\n\n"
                    f"Question: {user_input}\n\n"
                    f"Respond in {state.active_language}. "
                    f"Give a bounded answer based only on the evidence above. "
                    f"State clearly if the evidence is incomplete."
                )
                verify_outcome = "verify_partial"
            else:
                # Box M: inject session memory into verify fallback
                _mem_ctx = self._retrieve_memory_context(user_input)
                if _mem_ctx:
                    prompt = (
                        f"Session context:\n{_mem_ctx}\n\n"
                        f"Question: {user_input}\n\n"
                        f"Respond in {state.active_language}. "
                        f"You do not have external evidence but session context "
                        f"is available. Use it if relevant. "
                        f"State clearly what you cannot confirm and why."
                    )
                else:
                    prompt = (
                        f"Question: {user_input}\n\n"
                        f"Respond in {state.active_language}. "
                        f"No external evidence was found for this question. "
                        f"If you have relevant knowledge, answer using your own knowledge "
                        f"and note that external verification was not available. "
                        f"Do not refuse to answer just because no sources were retrieved."
                    )
                verify_outcome = "verify_failed"

            req  = KernelRequest(user_input=user_input, prompt=prompt)
            resp = self.adapter.generate(req)
            text = resp.text
        else:
            if local_context_text:
                text = (
                    f"[verify:partial] "
                    f"Sources: {', '.join(sources) or 'local corpus'}. "
                    f"Evidence found but model not connected."
                )
                verify_outcome = "verify_partial"
            else:
                text = compose_non_answer_response(
                    type("D", (), {"route": "verify"})(), state.active_language
                )
                verify_outcome = "verify_failed"

        return text, sources, verify_outcome
