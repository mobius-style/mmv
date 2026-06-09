"""
brave_search_adapter.py — Brave Search API adapter for MMV Verify.

Primary: LLM Context endpoint (/res/v1/llm/context) with Goggles.
Fallback: Web Search endpoint (/res/v1/web/search) on LLM Context failure.

Environment variable:
    BRAVE_API_KEY — Brave Search API key (Free AI Search plan)

Free tier: 2,000 queries/month
API docs: https://api.search.brave.com/app/documentation/web-search
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import requests

from ..adjudication.evidence_models import SearchResponse, SearchResult
from .web_search_adapter import WebSearchAdapter

logger = logging.getLogger(__name__)


# ── Goggles: prioritize authoritative sources ────────────────────────────────

BRAVE_GOGGLES = """\
! name: MOBIUS Verify Sources
! description: Prioritize authoritative sources for fact verification
! public: false
! author: MOBIUS

$boost=3,site=wikipedia.org
$boost=3,site=britannica.com
$boost=2,site=reuters.com
$boost=2,site=apnews.com
$boost=2,site=bbc.com
$boost=2,site=nature.com
$boost=2,site=sciencedirect.com
$boost=2,site=who.int
$boost=2,site=worldbank.org
$discard,site=pinterest.com
$discard,site=quora.com
$downrank=3,site=reddit.com
"""


def _flatten_snippet(text: str) -> str:
    """Flatten JSON-structured snippets (tables, etc.) to plain text.

    Brave LLM Context API sometimes returns structured data as JSON strings
    instead of plain text.  Small models struggle to parse raw JSON tables,
    so we convert them to readable text before passing to the adjudicator.
    Plain-text snippets pass through unchanged.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text

    if not isinstance(data, dict):
        return text

    parts: list[str] = []
    if "title" in data:
        parts.append(data["title"])
    if "caption" in data:
        parts.append(data["caption"])
    if "table" in data:
        table = data["table"]
        if isinstance(table, list):
            for row in table:
                if isinstance(row, dict):
                    parts.append(
                        " — ".join(f"{k}: {v}" for k, v in row.items())
                    )
                elif isinstance(row, list):
                    parts.append(" | ".join(str(cell) for cell in row))
                elif isinstance(row, str):
                    parts.append(row)
        elif isinstance(table, dict):
            parts.append(
                " — ".join(f"{k}: {v}" for k, v in table.items())
            )
    if "text" in data:
        parts.append(data["text"])

    return "\n".join(parts) if parts else text


class BraveSearchAdapter(WebSearchAdapter):
    """
    Concrete provider: Brave Search API.

    Primary endpoint: LLM Context (/res/v1/llm/context)
      - Returns structured text chunks (snippets, tables, code)
      - Supports Goggles for source prioritization
      - Same API key, same price tier as Web Search

    Fallback endpoint: Web Search (/res/v1/web/search)
      - Used when LLM Context returns an error (429, 500, etc.)

    Provider-specific logic is fully contained here.
    The kernel and adjudicator see only SearchResponse.
    """

    PROVIDER_NAME = "brave"
    LLM_CONTEXT_ENDPOINT = "https://api.search.brave.com/res/v1/llm/context"
    WEB_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
    TIMEOUT_SECONDS = 10

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("BRAVE_API_KEY", "")
        self._live   = bool(self.api_key)

    # ── Public interface ──────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        max_results: int = 5,
        freshness_hint: str | None = None,
        preset: str | None = None,
    ) -> SearchResponse:
        if not self._live:
            return SearchResponse(
                query=query,
                provider=self.PROVIDER_NAME,
                success=False,
                results=[],
                error_message="BRAVE_API_KEY not configured.",
            )
        try:
            return self._call_llm_context(query, max_results, freshness_hint)
        except Exception as exc:
            logger.warning(
                "[Brave] LLM Context failed (%s), falling back to Web Search",
                exc,
            )
            try:
                return self._call_web_search(query, max_results, freshness_hint)
            except Exception as exc2:
                return SearchResponse(
                    query=query,
                    provider=self.PROVIDER_NAME,
                    success=False,
                    results=[],
                    error_message=str(exc2),
                )

    # ── LLM Context API (primary) ────────────────────────────────────────────

    def _call_llm_context(
        self,
        query: str,
        max_results: int,
        freshness_hint: str | None,
    ) -> SearchResponse:
        params: dict = {
            "q": query,
            "result_count": min(max_results, 50),
            "goggles": BRAVE_GOGGLES,
        }
        if freshness_hint == "recent":
            params["page_age"] = "pw"

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }

        resp = requests.get(
            self.LLM_CONTEXT_ENDPOINT,
            params=params,
            headers=headers,
            timeout=self.TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()

        return self._parse_llm_context(query, data)

    def _parse_llm_context(
        self, query: str, data: dict
    ) -> SearchResponse:
        """Parse LLM Context API response into SearchResponse."""
        results: list[SearchResult] = []
        grounding = data.get("grounding", {}).get("generic", [])
        sources_meta = data.get("sources", {})
        fetched_at = datetime.now(timezone.utc).isoformat()

        for rank, item in enumerate(grounding, start=1):
            url = item.get("url", "")
            title = item.get("title", "")

            # Combine all snippet texts, flattening JSON structures
            snippets = item.get("snippets", [])
            if isinstance(snippets, list):
                snippet_texts = []
                for s in snippets:
                    if isinstance(s, dict):
                        snippet_texts.append(
                            _flatten_snippet(s.get("text", ""))
                        )
                    elif isinstance(s, str):
                        snippet_texts.append(_flatten_snippet(s))
                snippet = "\n".join(snippet_texts)
            else:
                snippet = str(snippets)

            # Source metadata
            src_meta = sources_meta.get(url, {})
            source_name = (
                src_meta.get("hostname", "")
                or (url.split("/")[2] if url and "/" in url else "")
            )
            date = src_meta.get("date", fetched_at)

            results.append(SearchResult(
                title=title,
                url=url,
                snippet=snippet[:4000],  # cap to prevent oversized payloads
                source_name=source_name,
                fetched_at=date,
                rank=rank,
                provider=self.PROVIDER_NAME,
            ))

        return SearchResponse(
            query=query,
            provider=self.PROVIDER_NAME,
            success=bool(results),
            results=results,
            error_message=None if results else "Brave LLM Context returned no results.",
        )

    # ── Web Search API (fallback) ────────────────────────────────────────────

    def _call_web_search(
        self,
        query: str,
        max_results: int,
        freshness_hint: str | None,
    ) -> SearchResponse:
        params: dict = {
            "q": query,
            "count": min(max_results, 20),
        }
        if freshness_hint == "recent":
            params["freshness"] = "pw"

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }

        resp = requests.get(
            self.WEB_SEARCH_ENDPOINT,
            params=params,
            headers=headers,
            timeout=self.TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()

        results: list[SearchResult] = []
        fetched_at = datetime.now(timezone.utc).isoformat()

        for rank, item in enumerate(
            data.get("web", {}).get("results", []), start=1
        ):
            snippet = (
                item.get("description")
                or item.get("extra_snippets", [""])[0]
                or ""
            )
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=snippet,
                source_name=item.get("meta_url", {}).get("hostname", "")
                            or item.get("url", "").split("/")[2],
                fetched_at=fetched_at,
                rank=rank,
                provider=self.PROVIDER_NAME,
            ))

        return SearchResponse(
            query=query,
            provider=self.PROVIDER_NAME,
            success=bool(results),
            results=results,
            error_message=None if results else "Brave Web Search returned no results.",
        )
