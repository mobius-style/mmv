"""
RCB_1 Reformulation Entitlement tests.

Per L0 v8.2 spec §9.1 and Phase 1 Audit (2026-04-22):
- TVS_THRESHOLD = 0.6 (behavioral gate, existing, freshness_sensitive routing)
- TVS_HIGH_THRESHOLD = 0.70 (declarative marker, new in Phase 2)
- reformulate_query must be skipped at _handle_verify when either gate is triggered.
- Answer-route reformulation paths (lines 1078, 1831) are left unchanged because
  their reformulated output is consumed by wiki (Box W) search.
"""
from __future__ import annotations

from src.kernel import routing_engine as _re
from src.kernel.routing_engine import RoutingEngine
from src.state.session_state import SessionState


# ── Threshold constants ──────────────────────────────────────────────────────

def test_tvs_high_threshold_constant_exists():
    from src.adapters.eal import TVS_HIGH_THRESHOLD
    assert TVS_HIGH_THRESHOLD == 0.70


def test_existing_tvs_threshold_unchanged():
    from src.adapters.eal import TVS_THRESHOLD
    assert TVS_THRESHOLD == 0.6


def test_two_thresholds_coexist_as_separate_symbols():
    # RCB_1 design: behavioral gate (0.6) and declarative marker (0.70) are
    # distinct concepts and must not be unified.
    from src.adapters.eal import TVS_THRESHOLD, TVS_HIGH_THRESHOLD
    assert TVS_THRESHOLD != TVS_HIGH_THRESHOLD
    assert TVS_THRESHOLD < TVS_HIGH_THRESHOLD


def test_tvs_high_threshold_imported_in_routing_engine():
    # The routing engine must carry the symbol so the skip guard is wired.
    assert _re.TVS_HIGH_THRESHOLD == 0.70


# ── Skip-on-freshness_sensitive behaviour at verify path ─────────────────────

class _CallCounter:
    """Records every call to reformulate_query without invoking the LLM."""
    def __init__(self):
        self.count = 0
        self.last_args = None

    def __call__(self, *args, **kwargs):
        self.count += 1
        self.last_args = (args, kwargs)
        # Return a ReformulatedQuery-shaped object so downstream code keeps running.
        return _re.ReformulatedQuery(
            original=args[0] if args else "",
            en_keywords="",
            native_keywords="",
            lang=args[1] if len(args) > 1 else "en",
        )


def _make_freshness_appraisal():
    """AppraisalState whose freshness_sensitive=True triggers the skip."""
    from src.kernel.appraisal import AppraisalState
    return AppraisalState(
        completeness=0.9,
        uncertainty=0.2,
        freshness_sensitive=True,
        safety_relevant=False,
        intent_clarity=0.9,
        stable_fact=False,
        kvs=None,
    )


def _make_tvs_high_appraisal():
    """AppraisalState with TVS >= 0.70 but freshness_sensitive=False."""
    from src.kernel.appraisal import AppraisalState
    from src.kernel.kvs import KVSResult
    kvs = KVSResult(
        tvs=0.80, mkr_base=0.6, r_fresh=0.0, e_hist=0.0, mkr_eff=0.6,
        model_class="test", domain="test", low_stakes_eligible=False,
    )
    return AppraisalState(
        completeness=0.9,
        uncertainty=0.2,
        freshness_sensitive=False,
        safety_relevant=False,
        intent_clarity=0.9,
        stable_fact=False,
        kvs=kvs,
    )


def _make_low_tvs_appraisal():
    """AppraisalState with TVS well below 0.70 and freshness_sensitive=False."""
    from src.kernel.appraisal import AppraisalState
    from src.kernel.kvs import KVSResult
    kvs = KVSResult(
        tvs=0.25, mkr_base=0.6, r_fresh=0.0, e_hist=0.0, mkr_eff=0.6,
        model_class="test", domain="test", low_stakes_eligible=True,
    )
    return AppraisalState(
        completeness=0.9,
        uncertainty=0.2,
        freshness_sensitive=False,
        safety_relevant=False,
        intent_clarity=0.9,
        stable_fact=False,
        kvs=kvs,
    )


def test_reformulate_skipped_when_freshness_sensitive(monkeypatch):
    counter = _CallCounter()
    monkeypatch.setattr(_re, "reformulate_query", counter)

    engine = RoutingEngine()  # no adapter, no web_search_adapter
    state = SessionState()
    appraisal = _make_freshness_appraisal()

    engine._handle_verify("who is the current prime minister?", appraisal, state)

    assert counter.count == 0, (
        "reformulate_query must be skipped at _handle_verify when "
        "freshness_sensitive=True (RCB_1 wasted-LLM-call elimination)."
    )


def test_reformulate_skipped_when_tvs_high(monkeypatch):
    counter = _CallCounter()
    monkeypatch.setattr(_re, "reformulate_query", counter)

    engine = RoutingEngine()
    state = SessionState()
    appraisal = _make_tvs_high_appraisal()

    engine._handle_verify("ambiguous volatile topic", appraisal, state)

    assert counter.count == 0, (
        "reformulate_query must be skipped at _handle_verify when "
        "TVS >= TVS_HIGH_THRESHOLD (RCB_1 declarative marker)."
    )


def test_reformulate_called_when_tvs_low_and_not_freshness(monkeypatch):
    counter = _CallCounter()
    monkeypatch.setattr(_re, "reformulate_query", counter)

    engine = RoutingEngine()
    state = SessionState()
    appraisal = _make_low_tvs_appraisal()

    engine._handle_verify("explain category theory", appraisal, state)

    assert counter.count == 1, (
        "reformulate_query must be called when TVS < TVS_HIGH_THRESHOLD AND "
        "freshness_sensitive=False (regression guard — skip must not over-fire)."
    )


# ── RCB_2 regression guard: date-stamp anchoring still applied ───────────────

def test_date_stamp_anchoring_still_applied_for_freshness_queries(monkeypatch):
    """RCB_2 (Date-Stamp Anchoring) must remain intact. When the verify path
    runs with freshness_sensitive=True, the web_search_adapter receives a
    query suffixed with a YYYY-MM-DD stamp (not the raw reformulator output).
    """
    import re as _re_mod
    captured = {}

    class _RecordingWebAdapter:
        def search(self, *, query, max_results, freshness_hint, preset):
            captured["query"] = query
            # Return empty to short-circuit the path quickly.
            from src.adjudication.evidence_models import SearchResponse
            return SearchResponse(
                query=query, provider="test-recorder",
                success=False, results=[], error_message="test stub",
            )

    # Stub reformulate_query so if it were called, it would be visible.
    counter = _CallCounter()
    monkeypatch.setattr(_re, "reformulate_query", counter)

    engine = RoutingEngine(web_search_adapter=_RecordingWebAdapter())
    state = SessionState()
    appraisal = _make_freshness_appraisal()

    engine._handle_verify("what is today's inflation rate?", appraisal, state)

    assert "query" in captured, "web_search_adapter.search must be reached"
    assert _re_mod.search(r"\d{4}-\d{2}-\d{2}", captured["query"]), (
        f"Freshness-sensitive verify query must carry a YYYY-MM-DD stamp "
        f"(RCB_2 regression guard). Got: {captured['query']!r}"
    )
    assert counter.count == 0, (
        "reformulate_query must not be invoked for freshness_sensitive queries."
    )
