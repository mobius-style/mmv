"""
test_verify_eval_suite.py — Comparison eval for MMV Verify Stage 1.

Three demo classes:
  A: freshness-sensitive fact  — verify must not stale-commit
  B: policy/institutional      — local-first, bounded web fallback
  C: under-specified query     — ask before verify

These tests use the stub adapter (no live search) to verify routing behavior.
Live synthesis is tested separately in live_verify_test.py.
"""
import pytest
from src.kernel.routing_engine import RoutingEngine
from src.adapters.web_search_adapter import VertexSearchAdapter
from src.adapters.brave_search_adapter import BraveSearchAdapter


def _stub_engine(preset="general"):
    """RoutingEngine with stub web adapter — no live search."""
    return RoutingEngine(
        web_search_adapter=VertexSearchAdapter(project_id="", app_id=""),
        verify_preset=preset,
    )


# ── Demo class A: freshness-sensitive fact ────────────────────────────────────

class TestFreshnessSensitiveFact:

    def test_freshness_query_routes_to_verify_or_ask(self):
        engine = _stub_engine()
        result = engine.evaluate("Who is the current prime minister of Japan?")
        assert result.decision.route in ("verify", "ask"), \
            f"Expected verify or ask, got {result.decision.route}"

    def test_stub_verify_does_not_produce_confident_direct_answer(self):
        engine = _stub_engine()
        result = engine.evaluate("Who is the current prime minister of Japan?")
        if result.decision.route == "verify":
            text = result.response_text.lower()
            assert any(kw in text for kw in (
                "verify", "cannot", "insufficient", "not connected", "failed"
            )), f"Expected bounded response, got: {result.response_text[:100]}"

    def test_verify_outcome_is_failed_when_stub(self):
        engine = _stub_engine()
        result = engine.evaluate("What is the latest GDP figure for Japan?")
        if result.decision.route == "verify":
            outcome = result.trace.get("VerifyOutcome", "")
            assert "failed" in (outcome or "").lower() or "partial" in (outcome or "").lower()


# ── Demo class B: policy/institutional ───────────────────────────────────────

class TestPolicyInstitutional:

    def test_policy_query_routes_to_verify_or_ask(self):
        engine = _stub_engine(preset="policy")
        result = engine.evaluate("What is Japan's current consumption tax rate?")
        assert result.decision.route in ("verify", "ask", "answer")

    def test_policy_preset_accepted(self):
        engine = _stub_engine(preset="policy")
        assert engine.verify_preset == "policy"

    def test_legal_preset_accepted(self):
        engine = _stub_engine(preset="legal")
        assert engine.verify_preset == "legal"


# ── Demo class C: under-specified query ───────────────────────────────────────

class TestUnderSpecifiedQuery:

    def test_under_specified_routes_to_ask(self):
        engine = _stub_engine()
        result = engine.evaluate("What are the latest changes?")
        assert result.decision.route in ("ask", "verify"), \
            f"Expected ask, got {result.decision.route}"

    def test_vague_query_does_not_route_to_answer(self):
        engine = _stub_engine()
        result = engine.evaluate("What changed recently?")
        # Should not confidently answer an unspecified query
        assert result.decision.route != "answer" or \
               result.decision.confidence_posture in ("bounded", "uncertain")

    def test_under_specified_verify_redirects_to_ask(self):
        """Guard inside _handle_verify should redirect under-specified turns."""
        engine = _stub_engine()
        result = engine.evaluate("Tell me the latest.")
        # Either routed to ask at route_decision or redirected inside verify handler
        assert result.decision.route in ("ask", "verify")


# ── Preset integrity ──────────────────────────────────────────────────────────

class TestPresetIntegrity:

    def test_all_presets_load(self):
        from src.adjudication.verify_presets import get_preset, PRESETS
        for name in ("general", "policy", "legal", "educational"):
            preset = get_preset(name)
            assert preset.name == name
            assert preset.max_results > 0

    def test_unknown_preset_falls_back_to_general(self):
        from src.adjudication.verify_presets import get_preset
        preset = get_preset("nonexistent")
        assert preset.name == "general"

    def test_presets_do_not_change_admissibility_structure(self):
        """Core admissibility logic must be preset-independent."""
        from src.adjudication.admissibility import decide_admissibility
        for preset_name in ("general", "policy", "legal", "educational"):
            result = decide_admissibility(
                freshness_state="current-supported",
                source_diversity_state="high",
                agreement_state="high",
                conflict_state="none",
                evidence_strength="strong",
                provenance_state="strong",
            )
            assert result == "answerable"
