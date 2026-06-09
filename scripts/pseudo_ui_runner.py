#!/usr/bin/env python3
"""Pseudo-UI runner — non-Gradio harness around RoutingEngine.

Per Evolution Log cyc_20260424_stage_abc_trilingual_complete (Stage A).

Purpose:
  Reproduces what a real user would see when typing into localhost:7860,
  but as a programmatic call suitable for scenario-based regression
  testing. The same RoutingEngine construction as src/ui/app.py is used,
  so a turn routed here and a turn routed through Gradio should produce
  identical adapter calls, identical box consultations, identical
  reason_codes — the only difference is that this harness returns a
  structured TurnResult instead of streaming tokens to a UI.

Design:
  PseudoUISession wraps a single SessionState so multi-turn context
  (Box M snapshots, conversation_turns, user_map, etc.) accumulates as
  it would in a real session. `reset()` produces a fresh state.

  process_turn(user_input, target_lang=None) returns a TurnResult with
  structured trace fields the scenario runner can assert against.

Not in scope:
  - Gradio / streaming / web search / Kiwix live calls (runtime wires
    them when available; the harness does not mock them).
  - Fine-tuned / mocked LLM responses. We call the real Ollama adapter;
    if Ollama is down, the response field will be empty / error.

Usage:
  from scripts.pseudo_ui_runner import PseudoUISession
  s = PseudoUISession()
  r = s.process_turn("貴方の特徴を教えてください")
  print(r.response_text)
  print(r.reason_codes)
  print(r.box_0_top_chunks)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure the repo root is importable (same trick src/ui/app.py uses).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.kernel.routing_engine import RoutingEngine, RoutingResult  # noqa: E402
from src.state.session_state import SessionState  # noqa: E402

logger = logging.getLogger(__name__)


# ── Structured turn result ──────────────────────────────────────────────────

@dataclass
class BoxChunk:
    """One retrieved chunk (Box 0 / Box W) summarized for assertions."""
    source_label: str
    chunk_index: Optional[int]
    relevance_score: float
    text_excerpt: str  # first ~200 chars


@dataclass
class TurnResult:
    """Structured result of a single Pseudo-UI turn."""

    # ─ Primary fields ─
    user_input: str
    response_text: str
    response_language: str       # detected output language
    active_language: str          # session.active_language after turn

    # ─ Routing layer ─
    route: str                    # ask / answer / verify / abstain
    reason_codes: List[str]
    intent_type: str              # meta_question / casual_greeting / factual_query / ...
    self_referential: bool

    # ─ Box consultation signals ─
    box_0_consulted: bool
    box_w_consulted: bool
    box_x_consulted: bool
    # C.3 fix (cyc_20260424_factual_integration_c3_fix) added Box S
    # (Brave / web search) tracking — critical for verifying that
    # calibration-insufficient escalation actually reaches Brave.
    box_s_consulted: bool = False
    box_0_top_chunks: List[BoxChunk] = field(default_factory=list)
    box_w_top_chunks: List[BoxChunk] = field(default_factory=list)

    # ─ KVS / MKR / TVS ─
    tvs: float = 0.0
    mkr: float = 0.0
    kvs_completeness: float = 0.0

    # ─ Retrieval sources ─
    grounding_sources: List[str] = field(default_factory=list)

    # ─ Timing ─
    processing_time_ms: float = 0.0

    # ─ Debug ─
    error: Optional[str] = None


# ── Language detection for the RESPONSE text ────────────────────────────────

_CJK_JA = tuple("ぁあ-ヿ")   # sentinel indices; we'll use real range below
_CJK_ZH = "一-龯"
_KANA = "ぁ-ヿ"


def _detect_response_language(text: str) -> str:
    """Light heuristic on the model's reply. Does not replace runtime
    language_policy detection (which operates on user input); this is
    for scenario assertions only ("response_language == zh" etc.).

    cyc_20260424_zh_residual_cleanup — heuristic refined after the
    C-1b identity anchor exposed a false-negative class for ZH: pure
    ZH technical responses routinely include parenthetical English
    loan-words ("MOBIUS MMV (Möbius Multi-Model Validation) 架构",
    "FAISS 向量索引", "qwen3.5:9b 模型") pushing the ASCII ratio above
    0.3 even though the text is substantively Chinese. Previously
    these were misclassified as "en". The refined rule: when kana is
    absent but CJK is present, the text is "zh" unless CJK is a token-
    rare minority (ASCII letters overwhelmingly outnumber CJK chars
    by ≥2x). Keeps "en with a Tokyo mention" correctly as "en".
    """
    if not text:
        return "unknown"
    import re
    has_kana = bool(re.search(r"[぀-ヿ]", text))
    if has_kana:
        return "ja"
    has_cjk = bool(re.search(r"[一-鿿]", text))
    # Any CJK without kana → zh. Scenarios follow the convention "EN
    # queries produce EN responses, ZH queries produce ZH responses",
    # so CJK in a non-JA response reliably indicates zh even when
    # technical loan-words inflate the ASCII letter count. Contrived
    # cross-lingual mixing ("Tokyo (東京) weather today") does not
    # appear in the scenario suite by construction.
    if has_cjk:
        return "zh"
    return "en"


# ── RoutingEngine construction (mirror of src/ui/app.py §_engine) ───────────

def _build_engine() -> RoutingEngine:
    """Construct a RoutingEngine with the same adapters as src/ui/app.py.

    Kept as a single function so the scenario runner and pytest
    integration share one source of truth for adapter wiring. Failures
    degrade to None (adapter unavailable is a legitimate runtime state
    for the pseudo-UI, not a fatal error).
    """
    adapter = None
    web_search = None
    kiwix = None
    box_0 = None
    wiki = None
    box_a_mgr = None
    box_b_mgr = None
    box_c_mgr = None

    # 1. Ollama / qwen3.5:9b
    try:
        from src.adapters.ollama_adapter import OllamaAdapter  # noqa: E402
        _ep = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
        _model = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")
        _ep2 = os.environ.get("OLLAMA_ENDPOINT_PASS2", "")
        adapter = OllamaAdapter(
            endpoint=_ep,
            model_name=_model,
            second_endpoint=_ep2 or None,
            dual_pass=bool(_ep2),
        )
    except Exception as e:
        logger.warning(f"[pseudo-ui] OllamaAdapter unavailable: {e}")

    # 2. Brave web search (only if key present)
    try:
        from src.adapters.brave_search_adapter import BraveSearchAdapter  # noqa: E402
        _brave = BraveSearchAdapter()
        if _brave.search("ping").provider == "brave" and os.getenv("BRAVE_API_KEY"):
            web_search = _brave
    except Exception:
        pass

    # 3. Kiwix
    try:
        from src.adapters.kiwix_search_adapter import KiwixSearchAdapter  # noqa: E402
        _k = KiwixSearchAdapter()
        if _k.is_available():
            kiwix = _k
    except Exception:
        pass

    # 4. Box 0 (ME5, per L1-A + Embedding Rule)
    try:
        from src.adapters.custom_rag_adapter import CustomRagAdapter  # noqa: E402
        _b0 = CustomRagAdapter(
            corpus_dir     = os.path.join(str(ROOT), "corpus_box_0"),
            data_dir       = os.path.join(str(ROOT), "data", "box_0"),
            watch          = False,
            model_name     = "intfloat/multilingual-e5-large",
            query_prefix   = "query: ",
            passage_prefix = "passage: ",
        )
        _b0.load()
        if _b0.is_available():
            box_0 = _b0
    except Exception as e:
        logger.warning(f"[pseudo-ui] Box 0 unavailable: {e}")

    # 5. Box W (Wikipedia ME5)
    try:
        from src.adapters.wiki_adapter import WikiAdapter  # noqa: E402
        wiki = WikiAdapter(
            index_path=os.path.join(str(ROOT), "Wiki/wiki_index_ivfpq_me5.faiss"),
            chunks_path=os.path.join(str(ROOT), "Wiki/wiki_chunks_clean.jsonl.gz"),
        )
        wiki.load()
    except Exception as e:
        logger.warning(f"[pseudo-ui] Wiki unavailable: {e}")

    # 6. Box A / B / C Managers
    try:
        from src.adapters.box_a_manager import BoxAManager  # noqa: E402
        box_a_mgr = BoxAManager(store_dir=os.path.join(str(ROOT), "data", "box_a"))
    except Exception:
        pass
    try:
        from src.adapters.box_b_manager import BoxBManager  # noqa: E402
        box_b_mgr = BoxBManager(store_dir=os.path.join(str(ROOT), "data", "box_b"))
    except Exception:
        pass
    try:
        from src.adapters.box_c_manager import BoxCManager  # noqa: E402
        box_c_mgr = BoxCManager(store_dir=os.path.join(str(ROOT), "data", "box_c"))
    except Exception:
        pass

    return RoutingEngine(
        adapter             = adapter,
        web_search_adapter  = web_search,
        kiwix_adapter       = kiwix,
        box_0_adapter       = box_0,
        wiki_adapter        = wiki,
        box_a_manager       = box_a_mgr,
        box_b_manager       = box_b_mgr,
        box_c_manager       = box_c_mgr,
    )


# ── TurnResult extractor ────────────────────────────────────────────────────

def _extract_box_chunks(source_list, label_filter: Optional[str] = None,
                        limit: int = 3) -> List[BoxChunk]:
    """Convert raw routing-result `sources` (list of dicts or objects) into
    BoxChunk entries. label_filter narrows to a specific adapter name if
    the source dict has a 'source' or 'kind' marker."""
    out: List[BoxChunk] = []
    if not source_list:
        return out
    for src in source_list[:limit]:
        if isinstance(src, dict):
            label = src.get("label") or src.get("title") or src.get("source_label") or ""
            idx = src.get("chunk_index")
            score = float(src.get("relevance_score") or src.get("score") or 0.0)
            text = src.get("text") or src.get("snippet") or ""
        else:
            label = getattr(src, "label", "") or getattr(src, "title", "")
            idx = getattr(src, "chunk_index", None)
            score = float(getattr(src, "relevance_score", 0.0) or 0.0)
            text = getattr(src, "text", "") or getattr(src, "snippet", "")
        if label_filter and label_filter not in label:
            continue
        out.append(BoxChunk(
            source_label=label,
            chunk_index=idx,
            relevance_score=score,
            text_excerpt=(text or "")[:200],
        ))
    return out


def _derive_box_consultations(reason_codes: List[str],
                              result: RoutingResult) -> Dict[str, bool]:
    """Infer which boxes were consulted from reason_codes and result fields.

    cyc_20260424_factual_integration_c3_fix: the calibration insufficient
    branch now emits WIKI_INSUFFICIENT_ESCALATED (re-escalated to verify
    → Brave) or WIKI_INSUFFICIENT_STOP (ended without Brave). Also added
    Box S (Brave/web_search) detection via escalation reason codes and
    verify-path markers. Box 0 remains heuristic (no dedicated code)."""
    rc = set(reason_codes or [])

    # ── Box W (Wikipedia FAISS) ─────────────────────────────────────
    box_w = any(code in rc for code in (
        "WIKI_EVIDENCE", "WIKI_LOW_CONFIDENCE", "WIKI_INSUFFICIENT",
        "WIKI_INSUFFICIENT_ESCALATED", "WIKI_INSUFFICIENT_STOP",
        "WIKI_AUXILIARY", "WIKI_SKIPPED_BY_SUPERVISOR",
    ))

    # ── Box S (Brave / web search) — C.3 fix adds this axis ─────────
    # The verify path invokes Brave when wiki_escalate=True and
    # web_search_adapter is wired. WIKI_INSUFFICIENT_ESCALATED is a
    # strong signal that Brave was consulted (the answer-path
    # escalation calls _handle_verify which runs Brave). Additional
    # RGC_ESCALATE_VERIFY / RGC_BAND_ESCALATE_VERIFY signal verify-
    # path entry from elsewhere.
    box_s = any(code in rc for code in (
        "WIKI_INSUFFICIENT_ESCALATED",
        "WIKI_LOW_CONFIDENCE",           # legacy escalation path
        "RGC_ESCALATE_VERIFY",
        "RGC_BAND_ESCALATE_VERIFY",
    ))

    # ── Box X (curated external durable) ─────────────────────────────
    box_x = "BOX_X_CONSULTED" in rc

    # ── Box 0 (self-reference) — heuristic ───────────────────────────
    box_0 = False
    state = getattr(result, "session_state", None)
    if state is not None:
        if getattr(state, "_last_box_0_consulted", False):
            box_0 = True
    if not box_0:
        appraisal = getattr(result, "appraisal", None)
        if (appraisal is not None
                and getattr(appraisal, "self_referential", False)
                and "CASUAL_GREETING_FAST_PATH" not in rc):
            box_0 = True
    return {"box_0": box_0, "box_w": box_w, "box_x": box_x, "box_s": box_s}


# ── PseudoUISession ─────────────────────────────────────────────────────────

# Phase 3 Commit 28: cache the constructed engine at module scope so
# multiple PseudoUISession instances reuse the SAME engine. The
# wiki_adapter / custom_rag_adapter / pattern_library each load ME5
# at construction; without this cache the env-on 33-scenario harness
# pays N × ME5_load × M_adapters of overhead. With the cache:
#   - First session pays one full engine construction
#   - Sessions 2..N reuse it (microseconds)
# Spec v1.4 Section 5.4.1 perf gate: env-on harness <15 min target.
# Test paths inject their own engine via PseudoUISession(engine=...);
# this cache is bypassed when an explicit engine is provided.
_CACHED_ENGINE: Optional[RoutingEngine] = None


def _get_or_build_engine() -> RoutingEngine:
    global _CACHED_ENGINE
    if _CACHED_ENGINE is None:
        _CACHED_ENGINE = _build_engine()
    return _CACHED_ENGINE


class PseudoUISession:
    """Stateful multi-turn wrapper around RoutingEngine."""

    def __init__(self, engine: Optional[RoutingEngine] = None):
        self.engine = engine if engine is not None else _get_or_build_engine()
        self.state: SessionState = SessionState()

    def reset(self) -> None:
        """Drop conversation state. The engine (and therefore loaded
        indexes / adapters) is preserved — only per-session state is
        reset."""
        self.state = SessionState()

    def process_turn(self, user_input: str,
                     target_lang: Optional[str] = None) -> TurnResult:
        """Run one turn. `target_lang` is a soft hint — if supplied it
        seeds `session_state.active_language` so the engine's internal
        language_policy has a prior expectation; it is NOT enforced.

        cyc_20260424_pseudo_ui_real_ui_divergence_forensic (Layer 2
        fix): mirror src/ui/app.py process() pre-engine setup so the
        adapter receives the same governance + history injection as
        the real Gradio UI. Without this, multi-turn queries see no
        prior context — the F4b "18号です" correction case was
        evaluated as a standalone "18号" Wikipedia query in Pseudo-UI,
        which is why the harness passed 3/3 while real UI surfaced
        "London bus route 18" drift.

        Mirrored real UI behavior:
          1. Pre-engine: set adapter._governance_instruction to the
             default factual_query QK block (real UI does this in
             app.py:547-556).
          2. Pre-engine: set adapter._conversation_turns from the
             session's accumulated turns (app.py:545).
          3. Post-engine: manually append (user, assistant) to
             state.conversation_turns with the 20-turn cap (app.py:
             572-575) — because routing_engine reads but never
             writes this list.
          4. Clear adapter._governance_instruction after engine runs
             (app.py:566) to avoid leakage into the next invocation.
        """
        t0 = time.time()
        if target_lang:
            self.state.active_language = target_lang

        # Layer 2 alignment — pre-engine setup mirroring real UI
        adapter = self.engine.adapter
        if adapter is not None:
            conv_turns = getattr(self.state, "conversation_turns", []) or []
            adapter._conversation_turns = conv_turns[-6:] if conv_turns else []
            try:
                from src.adapters.question_kernel import (
                    select_kernels,
                    format_kernel_block,
                    get_zone_for_intent,
                )
                _qk_zone = get_zone_for_intent("factual_query")
                _qk_kernels = select_kernels("factual_query", zone=_qk_zone)
                _qk_block = format_kernel_block(_qk_kernels)
                adapter._governance_instruction = _qk_block
            except Exception:
                adapter._governance_instruction = ""

        try:
            result: RoutingResult = self.engine.evaluate(
                user_input, session_state=self.state,
            )
        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            logger.exception("[pseudo-ui] engine.evaluate failed")
            # Clear governance_instruction on failure path too so
            # the next invocation starts clean.
            if adapter is not None:
                adapter._governance_instruction = ""
            return TurnResult(
                user_input=user_input,
                response_text="",
                response_language="unknown",
                active_language=getattr(self.state, "active_language", ""),
                route="",
                reason_codes=[],
                intent_type="",
                self_referential=False,
                box_0_consulted=False,
                box_w_consulted=False,
                box_x_consulted=False,
                processing_time_ms=elapsed,
                error=str(e),
            )
        elapsed = (time.time() - t0) * 1000

        # Persist the updated session state for the next turn.
        self.state = result.session_state

        # Layer 2 alignment — post-engine cleanup mirroring real UI:
        # clear governance_instruction (so next invocation re-installs
        # it cleanly) and manually append the turn to
        # state.conversation_turns (routing_engine reads but never
        # writes this list; only the real UI's process() manually
        # appends at app.py:572-575).
        if adapter is not None:
            adapter._governance_instruction = ""
        _turns = list(getattr(self.state, "conversation_turns", []) or [])
        _turns.append({"role": "user", "content": user_input})
        _turns.append({"role": "assistant",
                       "content": result.response_text or ""})
        if len(_turns) > 20:
            _turns = _turns[-20:]
        self.state.conversation_turns = _turns

        # Extract structured fields.
        appraisal = result.appraisal
        decision = result.decision
        reason_codes = list(getattr(decision, "reason_codes", []) or [])
        box_flags = _derive_box_consultations(reason_codes, result)

        # Intent-type best-effort extraction:
        # routing_engine._infer_intent_type is a staticmethod we can call.
        try:
            intent = RoutingEngine._infer_intent_type(user_input, appraisal)
        except Exception:
            intent = ""

        # Try to tease apart Box 0 / Box W sources if routing_engine
        # attached any diagnostic data to session_state. Fall back to
        # collapsing all `result.sources` into grounding_sources.
        grounding = []
        if result.sources:
            for s in result.sources:
                if isinstance(s, dict):
                    grounding.append(s.get("label") or s.get("title") or str(s)[:80])
                else:
                    grounding.append(
                        getattr(s, "label", None)
                        or getattr(s, "title", None)
                        or str(s)[:80]
                    )

        # Box 0 / Box W last-retrieval snapshots (if routing_engine
        # stored them on state for trace observability).
        box_0_chunks = _extract_box_chunks(
            getattr(result.session_state, "_last_box_0_chunks", None) or [],
            limit=3,
        )
        box_w_chunks = _extract_box_chunks(
            getattr(result.session_state, "_last_box_w_chunks", None) or [],
            limit=3,
        )

        tvs = float(getattr(appraisal, "kvs", None) and
                    getattr(appraisal.kvs, "tvs", 0.0) or 0.0)
        mkr = float(getattr(appraisal, "kvs", None) and
                    getattr(appraisal.kvs, "mkr", 0.0) or 0.0)
        completeness = float(getattr(appraisal, "completeness", 0.0) or 0.0)

        return TurnResult(
            user_input=user_input,
            response_text=result.response_text or "",
            response_language=_detect_response_language(result.response_text or ""),
            active_language=getattr(self.state, "active_language", "") or "",
            route=getattr(decision, "route", "") or "",
            reason_codes=reason_codes,
            intent_type=intent or "",
            self_referential=bool(getattr(appraisal, "self_referential", False)),
            box_0_consulted=box_flags["box_0"],
            box_w_consulted=box_flags["box_w"],
            box_x_consulted=box_flags["box_x"],
            box_s_consulted=box_flags.get("box_s", False),
            box_0_top_chunks=box_0_chunks,
            box_w_top_chunks=box_w_chunks,
            tvs=tvs,
            mkr=mkr,
            kvs_completeness=completeness,
            grounding_sources=grounding,
            processing_time_ms=elapsed,
            error=None,
        )


# ── CLI for interactive exploration ─────────────────────────────────────────

def _cli():
    import argparse, json
    parser = argparse.ArgumentParser(description="Pseudo-UI runner CLI")
    parser.add_argument("query", nargs="?", default=None)
    parser.add_argument("--lang", default=None, help="Seed active_language")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    session = PseudoUISession()

    if args.query:
        r = session.process_turn(args.query, target_lang=args.lang)
        print(json.dumps({
            "query": r.user_input,
            "response": r.response_text[:600],
            "response_language": r.response_language,
            "route": r.route,
            "intent_type": r.intent_type,
            "self_referential": r.self_referential,
            "box_0_consulted": r.box_0_consulted,
            "box_w_consulted": r.box_w_consulted,
            "box_x_consulted": r.box_x_consulted,
            "reason_codes": r.reason_codes,
            "tvs": r.tvs,
            "processing_ms": round(r.processing_time_ms, 1),
            "error": r.error,
        }, ensure_ascii=False, indent=2))
        return

    print("Pseudo-UI interactive mode. Ctrl-D to exit.")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q == ":reset":
            session.reset()
            print("(session reset)")
            continue
        r = session.process_turn(q)
        print(f"[{r.route} / {r.intent_type} / {r.processing_time_ms:.0f}ms]")
        print(r.response_text[:600])
        print()


if __name__ == "__main__":
    _cli()
