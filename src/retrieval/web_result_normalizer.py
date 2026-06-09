"""
web_result_normalizer.py — Normalize raw SearchResponse before adjudication.

Responsibilities:
- Remove results with empty URL or empty snippet.
- Deduplicate by canonical URL.
- Trim snippets to a reasonable length.
- Normalize source_name from URL hostname.
- Apply max_results cap.
- Return success=False if nothing survives normalization.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

from ..adjudication.evidence_models import SearchResponse, SearchResult

_MAX_SNIPPET_CHARS = 400
_DEFAULT_MAX_RESULTS = 8


def _canonical_url(url: str) -> str:
    """Lowercase scheme+host, strip fragment and trailing slash."""
    try:
        p = urlparse(url.strip())
        canonical = urlunparse((
            p.scheme.lower(),
            p.netloc.lower(),
            p.path.rstrip("/"),
            p.params,
            p.query,
            "",          # strip fragment
        ))
        return canonical
    except Exception:
        return url.strip().lower()


def _source_name_from_url(url: str, fallback: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        host = host.lower().lstrip("www.")
        return host if host else fallback
    except Exception:
        return fallback


# RCB_3 (Snippet Preprocessing): strip inline HTML tags from search result
# snippets before passing to synthesizer. Brave API 'description' field
# frequently contains inline HTML (e.g. bold highlight tags) and other
# markup that would otherwise flow into the LLM prompt.
_HTML_TAG_PATTERN = re.compile(r'<[^>]+>')


def _strip_html_tags(text):
    """Remove inline HTML tags from a snippet string.

    Preserves surrounding text. Decodes the most common HTML entities
    (&amp;, &lt;, &gt;, &quot;, &#39;) since the synthesizer is tolerant
    of stray entities but confused by markup.
    """
    if not text:
        return text
    stripped = _HTML_TAG_PATTERN.sub('', text)
    stripped = (
        stripped
        .replace('&amp;', '&')
        .replace('&lt;', '<')
        .replace('&gt;', '>')
        .replace('&quot;', '"')
        .replace('&#39;', "'")
    )
    return stripped


def _trim_snippet(snippet: str) -> str:
    snippet = snippet.strip()
    if len(snippet) <= _MAX_SNIPPET_CHARS:
        return snippet
    # Cut at last word boundary before limit
    trimmed = snippet[:_MAX_SNIPPET_CHARS]
    last_space = trimmed.rfind(" ")
    return (trimmed[:last_space] if last_space > 0 else trimmed) + "…"


def normalize_search_response(
    raw: SearchResponse,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> SearchResponse:
    """
    Return a cleaned SearchResponse suitable for adjudication.

    If no results survive normalization, success is set to False
    so the verify pipeline treats it as a retrieval failure.
    """
    if not raw.success or not raw.results:
        return SearchResponse(
            query=raw.query,
            provider=raw.provider,
            success=False,
            results=[],
            error_message=raw.error_message or "Empty result set before normalization.",
        )

    seen_urls: set[str] = set()
    cleaned: list[SearchResult] = []

    for result in raw.results:
        # Drop results with no URL or no snippet
        if not result.url or not result.snippet:
            continue

        canon = _canonical_url(result.url)
        if canon in seen_urls:
            continue
        seen_urls.add(canon)

        source_name = _source_name_from_url(result.url, result.source_name)
        # RCB_3: strip HTML BEFORE trim to avoid leaving dangling tag fragments
        # when trim cuts through a tag boundary at the _MAX_SNIPPET_CHARS limit.
        snippet = _trim_snippet(_strip_html_tags(result.snippet))
        title = result.title.strip() if result.title else source_name

        cleaned.append(SearchResult(
            title=title,
            url=canon,
            snippet=snippet,
            source_name=source_name,
            fetched_at=result.fetched_at,
            rank=result.rank,
            provider=result.provider or raw.provider,
            provider_payload=result.provider_payload,
        ))

        if len(cleaned) >= max_results:
            break

    if not cleaned:
        return SearchResponse(
            query=raw.query,
            provider=raw.provider,
            success=False,
            results=[],
            error_message="All results were filtered during normalization.",
        )

    return SearchResponse(
        query=raw.query,
        provider=raw.provider,
        success=True,
        results=cleaned,
    )
