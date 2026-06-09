"""
RCB_3 Snippet Preprocessing: HTML tag stripping.

Per Phase 1 Audit (2026-04-22): Brave API description field may contain
inline HTML that was passing through to the synthesizer.
"""
from __future__ import annotations

from src.adjudication.evidence_models import SearchResponse, SearchResult
from src.retrieval.web_result_normalizer import (
    _strip_html_tags,
    normalize_search_response,
)


# ── _strip_html_tags unit tests ──────────────────────────────────────────────

def test_strip_basic_bold_tags():
    assert _strip_html_tags("the <b>quick</b> brown fox") == "the quick brown fox"


def test_strip_nested_tags():
    assert _strip_html_tags("<p>hello <b>world</b></p>") == "hello world"


def test_strip_self_closing_tags():
    assert _strip_html_tags("line1<br/>line2") == "line1line2"


def test_entity_decoding_amp():
    assert _strip_html_tags("Rock &amp; Roll") == "Rock & Roll"


def test_entity_decoding_lt_gt():
    # &lt;script&gt; should decode to literal angle brackets, *not* be
    # interpreted as a tag to strip (the entity decode runs after tag strip).
    assert _strip_html_tags("&lt;script&gt;") == "<script>"


def test_entity_decoding_quote_and_apos():
    assert _strip_html_tags("he said &quot;hi&quot;") == 'he said "hi"'
    assert _strip_html_tags("it&#39;s fine") == "it's fine"


def test_preserves_plain_text():
    assert _strip_html_tags("no tags here") == "no tags here"


def test_empty_input_returns_empty():
    assert _strip_html_tags("") == ""


def test_none_input_returns_none():
    assert _strip_html_tags(None) is None


def test_strip_multiple_tags_in_sequence():
    src = '<a href="http://x">foo</a> and <b>bar</b>'
    assert _strip_html_tags(src) == "foo and bar"


# ── Integration with normalize_search_response ──────────────────────────────

def _make_response_with_snippet(snippet: str) -> SearchResponse:
    return SearchResponse(
        query="test",
        provider="test-provider",
        success=True,
        results=[SearchResult(
            title="title",
            url="https://example.com/page",
            snippet=snippet,
            source_name="example.com",
            fetched_at="2026-04-22T00:00:00Z",
            rank=1,
            provider="test-provider",
        )],
    )


def test_strip_applied_in_normalize_basic():
    raw = _make_response_with_snippet("the <b>quick</b> brown fox")
    out = normalize_search_response(raw)
    assert out.success
    assert out.results[0].snippet == "the quick brown fox"


def test_strip_applied_in_normalize_with_entities():
    raw = _make_response_with_snippet("Rock &amp; Roll &lt;hit&gt;")
    out = normalize_search_response(raw)
    assert out.success
    assert out.results[0].snippet == "Rock & Roll <hit>"


def test_normalize_drops_empty_after_strip_is_not_required():
    # A snippet that is *only* HTML tags (no text) becomes empty after strip.
    # The normalizer must still handle this gracefully (either drop or keep
    # the empty). Current contract: empty snippet triggers the existing
    # "drop if not snippet" path *before* strip. This test documents the
    # surviving order-of-operations expectation: the original (pre-strip)
    # presence guard still fires, and no crash occurs.
    raw = _make_response_with_snippet("<b></b><i></i>")
    out = normalize_search_response(raw)
    # The pre-strip "not result.snippet" guard allows the result through
    # since "<b></b><i></i>" is truthy. After strip it becomes "". After
    # trim.strip() it stays "". Verify no crash and the surviving snippet
    # is empty string (acceptable for the contract; synthesizer tolerates
    # empty).
    if out.success and out.results:
        assert out.results[0].snippet == ""


def test_strip_before_trim_boundary_no_dangling_fragment():
    # Construct a snippet where an HTML tag would end near the 400-char
    # trim boundary. If strip happened AFTER trim, the tag could be
    # cut mid-way and leave a fragment like "<bo" in the output.
    # We test the contract: the normalized snippet must not contain
    # any '<' or '>' characters (which strip would have removed entirely).
    bulk_text = "word " * 80      # 400 chars exactly
    snippet = bulk_text + "<b>highlighted phrase at the far end</b>"
    raw = _make_response_with_snippet(snippet)
    out = normalize_search_response(raw)
    assert out.success
    cleaned = out.results[0].snippet
    assert "<" not in cleaned
    assert ">" not in cleaned


def test_strip_idempotent_on_tag_free_snippet():
    # Passing a tag-free snippet through normalize must not alter it
    # beyond the existing trim / strip behaviour.
    raw = _make_response_with_snippet("already clean snippet")
    out = normalize_search_response(raw)
    assert out.results[0].snippet == "already clean snippet"
