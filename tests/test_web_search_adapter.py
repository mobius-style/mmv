"""Tests for web_search_adapter.py"""
import pytest
from src.adapters.web_search_adapter import VertexSearchAdapter, make_default_adapter


def test_stub_returns_failed_when_unconfigured():
    adapter = VertexSearchAdapter(project_id="", app_id="")
    response = adapter.search("test query")
    assert response.success is False
    assert response.results == []
    assert response.error_message is not None
    assert "stub" in response.error_message.lower()


def test_stub_preserves_query():
    adapter = VertexSearchAdapter(project_id="", app_id="")
    response = adapter.search("Who is the PM of Japan?")
    assert response.query == "Who is the PM of Japan?"


def test_stub_provider_name():
    adapter = VertexSearchAdapter(project_id="", app_id="")
    response = adapter.search("test")
    assert response.provider == "vertex"


def test_make_default_adapter_returns_web_search_adapter():
    from src.adapters.web_search_adapter import WebSearchAdapter
    adapter = make_default_adapter()
    assert isinstance(adapter, WebSearchAdapter)


def test_stub_does_not_raise():
    adapter = VertexSearchAdapter()
    try:
        response = adapter.search("any query", max_results=3)
    except Exception as e:
        pytest.fail(f"Stub raised unexpectedly: {e}")
