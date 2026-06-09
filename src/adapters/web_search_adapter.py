"""
web_search_adapter.py — Provider-agnostic search interface + Vertex stub.

Architecture rule: the kernel and adjudicator depend only on SearchResponse.
Provider-specific logic must not leak beyond this module.

Vertex AI Search (Discovery Engine) is the reference provider.
The stub returns empty results with success=False until credentials are
configured. Replace VertexSearchAdapter._call_api() when ready.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from ..adjudication.evidence_models import SearchResponse, SearchResult


class WebSearchAdapter(ABC):
    """Abstract provider interface. All concrete adapters must implement search()."""

    @abstractmethod
    def search(
        self,
        query: str,
        max_results: int = 5,
        freshness_hint: str | None = None,
        preset: str | None = None,
    ) -> SearchResponse:
        """Execute a search and return a normalized SearchResponse."""
        ...


# ── Vertex AI Search (Discovery Engine) ──────────────────────────────────────

class VertexSearchAdapter(WebSearchAdapter):
    """
    Reference provider: Google Vertex AI Search (Discovery Engine).

    Stage 1 status: STUB — returns empty results until credentials are set.

    Required environment variables (when live):
        VERTEX_PROJECT_ID      — GCP project ID
        VERTEX_LOCATION        — e.g. "global" or "us-central1"
        VERTEX_SEARCH_APP_ID   — Discovery Engine app / data store ID

    When the above variables are present, this adapter calls the
    Discovery Engine REST API. Until then it returns a safe stub response
    so that the rest of the verify pipeline can be tested offline.
    """

    PROVIDER_NAME = "vertex"

    def __init__(
        self,
        project_id: str | None = None,
        location: str | None = None,
        app_id: str | None = None,
    ) -> None:
        self.project_id = project_id or os.getenv("VERTEX_PROJECT_ID", "")
        self.location   = location   or os.getenv("VERTEX_LOCATION", "global")
        self.app_id     = app_id     or os.getenv("VERTEX_SEARCH_APP_ID", "")
        self._live      = bool(self.project_id and self.app_id)

    # ── Public interface ──────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        max_results: int = 5,
        freshness_hint: str | None = None,
        preset: str | None = None,
    ) -> SearchResponse:
        if not self._live:
            return self._stub_response(query)
        try:
            return self._call_api(query, max_results)
        except Exception as exc:
            return SearchResponse(
                query=query,
                provider=self.PROVIDER_NAME,
                success=False,
                results=[],
                error_message=str(exc),
            )

    # ── Stub (offline / unconfigured) ─────────────────────────────────────────

    def _stub_response(self, query: str) -> SearchResponse:
        """
        Returns a clearly-marked stub response.
        The verify pipeline treats success=False as retrieval failure
        and will not collapse into a direct answer.
        """
        return SearchResponse(
            query=query,
            provider=self.PROVIDER_NAME,
            success=False,
            results=[],
            error_message=(
                "Vertex Search stub: VERTEX_PROJECT_ID / VERTEX_SEARCH_APP_ID "
                "not configured. Set environment variables to enable live search."
            ),
        )

    # ── Live API call (to be completed when credentials are available) ─────────

    def _call_api(self, query: str, max_results: int) -> SearchResponse:
        """
        Calls Vertex AI Search (Discovery Engine) REST API.

        TODO: implement when credentials are available.
        Endpoint:
          POST https://discoveryengine.googleapis.com/v1/projects/{project}/
               locations/{location}/collections/default_collection/
               engines/{app_id}/servingConfigs/default_search:search

        Auth: google-auth with Application Default Credentials.
        Install: pip install google-auth requests
        """
        raise NotImplementedError(
            "VertexSearchAdapter._call_api() is not yet implemented. "
            "Configure credentials and complete this method for live search."
        )

    @staticmethod
    def _now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()


# ── Convenience factory ───────────────────────────────────────────────────────

def make_default_adapter() -> WebSearchAdapter:
    """
    Returns the default web search adapter (Brave Search).
    Kiwix is wired separately via RoutingEngine.kiwix_adapter for
    non-freshness local fallback — it does NOT go through this factory.
    """
    from .brave_search_adapter import BraveSearchAdapter
    return BraveSearchAdapter()
