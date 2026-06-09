"""
kiwix_search_adapter.py — Bridge KiwixAdapter into the WebSearchAdapter interface.

Allows the kernel's verify pipeline (Pipeline 2) to use Kiwix as a local
evidence source without any code changes to the adjudication or synthesis layers.

Architecture:
  - KiwixAdapter (kiwix_adapter.py) handles kiwix-serve lifecycle and retrieval.
  - This adapter converts its output to SearchResponse / SearchResult contracts
    so that routing_engine._handle_verify() can use it identically to Brave.
  - source_type remains "local_rag" (Frozen v1.0).

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..adjudication.evidence_models import SearchResponse, SearchResult
from .web_search_adapter import WebSearchAdapter
from .kiwix_adapter import KiwixAdapter


class KiwixSearchAdapter(WebSearchAdapter):
    """WebSearchAdapter facade over KiwixAdapter for Pipeline 2 integration."""

    PROVIDER_NAME = "kiwix"

    def __init__(self, **kiwix_kwargs) -> None:
        self._kiwix = KiwixAdapter(**kiwix_kwargs)

    # ── WebSearchAdapter interface ───────────────────────────────────────────

    def search(
        self,
        query: str,
        max_results: int = 5,
        freshness_hint: str | None = None,
        preset: str | None = None,
    ) -> SearchResponse:
        # Kiwix serves a static Wikipedia snapshot — cannot satisfy freshness.
        if freshness_hint == "recent":
            return SearchResponse(
                query=query,
                provider=self.PROVIDER_NAME,
                success=False,
                results=[],
                error_message="Kiwix cannot satisfy freshness-sensitive queries.",
            )

        result = self._kiwix.retrieve(query, top_k=max_results)

        if not result.sources:
            return SearchResponse(
                query=query,
                provider=self.PROVIDER_NAME,
                success=False,
                results=[],
                error_message="Kiwix returned no results.",
            )

        now = datetime.now(timezone.utc).isoformat()
        search_results: list[SearchResult] = []
        # Split the synthesis text back into per-source snippets
        snippets = result.synthesis.split("\n\n") if result.synthesis else []

        for rank, source in enumerate(result.sources, start=1):
            # Extract hostname from URI for source_name
            uri = source.uri
            if "localhost" in uri:
                source_name = "kiwix-wikipedia"
            else:
                parts = uri.split("/")
                source_name = parts[2] if len(parts) > 2 else "kiwix"

            # Use per-source snippet if available, else label
            snippet = ""
            if rank - 1 < len(snippets):
                snippet = snippets[rank - 1]
                # Strip the [Title] prefix line if present
                lines = snippet.split("\n", 1)
                if len(lines) > 1 and lines[0].startswith("["):
                    snippet = lines[1]

            search_results.append(SearchResult(
                title=source.label,
                url=uri,
                snippet=snippet,
                source_name=source_name,
                fetched_at=source.retrieved_at or now,
                rank=rank,
                provider=self.PROVIDER_NAME,
            ))

        return SearchResponse(
            query=query,
            provider=self.PROVIDER_NAME,
            success=True,
            results=search_results,
        )

    # ── Convenience ──────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        return self._kiwix.is_available()
