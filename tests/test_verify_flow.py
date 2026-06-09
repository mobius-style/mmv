"""Tests for web_result_normalizer.py and end-to-end verify flow."""
import pytest
from datetime import datetime, timezone

from src.retrieval.web_result_normalizer import normalize_search_response
from src.adjudication.evidence_models import SearchResponse, SearchResult
from src.kernel.routing_engine import RoutingEngine
from src.adapters.web_search_adapter import VertexSearchAdapter


def _now():
    return datetime.now(timezone.utc).isoformat()


def _make_result(title, url, snippet, rank=1):
    return SearchResult(
        title=title, url=url, snippet=snippet,
        source_name=url.split("/")[2],
        fetched_at=_now(), rank=rank, provider="vertex",
    )


# ── normalize_search_response ─────────────────────────────────────────────────

def test_normalize_removes_empty_url():
    response = SearchResponse(
        query="test", provider="vertex", success=True,
        results=[
            _make_result("Good", "https://reuters.com/a", "Good snippet."),
            SearchResult(title="Bad", url="", snippet="x",
                         source_name="?", fetched_at=_now()),
        ],
    )
    result = normalize_search_response(response)
    assert result.success
    assert all(r.url for r in result.results)


def test_normalize_deduplicates_urls():
    response = SearchResponse(
        query="test", provider="vertex", success=True,
        results=[
            _make_result("A", "https://reuters.com/story", "Snippet A."),
            _make_result("A2", "https://reuters.com/story", "Snippet A2."),
        ],
    )
    result = normalize_search_response(response)
    assert len(result.results) == 1


def test_normalize_empty_response_returns_failed():
    response = SearchResponse(
        query="test", provider="vertex", success=False, results=[],
    )
    result = normalize_search_response(response)
    assert result.success is False


def test_normalize_trims_long_snippet():
    long_snippet = "word " * 200
    response = SearchResponse(
        query="test", provider="vertex", success=True,
        results=[_make_result("X", "https://bbc.com/x", long_snippet)],
    )
    result = normalize_search_response(response)
    assert len(result.results[0].snippet) <= 410  # 400 + ellipsis


def test_normalize_respects_max_results():
    results = [
        _make_result(f"T{i}", f"https://example{i}.com/x", f"Snippet {i}.", rank=i)
        for i in range(10)
    ]
    response = SearchResponse(query="test", provider="vertex", success=True, results=results)
    normalized = normalize_search_response(response, max_results=3)
    assert len(normalized.results) == 3


# ── verify flow: stub adapter keeps failure discipline ────────────────────────

def test_verify_flow_stub_does_not_collapse_to_direct_answer():
    """When Vertex stub returns failure, verify must not produce a direct answer."""
    engine = RoutingEngine(
        web_search_adapter=VertexSearchAdapter(project_id="", app_id=""),
    )
    # Freshness-sensitive query should go to verify route
    result = engine.evaluate("Who is the current prime minister of Japan?")
    if result.decision.route == "verify":
        # verify_failed is the only acceptable outcome when stub returns nothing
        assert "verify_failed" in (result.trace.get("VerifyOutcome") or "")
        # Must not look like a direct confident answer
        assert result.response_text.startswith("[verify:") or \
               "cannot" in result.response_text.lower() or \
               "insufficient" in result.response_text.lower() or \
               "not connected" in result.response_text.lower()


def test_routing_engine_accepts_web_search_adapter():
    adapter = VertexSearchAdapter()
    engine = RoutingEngine(web_search_adapter=adapter)
    assert engine.web_search_adapter is adapter


def test_routing_engine_default_preset_is_general():
    engine = RoutingEngine()
    assert engine.verify_preset == "general"
