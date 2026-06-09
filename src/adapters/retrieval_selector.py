#!/usr/bin/env python3
"""
retrieval_selector.py — MOBIUS MMV Phase C: 3-stage fallback integration
src/adapters/retrieval_selector.py

Executes fallback search in the order Box A -> Box W -> Box S.

Fallback order (phase_c_spec_v2_2.docx section 2.1):
  verify route triggered
    -> Stage 1: Box A (custom_index.faiss)
        sufficient -> to EAL
        insufficient ->
    -> Stage 2: Box W (wiki_index_ivfpq.faiss; legacy selector id B)
        sufficient -> to EAL
        insufficient ->
    -> Stage 3: Box S (Brave Search API) <- freshness_sensitive only
        insufficient -> verify_failed

Design principles:
  - Only Source[] is passed to EAL. RetrievalSelector does not synthesize.
  - Answer Entitlement decisions are made by the L0 control layer.
  - Box S fires only when the freshness_sensitive flag is True.
  - If a Box's is_available() returns False, it is automatically skipped.
  - Feature flags allow enabling/disabling individual Boxes (section 2.2 suite pack).

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : phase_c_spec_v2_2.docx §2, §2.1, §2.2, §7
"""

from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path

# -- Memory Capsule search (Phase E E.4) ---------------------------------------
_mem_dir = str(_Path(__file__).parent.parent / "memory")
if _mem_dir not in _sys.path:
    _sys.path.insert(0, _mem_dir)
try:
    from memory_indexer import MemoryIndexer as _MemoryIndexer
    _CAPSULE_SEARCH_AVAILABLE = True
except ImportError:
    _MemoryIndexer             = None
    _CAPSULE_SEARCH_AVAILABLE  = False

import logging
import os
import time
try:
    from src.adapters.kiwix_adapter import KiwixAdapter as _KiwixAdapter
    _KIWIX_AVAILABLE = True
except ImportError:
    _KiwixAdapter = None
    _KIWIX_AVAILABLE = False
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

# -- Type definitions (conforming to 08_api_types.docx section 9, shared with wiki_adapter.py) --

@dataclass
class Source:
    source_type:     str
    label:           str
    uri:             str
    chunk_index:     Optional[int]   = None
    retrieved_at:    str             = ""
    relevance_score: Optional[float] = None

    def __post_init__(self):
        if not self.retrieved_at:
            self.retrieved_at = datetime.now(timezone.utc).isoformat()


@dataclass
class RetrievalResult:
    sources:   List[Source]
    outcome:   str    # "success" | "partial" | "failed"
    synthesis: str


# -- Selection result ----------------------------------------------------------

@dataclass
class SelectorResult:
    """
    Return value of RetrievalSelector.select().

    Attributes:
        result         : The final adopted RetrievalResult
        box_used       : The Box adopted ("A" | "B" | "S" | None);
                        "B" is the legacy wire id for Box W/Wikipedia
        sufficient     : Sufficiency determination (True = can be passed to EAL)
        score          : Sufficiency score of the adopted Box
        fallback_trace : Log of fallback progression
        latency_ms     : Total search time
    """
    result:         RetrievalResult
    box_used:       Optional[str]
    sufficient:     bool
    score:          float
    fallback_trace: List[dict] = field(default_factory=list)
    latency_ms:     float = 0.0
    # Phase C.5 additions — optional, do not change existing semantics when None.
    box_w_label:        Optional[str]  = None   # insufficient | auxiliary | sufficient
    box_w_calibration:  Optional[dict] = None   # serialized calibration summary


# -- Feature Flags -------------------------------------------------------------

@dataclass
class BoxFlags:
    """
    Section 2.2 suite pack configuration.
    Can be overridden via environment variables MOBIUS_BOX_A / W / S.

        MOBIUS_BOX_A=0 -> Box A disabled
        MOBIUS_BOX_W=0 -> Box W disabled
        MOBIUS_BOX_B=0 -> legacy alias for disabling Box W
        MOBIUS_BOX_S=0 -> Box S disabled (full privacy mode, etc.)
    """
    box_0:     bool = True    # Box 0 (System canonical). Disabled with MOBIUS_BOX_0=0
    box_a:     bool = True
    box_b:     bool = True    # Legacy field name for Box W (Wikipedia)
    box_s:     bool = True
    box_kiwix: bool = True   # Box W complement. Disabled with MOBIUS_BOX_KIWIX=0

    @classmethod
    def from_env(cls) -> "BoxFlags":
        def _flag(key: str, default: bool) -> bool:
            val = os.environ.get(key, "").strip().lower()
            if val in ("0", "false", "no", "off"):
                return False
            if val in ("1", "true", "yes", "on"):
                return True
            return default
        box_w_enabled = _flag("MOBIUS_BOX_W", _flag("MOBIUS_BOX_B", True))
        return cls(
            box_0     = _flag("MOBIUS_BOX_0",     True),
            box_a     = _flag("MOBIUS_BOX_A",     True),
            box_b     = box_w_enabled,
            box_s     = _flag("MOBIUS_BOX_S",     True),
            box_kiwix = _flag("MOBIUS_BOX_KIWIX", True),
        )


# -- Box S (Brave Search API) -------------------------------------------------

class _BraveSearchAdapter:
    """
    Box S: Brave Search API wrapper.
    For freshness_sensitive queries only.

    Requires the BRAVE_API_KEY environment variable.
    If not set, is_available() returns False.
    """

    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
    DEFAULT_COUNT = 5
    SUFFICIENCY_THRESHOLD = 0.0  # Box S considers any retrieval as sufficient

    def __init__(self):
        self._api_key = os.environ.get("BRAVE_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._api_key)

    def retrieve(self, query: str, top_k: int = DEFAULT_COUNT) -> RetrievalResult:
        if not self._api_key:
            return RetrievalResult(sources=[], outcome="failed", synthesis="")
        try:
            import requests
            resp = requests.get(
                self.ENDPOINT,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": self._api_key,
                },
                params={"q": query, "count": top_k},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[BoxS] Brave Search failed: {e}")
            return RetrievalResult(sources=[], outcome="failed", synthesis="")

        results = data.get("web", {}).get("results", [])
        if not results:
            return RetrievalResult(sources=[], outcome="failed", synthesis="")

        now     = datetime.now(timezone.utc).isoformat()
        sources = []
        texts   = []
        for r in results[:top_k]:
            title       = r.get("title", "")
            url         = r.get("url", "")
            description = r.get("description", "")
            sources.append(Source(
                source_type     = "web_search",
                label           = title,
                uri             = url,
                retrieved_at    = now,
                relevance_score = None,  # Brave does not return numeric scores
            ))
            texts.append(f"{title}\n{description}" if description else title)

        outcome = "success" if len(sources) == top_k else "partial"
        return RetrievalResult(
            sources   = sources,
            outcome   = outcome,
            synthesis = "\n\n".join(texts),
        )

    def get_sufficiency_score(self, result: RetrievalResult) -> float:
        # Box S is sufficient if retrieved count > 0
        return 1.0 if result.sources else 0.0


# -- RetrievalSelector ---------------------------------------------------------

class RetrievalSelector:
    """
    Integrates 3-stage fallback search: Box A -> W -> S.

    Usage:
        from src.adapters.wiki_adapter import WikiAdapter
        from src.adapters.custom_rag_adapter import CustomRagAdapter
        from src.adapters.retrieval_selector import RetrievalSelector

        selector = RetrievalSelector(
            box_a = custom_rag_adapter,
            box_b = wiki_adapter,
        )
        result = selector.select(
            query              = "What is the project deadline?",
            freshness_sensitive = False,
        )
        if result.sufficient:
            # Pass result.result.sources to EAL
            pass
        else:
            # verify_failed -> abstain route
            pass

    Args:
        box_a: CustomRagAdapter instance (already loaded)
        box_b: WikiAdapter instance (already loaded). Legacy parameter name;
               this is the Box W / Wikipedia adapter.
        box_s: _BraveSearchAdapter instance (optional)
        flags: BoxFlags (auto-detected from environment variables if omitted)
        top_k: Number of search results per Box
    """

    def __init__(
        self,
        box_0=None,
        box_a=None,
        box_b=None,
        box_s=None,
        flags: Optional[BoxFlags] = None,
        top_k: int = 5,
        box_x_store=None,
    ):
        self._box_0  = box_0   # Box 0 (System canonical) — self-referential priority
        self._box_a  = box_a
        self._box_b  = box_b
        self._memory = None  # Box M (Phase E) — set after init if available
        self._box_s  = box_s or _BraveSearchAdapter()
        # Box W complement: KiwixAdapter (auto-detect ZIM, source_type="local_rag")
        self._box_kiwix = (
            _KiwixAdapter() if _KIWIX_AVAILABLE else None
        )
        self._flags  = flags or BoxFlags.from_env()
        self._top_k  = top_k
        # Box X (curated external durable knowledge) — optional. When
        # provided AND populated AND the query is technical, it acts as
        # a supplemental candidate after W/A/0. Never overrides W/A/0
        # when those were sufficient. Disabled with MOBIUS_BOX_X=0.
        self._box_x_store = box_x_store
        self._box_x_enabled = (
            os.environ.get("MOBIUS_BOX_X", "1").strip().lower()
            not in ("0", "false", "no", "off")
        )

    # -- Public API ------------------------------------------------------------

    def select(
        self,
        query:               str,
        freshness_sensitive: bool = False,
        self_referential:    bool = False,
        top_k:               Optional[int] = None,
        *,
        appraisal_hints:     Optional[dict] = None,
        retrieval_profile:   Optional[object] = None,
    ) -> SelectorResult:
        """
        Execute 3-stage fallback search and return SelectorResult.

        Args:
            query               : Search query (English recommended. Non-English should be pre-translated via ArgosBridge)
            freshness_sensitive : Box S fires only when True
            top_k               : Number of search results per Box (defaults to constructor value if omitted)
            retrieval_profile   : Phase G optional profile. When provided, the
                                  selector respects allow_wiki (skip Stage 2/2b)
                                  and allow_search (skip Stage 3). Unset or
                                  balanced_default → no behavior change.

        Returns:
            SelectorResult
              .sufficient=True  -> pass result.sources to EAL
              .sufficient=False -> verify_failed (L0 decides abstain, etc.)
        """
        k = top_k or self._top_k
        t0 = time.time()
        trace: list[dict] = []

        # Phase G: derive profile preferences (None → balanced_default).
        _allow_wiki   = True
        _allow_search = True
        _profile_id_str = "balanced_default"
        if retrieval_profile is not None:
            _allow_wiki = bool(getattr(retrieval_profile, "allow_wiki", True))
            _allow_search = bool(getattr(retrieval_profile, "allow_search", True))
            _profile_id_str = getattr(retrieval_profile, "profile_id", "unknown")
        if _profile_id_str != "balanced_default":
            trace.append({
                "box": "profile", "id": _profile_id_str,
                "allow_wiki": _allow_wiki, "allow_search": _allow_search,
            })

        # Phase G.1: compute preference-merge hints (bounded priority shaping).
        # balanced_default → PreferenceHints with no effect → no behavior change.
        try:
            from src.kernel.profiles import compute_preference_merge as _compute_pm
            _pref_hints = _compute_pm(retrieval_profile)
        except Exception:
            _pref_hints = None
        # Inspectability state for preference merge. Populated during the
        # stage sequence and exposed via trace.
        _box_m_had_hit: bool = False
        _box_a_had_any_result: bool = False

        # -- Stage 0: Box M (Memory Capsule) -----------------------------------
        # Query verified knowledge from past sessions with highest priority.
        # Even on hit, Box A/B/C fallback is maintained.
        if (
            _CAPSULE_SEARCH_AVAILABLE
            and self._memory is not None
            and hasattr(self._memory, "search")
        ):
            try:
                _caps = self._memory.search(
                    query        = query,
                    top_k        = k,
                    min_salience = 0.40,
                )
                if _caps:
                    _box_m_had_hit = True  # Phase G.1: preference-merge signal
                    _cap_sources = [
                        Source(
                            source_type     = "memory_capsule",
                            label           = c.get("memory_type","capsule"),
                            uri             = f"capsule://{c.get('capsule_id','')}",
                            relevance_score = c.get("_search_score", 0.0),
                        )
                        for c in _caps
                    ]
                    _cap_text = '\n\n'.join(
                        c.get("memory_text","") for c in _caps if c.get("memory_text")
                    )
                    _cap_result = RetrievalResult(
                        sources   = _cap_sources,
                        outcome   = "success",
                        synthesis = f"[Memory] {_cap_text}",
                    )
                    score = max((c.get("_search_score",0.0) for c in _caps), default=0.0)
                    trace.append({
                        "box": "M", "score": score, "sufficient": True,
                        "outcome": "success", "capsules": len(_caps)
                    })
                    logger.debug(f"[Selector] Box M hit: {len(_caps)} capsules")
                    # Box M is returned as reference info (sufficient=False to proceed to fallback)
                    # Setting sufficient=True would skip the remaining
                    # evidence stages.
                    # Box M results are prepended to synthesis and merged
                    # with Box A/W/S evidence when available.
                    # Currently only recorded in trace (full integration in Phase F)
            except Exception as _mem_exc:
                logger.debug(f"[Selector] Box M error (ignored): {_mem_exc}")

        # -- Stage 0.5: Box 0 (System canonical) ------------------------------
        # Retrieves canonical documents with highest priority for self_referential queries.
        # Even when self_referential=False, Box 0 is attempted but returns immediately only when sufficient.
        if (
            self._flags.box_0
            and self._box_0 is not None
            and self._box_0.is_available()
        ):
            r, score, ok = self._try_box("0", self._box_0, query, k)
            trace.append({"box": "0", "score": score, "sufficient": ok,
                           "outcome": r.outcome})
            if ok and (self_referential or score >= 0.55):
                return SelectorResult(
                    result=r, box_used="0", sufficient=True, score=score,
                    fallback_trace=trace,
                    latency_ms=round((time.time() - t0) * 1000, 1),
                )
        else:
            reason = (
                "disabled by flag" if not self._flags.box_0
                else "not available" if self._box_0 is None
                else "is_available=False"
            )
            trace.append({"box": "0", "skipped": True, "reason": reason})
            logger.debug(f"[Selector] Box 0 skipped: {reason}")

        # -- Stage 1: Box A ---------------------------------------------------
        if self._flags.box_a and self._box_a is not None \
                and self._box_a.is_available():
            r, score, ok = self._try_box("A", self._box_a, query, k)
            # Phase G.1: track whether Box A returned *any* sources, even
            # when not sufficient. Consumed by workspace_first preference merge.
            try:
                _box_a_had_any_result = bool(getattr(r, "sources", None))
            except Exception:
                _box_a_had_any_result = False
            trace.append({"box": "A", "score": score, "sufficient": ok,
                           "outcome": r.outcome})
            if ok:
                # Phase G.2: supplementary Box W consultation AFTER Box A
                # success. Runs only when the active profile explicitly opts
                # in via `supplementary_w_after_inner_hit=True` (verify_heavy /
                # wide_recall). Primary result stays Box A; the supplementary
                # call is non-terminal, purely inspectable via trace, and
                # bounded by the same `_allow_wiki` and freshness gates used
                # elsewhere. If Box W fails or is unavailable, we proceed
                # silently — never fabricate.
                self._maybe_run_supplementary_w(
                    query=query,
                    k=k,
                    pref_hints=_pref_hints,
                    allow_wiki=_allow_wiki,
                    freshness_sensitive=freshness_sensitive,
                    profile_id=_profile_id_str,
                    trace=trace,
                )
                return SelectorResult(
                    result=r, box_used="A", sufficient=True, score=score,
                    fallback_trace=trace,
                    latency_ms=round((time.time() - t0) * 1000, 1),
                )
        else:
            reason = (
                "disabled by flag" if not self._flags.box_a
                else "not available" if self._box_a is None
                else "is_available=False"
            )
            trace.append({"box": "A", "skipped": True, "reason": reason})
            logger.debug(f"[Selector] Box A skipped: {reason}")

        # -- Stage 2: Box W ---------------------------------------------------
        # When freshness_sensitive=True, even if Box W is sufficient, do not return; proceed to Stage 3.
        # Reason: Wikipedia snapshots do not contain real-time data.
        #         Box S (Brave Search) needs to overwrite with latest values.
        #
        # Phase C.5 (2026-04-20): Box W is calibrated to a 3-value label.
        # When appraisal_hints is supplied, "sufficient" requires semantic
        # admissibility, not just retrieval hit. "auxiliary" is held over as a
        # bounded fallback (same treatment as the freshness holdover).
        _box_w_result = None
        _box_w_label: Optional[str] = None
        _box_w_calibration: Optional[dict] = None
        # Phase G: profile can disable Box W. Balanced_default → _allow_wiki=True
        # → no change. memory_first → _allow_wiki=False → skip stage 2.
        #
        # Phase G.1: bounded preference merge. If Box M hit (memory_first) or
        # Box A already returned results (workspace_first), defer Stage 2 as
        # optional widening. Freshness does NOT use this deferral — freshness
        # takes its own path at Stage 3 regardless.
        _g1_defer_wiki_note: Optional[str] = None
        if _pref_hints is not None and _allow_wiki and not freshness_sensitive:
            if _pref_hints.defer_wiki_if_memory_hit and _box_m_had_hit:
                _g1_defer_wiki_note = (
                    f"profile_defers_wiki_due_to_memory_first "
                    f"(profile:{_profile_id_str})"
                )
            elif _pref_hints.defer_wiki_if_workspace_hit and _box_a_had_any_result:
                _g1_defer_wiki_note = (
                    f"profile_defers_wiki_due_to_workspace_first "
                    f"(profile:{_profile_id_str})"
                )
        if not _allow_wiki:
            trace.append({"box": "W", "skipped": True,
                          "reason": f"disabled by profile:{_profile_id_str}"})
        elif _g1_defer_wiki_note is not None:
            trace.append({"box": "W", "skipped": True,
                          "reason": _g1_defer_wiki_note,
                          "phase_g1": True})
        elif self._flags.box_b and self._box_b is not None \
                and self._box_b.is_available():
            r, score, ok = self._try_box("B", self._box_b, query, k)
            _box_w_trace_entry = {"box": "B", "score": score, "sufficient": ok,
                                   "outcome": r.outcome}
            trace.append(_box_w_trace_entry)

            # Phase C.5 calibration — only engaged if appraisal_hints provided.
            if appraisal_hints is not None and r is not None and r.sources:
                try:
                    from .box_w_calibration import (
                        BoxBCalibrationInputs as _BBI,
                        calibrate_box_b as _calibrate,
                        LABEL_SUFFICIENT as _LAB_SUF,
                        LABEL_AUXILIARY as _LAB_AUX,
                        LABEL_INSUFFICIENT as _LAB_INS,
                    )
                    _top_source = r.sources[0] if r.sources else None
                    _title = getattr(_top_source, "label", "") if _top_source else ""
                    _chunk = (r.synthesis or "")[:4000]
                    _top2_score = 0.0
                    if len(r.sources) >= 2:
                        _top2_score = float(getattr(r.sources[1], "relevance_score", 0.0) or 0.0)
                    _calib = _calibrate(_BBI(
                        query=query,
                        chunk_text=_chunk,
                        chunk_title=_title,
                        top1_score=float(score),
                        top2_score=_top2_score,
                        self_referential=bool(appraisal_hints.get("self_referential", self_referential)),
                        freshness_sensitive=bool(appraisal_hints.get("freshness_sensitive", freshness_sensitive)),
                        context_dependent=bool(appraisal_hints.get("context_dependent", False)),
                        tvs_band=str(appraisal_hints.get("tvs_band", "LOW")).upper(),
                        user_correction=bool(appraisal_hints.get("user_correction", False)),
                        meta_recall_intent=bool(appraisal_hints.get("meta_recall_intent", False)),
                        route_hint=str(appraisal_hints.get("route_hint", "answer")),
                        active_context_present=bool(appraisal_hints.get("active_context_present", False)),
                        box_m_hit=bool(appraisal_hints.get("box_m_hit", False)),
                        box_0_hit=bool(appraisal_hints.get("box_0_hit", False)),
                        box_a_hit=bool(appraisal_hints.get("box_a_hit", False)),
                    ))
                    _box_w_label = _calib.label
                    _box_w_calibration = _calib.to_dict()
                    trace.append({
                        "box": "B-calibration",
                        "label": _calib.label,
                        "ess_b": round(_calib.ess_b, 4),
                        "hard_guards": list(_calib.hard_guards),
                    })
                    # Override ok based on calibration:
                    #  sufficient  -> ok=True  (may still be gated by freshness)
                    #  auxiliary   -> treated as holdover (ok=False terminal, but keep as fallback)
                    #  insufficient-> ok=False (skip Box W)
                    if _calib.label == _LAB_SUF:
                        ok = True
                    elif _calib.label == _LAB_AUX:
                        # Not terminal, but hold as bounded fallback
                        ok = False
                        _box_w_result = (r, score)
                    else:  # insufficient
                        ok = False
                    # Keep trace consistent with calibrated decision so that
                    # downstream Stage 2b "was_sufficient" check is honest.
                    _box_w_trace_entry["sufficient"] = ok
                except Exception as _e:
                    logger.debug(f"[Selector] Box W calibration skipped: {_e}")

            if ok and not freshness_sensitive:
                # freshness_sensitive=False: Return immediately on Box W sufficiency
                return SelectorResult(
                    result=r, box_used="B", sufficient=True, score=score,
                    fallback_trace=trace,
                    latency_ms=round((time.time() - t0) * 1000, 1),
                    box_w_label=_box_w_label,
                    box_w_calibration=_box_w_calibration,
                )
            elif ok:
                # freshness_sensitive=True: Hold Box W result and proceed to Stage 3
                _box_w_result = (r, score)

        # -- Stage 2b: Box Kiwix (Box W full-text complement) -----------------
        # When Box W (FAISS) is sufficient and freshness_sensitive=False,
        # complements with full text via Kiwix retrieval. source_type="local_rag" (Frozen v1.0 maintained)
        # When Box W is insufficient, delegates to Stage 3 (Brave).
        _box_w_was_sufficient = (
            "B" in [t.get("box") for t in trace if t.get("sufficient")]
        )
        if (
            _box_w_was_sufficient
            and not freshness_sensitive
            and _allow_wiki                # Phase G: profile gate on Box W family (Kiwix is its complement)
            and self._flags.box_b          # Linked with Box W (legacy BoxFlags.box_b name) as its complement
            and self._flags.box_kiwix      # Can be individually disabled with MOBIUS_BOX_KIWIX=0
            and self._box_kiwix is not None
            and self._box_kiwix.is_available()
        ):
            _kr, _ks, _ko = self._try_box("B-Kiwix", self._box_kiwix, query, k)
            trace.append({
                "box": "B-Kiwix", "score": _ks,
                "sufficient": _ko, "outcome": _kr.outcome,
            })
            if _ko:
                logger.info("[Selector] Box Kiwix sufficient.")
                return SelectorResult(
                    result=_kr, box_used="B-Kiwix", sufficient=True,
                    score=_ks, fallback_trace=trace,
                    latency_ms=round((time.time() - t0) * 1000, 1),
                )
        else:
            reason = (
                "disabled by flag" if not self._flags.box_kiwix
                else "not available" if self._box_kiwix is None
                else "is_available=False"
            )
            trace.append({"box": "B-Kiwix", "skipped": True, "reason": reason})
            logger.debug(f"[Selector] Box B-Kiwix skipped: {reason}")

        # -- Stage 2.5: Box X (curated external durable knowledge) ------------
        # Bounded supplemental consultation. Activates only when:
        #   - a Box X store is wired,
        #   - the store is populated,
        #   - the query is technical/reference (or appraisal_hints flag),
        #   - we have not already returned a sufficient result.
        # Box X CANNOT override Box W/A/0 results that were already
        # sufficient (those returned earlier). It CAN return its own
        # result when the upstream stages did not yield one and the
        # query is not freshness-sensitive.
        _box_x_consultation = self._maybe_consult_box_x(
            query=query,
            top_k=k,
            appraisal_hints=appraisal_hints,
            freshness_sensitive=freshness_sensitive,
            trace=trace,
        )
        if (
            _box_x_consultation is not None
            and _box_x_consultation.has_hit()
            and not freshness_sensitive
            and _box_w_result is None
        ):
            _bx_sources, _bx_synthesis, _bx_score = (
                self._build_box_x_result(_box_x_consultation, now=datetime.now(timezone.utc).isoformat())
            )
            if _bx_sources:
                trace.append({
                    "box": "X", "score": _bx_score,
                    "sufficient": True, "outcome": "success",
                    "note": "box_x_used",
                })
                return SelectorResult(
                    result=RetrievalResult(
                        sources=_bx_sources,
                        outcome="success" if len(_bx_sources) == k else "partial",
                        synthesis=_bx_synthesis,
                    ),
                    box_used="X",
                    sufficient=True,
                    score=_bx_score,
                    fallback_trace=trace,
                    latency_ms=round((time.time() - t0) * 1000, 1),
                )

        # -- Stage 3: Box S ---------------------------------------------------
        # When freshness_sensitive=True, always attempt Box S even if Box W was sufficient.
        # Reason: Wikipedia snapshots do not contain real-time financial data.
        #         freshness_sensitive queries always require the latest sources.
        # When freshness_sensitive=False, Box S is skipped unless the route is
        # explicitly freshness-sensitive.
        # Phase G.1: freshness is a hard invariant. When the query is truly
        # freshness-sensitive and a Box S backend is available, Box S MUST
        # fire regardless of profile allow_search=False. Profiles are
        # preferences, not sovereign controllers over constitutional behavior.
        _freshness_forces_search = (
            freshness_sensitive
            and not _allow_search
            and self._flags.box_s
            and self._box_s is not None
            and self._box_s.is_available()
        )
        if _freshness_forces_search:
            trace.append({
                "box": "profile_override",
                "reason": (f"freshness overrides profile:{_profile_id_str} "
                           f"allow_search=False"),
                "phase_g1": True,
            })
        box_s_should_fire = (
            (_allow_search or _freshness_forces_search)   # Phase G.1 override
            and self._flags.box_s
            and self._box_s.is_available()
            and freshness_sensitive  # freshness_sensitive only
        )
        if box_s_should_fire:
            r, score, ok = self._try_box("S", self._box_s, query, k)
            trace.append({"box": "S", "score": score, "sufficient": ok,
                           "outcome": r.outcome})
            if ok:
                return SelectorResult(
                    result=r, box_used="S", sufficient=True, score=score,
                    fallback_trace=trace,
                    latency_ms=round((time.time() - t0) * 1000, 1),
                )
        else:
            if not _allow_search and not freshness_sensitive:
                reason = f"disabled by profile:{_profile_id_str}"
            elif not self._flags.box_s:
                reason = "disabled by flag"
            elif not freshness_sensitive:
                reason = "not freshness_sensitive"
            elif self._box_s is None or not self._box_s.is_available():
                reason = "BRAVE_API_KEY not set"
            else:
                reason = "unavailable"
            trace.append({"box": "S", "skipped": True, "reason": reason})
            logger.debug(f"[Selector] Box S skipped: {reason}")

        # -- Box S failed for freshness_sensitive -> fall back to Box W result --
        #    Phase C.5: When the holdover is an AUXILIARY calibration, expose
        #    sufficient=False with box_w_label=auxiliary so EAL treats it as
        #    bounded-only rather than primary evidence.
        if _box_w_result is not None:
            r, score = _box_w_result
            _is_auxiliary = (_box_w_label == "auxiliary")
            logger.info(
                f"[Selector] Box S failed. Falling back to Box W result. "
                f"score={score:.4f} label={_box_w_label or 'legacy'}"
            )
            trace.append({
                "box": "B_fallback", "score": score,
                "sufficient": not _is_auxiliary,
                "label": _box_w_label,
            })
            return SelectorResult(
                result=r, box_used="B",
                sufficient=(not _is_auxiliary),
                score=score,
                fallback_trace=trace,
                latency_ms=round((time.time() - t0) * 1000, 1),
                box_w_label=_box_w_label,
                box_w_calibration=_box_w_calibration,
            )

        # -- verify_failed -----------------------------------------------------
        logger.info(
            f"[Selector] verify_failed. query={query[:50]!r} "
            f"freshness={freshness_sensitive}"
        )
        return SelectorResult(
            result=RetrievalResult(sources=[], outcome="failed", synthesis=""),
            box_used=None,
            sufficient=False,
            score=0.0,
            fallback_trace=trace,
            box_w_label=_box_w_label,
            box_w_calibration=_box_w_calibration,
            latency_ms=round((time.time() - t0) * 1000, 1),
        )

    # -- Box X consultation (Stage 2.5) ---------------------------------------

    def _maybe_consult_box_x(
        self,
        *,
        query: str,
        top_k: int,
        appraisal_hints,
        freshness_sensitive: bool,
        trace: list,
    ):
        """Consult Box X bounded supplemental layer.

        Returns the BoxXConsultation object on success, or None when the
        consultation was skipped. Always appends an inspectable trace
        entry; never raises.
        """
        if not self._box_x_enabled or self._box_x_store is None:
            trace.append({"box": "X", "skipped": True,
                          "reason": "box_x_not_wired",
                          "note": "box_x_skipped"})
            return None
        if freshness_sensitive:
            trace.append({"box": "X", "skipped": True,
                          "reason": "freshness_sensitive_uses_box_s",
                          "note": "box_x_skipped"})
            return None
        # Optional appraisal-side hints. Callers may pass:
        #   technical_hint:   bool — query is technical/definitional
        #   reference_intent: bool — query is reference-seeking
        technical_hint = False
        reference_intent = False
        if isinstance(appraisal_hints, dict):
            technical_hint = bool(appraisal_hints.get("technical_hint", False))
            reference_intent = bool(appraisal_hints.get("reference_intent", False))
        try:
            from src.retrieval.box_x_consultation import consult_box_x
        except Exception as exc:   # noqa: BLE001
            trace.append({"box": "X", "skipped": True,
                          "reason": f"consult_module_unavailable:{exc}",
                          "note": "box_x_skipped"})
            return None
        try:
            out = consult_box_x(
                query=query,
                store=self._box_x_store,
                top_k=top_k,
                reference_intent=reference_intent,
                technical_hint=technical_hint,
            )
        except Exception as exc:   # noqa: BLE001
            trace.append({"box": "X", "skipped": True,
                          "reason": f"consult_failed:{exc}",
                          "note": "box_x_skipped"})
            return None
        trace.append({
            "box":         "X",
            "consulted":   bool(out.consulted),
            "hit":         bool(out.has_hit()),
            "reason":      out.reason,
            "hit_count":   len(out.hits),
            "notes":       list(out.notes),
        })
        return out

    def _build_box_x_result(self, consultation, *, now: str):
        """Convert a BoxXConsultation into (sources, synthesis, score)
        compatible with the existing RetrievalResult shape.
        """
        sources = []
        text_blocks = []
        max_score = 0.0
        for hit in consultation.hits:
            score = float(hit.get("quality_score") or 0.0)
            if score > max_score:
                max_score = score
            sources.append(Source(
                source_type     = "local_rag",
                label           = hit.get("title", "(untitled)"),
                uri             = hit.get("source_uri", ""),
                chunk_index     = 0,
                retrieved_at    = now,
                relevance_score = round(score, 4),
            ))
            # Only the title + canonical-term hint travels in the synthesis
            # blob — Box X is a curated reference layer, not a content cache.
            terms = ", ".join(hit.get("canonical_terms") or [])
            text_blocks.append(
                f"[Box X] {hit.get('title','')}"
                + (f" — {terms}" if terms else "")
                + f" (domain: {hit.get('domain','')})"
            )
        synthesis = "\n\n".join(text_blocks)
        return sources, synthesis, max_score

    # -- Internal methods ------------------------------------------------------

    def _maybe_run_supplementary_w(
        self,
        *,
        query: str,
        k: int,
        pref_hints,
        allow_wiki: bool,
        freshness_sensitive: bool,
        profile_id: str,
        trace: list,
    ) -> None:
        """
        Phase G.2: run Box W as a non-terminal supplementary consultation
        after Stage 1 Box A has already succeeded. Never changes the primary
        box_used (still "A"); only appends an inspectable trace entry.

        Gated by:
          - pref_hints.supplementary_w_after_inner_hit (profile opt-in)
          - allow_wiki (profile gate)
          - NOT freshness_sensitive (freshness uses Box S, not supplementary W)
          - BoxFlags.box_b + adapter availability

        Errors are swallowed (non-terminal) — supplementary consultation must
        never crash the primary A success path.
        """
        if pref_hints is None or not getattr(pref_hints, "supplementary_w_after_inner_hit", False):
            return
        if not allow_wiki:
            trace.append({
                "box": "W-supplementary", "skipped": True,
                "reason": f"disabled by profile:{profile_id}",
                "phase_g2": True,
            })
            return
        if freshness_sensitive:
            trace.append({
                "box": "W-supplementary", "skipped": True,
                "reason": "freshness_sensitive (supplementary W disabled)",
                "phase_g2": True,
            })
            return
        if not (self._flags.box_b and self._box_b is not None):
            trace.append({
                "box": "W-supplementary", "skipped": True,
                "reason": "Box W backend unavailable",
                "phase_g2": True,
            })
            return
        try:
            if not self._box_b.is_available():
                trace.append({
                    "box": "W-supplementary", "skipped": True,
                    "reason": "is_available=False",
                    "phase_g2": True,
                })
                return
        except Exception as _e:
            trace.append({
                "box": "W-supplementary", "skipped": True,
                "reason": f"availability check failed: {_e}",
                "phase_g2": True,
            })
            return

        try:
            r, score, ok = self._try_box("W-supplementary", self._box_b, query, k)
            trace.append({
                "box": "W-supplementary",
                "score": score,
                "sufficient": ok,
                "outcome": r.outcome,
                "terminal": False,
                "profile_id": profile_id,
                "preference_order": list(getattr(pref_hints, "optional_preference_order", ())),
                "widen_reason_notes": list(getattr(pref_hints, "widen_reason_notes", [])),
                "phase_g2": True,
            })
        except Exception as _e:
            trace.append({
                "box": "W-supplementary", "skipped": True,
                "reason": f"supplementary W error (ignored): {_e}",
                "phase_g2": True,
            })

    def _try_box(
        self,
        box_name: str,
        adapter,
        query: str,
        top_k: int,
    ) -> tuple[RetrievalResult, float, bool]:
        """
        Execute a single Box and return (result, score, sufficient).
        Exceptions are caught internally to continue fallback.
        """
        try:
            t0 = time.time()
            result = adapter.retrieve(query, top_k=top_k)
            score  = adapter.get_sufficiency_score(result)
            ms     = round((time.time() - t0) * 1000, 1)

            # Get per-Box threshold
            threshold = getattr(adapter, "threshold", 0.0) or 0.0
            sufficient = score >= threshold and bool(result.sources)

            logger.info(
                f"[Selector] Box {box_name}: score={score:.4f} "
                f"threshold={threshold:.4f} sufficient={sufficient} "
                f"sources={len(result.sources)} latency={ms}ms"
            )
            return result, score, sufficient

        except Exception as e:
            logger.error(f"[Selector] Box {box_name} error: {e}")
            empty = RetrievalResult(sources=[], outcome="failed", synthesis="")
            return empty, 0.0, False

    def status(self) -> dict:
        """Return the status of each Box (for debugging/health checks)"""
        def _box_status(name: str, adapter, flag: bool) -> dict:
            if not flag:
                return {"box": name, "flag": False, "available": False}
            if adapter is None:
                return {"box": name, "flag": True, "available": False, "reason": "not injected"}
            avail = adapter.is_available()
            threshold = getattr(adapter, "threshold", None)
            return {
                "box":       name,
                "flag":      True,
                "available": avail,
                "threshold": threshold,
                "repr":      repr(adapter),
            }
        return {
            "box_0": _box_status("0", self._box_0, self._flags.box_0),
            "box_a": _box_status("A", self._box_a, self._flags.box_a),
            "box_w": _box_status("W", self._box_b, self._flags.box_b),
            "box_b_legacy": _box_status("B", self._box_b, self._flags.box_b),
            "box_s": _box_status("S", self._box_s, self._flags.box_s),
        }

    def __repr__(self) -> str:
        a = self._box_a.is_available() if self._box_a else False
        b = self._box_b.is_available() if self._box_b else False
        c = self._box_s.is_available() if self._box_s else False
        return (
            f"RetrievalSelector("
            f"A={'✅' if a else '—'} "
            f"W={'✅' if b else '—'} "
            f"S={'✅' if c else '—'} "
            f"flags={self._flags})"
        )


# -- CLI -----------------------------------------------------------------------

def _cli():
    import argparse, sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

    parser = argparse.ArgumentParser(
        description="RetrievalSelector CLI — 3-stage fallback search test"
    )
    parser.add_argument("--corpus",    default="corpus")
    parser.add_argument("--data-a",    default="data/box_a")
    parser.add_argument("--index-b",   default="Wiki/wiki_index_ivfpq_me5.faiss")
    parser.add_argument("--chunks-b",  default="Wiki/wiki_chunks_clean.jsonl.gz")
    parser.add_argument("--top-k",     type=int, default=5)
    parser.add_argument("--freshness", action="store_true",
                        help="Fire Box S with freshness_sensitive=True")
    parser.add_argument("--status",    action="store_true",
                        help="Display each Box's status and exit")
    parser.add_argument("query", nargs="?", default="What is the speed of light?")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Path resolution: supports execution from both MOBIUS_MMV root and src/adapters/
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    for _p in [_here, _here.parent, _here.parent.parent]:
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))

    # Box A
    from custom_rag_adapter import CustomRagAdapter
    box_a = CustomRagAdapter(corpus_dir=args.corpus, data_dir=args.data_a, watch=False)
    box_a.load()

    # Box W (legacy local variable name: box_b)
    from wiki_adapter import WikiAdapter
    box_b = WikiAdapter(index_path=args.index_b, chunks_path=args.chunks_b)
    box_b.load()

    selector = RetrievalSelector(box_a=box_a, box_b=box_b, top_k=args.top_k)

    if args.status:
        import json
        print(json.dumps(selector.status(), indent=2, ensure_ascii=False))
        return

    print(f"\nSelector: {selector}")
    print(f"Query: {args.query!r}  freshness={args.freshness}")

    sr = selector.select(args.query, freshness_sensitive=args.freshness)

    print(f"\n{'='*60}")
    print(f"  box_used   : {sr.box_used}")
    print(f"  sufficient : {sr.sufficient}")
    print(f"  score      : {sr.score:.4f}")
    print(f"  outcome    : {sr.result.outcome}")
    print(f"  sources    : {len(sr.result.sources)}")
    print(f"  latency    : {sr.latency_ms} ms")
    print(f"\n  Fallback trace:")
    for step in sr.fallback_trace:
        print(f"    {step}")
    print(f"{'='*60}")

    if sr.result.sources:
        print("\nTop sources:")
        blocks = sr.result.synthesis.split("\n\n")
        for i, src in enumerate(sr.result.sources[:3], 1):
            snippet = blocks[i-1][:120] if i-1 < len(blocks) else ""
            print(f"  [{i}] score={src.relevance_score}  {src.label}")
            print(f"       {src.uri}")
            print(f"       {snippet}...")


if __name__ == "__main__":
    _cli()
