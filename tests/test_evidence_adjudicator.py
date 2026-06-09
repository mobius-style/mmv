"""Tests for evidence_adjudicator.py"""
import pytest
from src.adjudication.evidence_adjudicator import (
    adjudicate_evidence,
    extract_central_claim,
)
from src.adjudication.evidence_models import (
    SearchResponse,
    SearchResult,
    ADMISSIBILITY_FAILED,
    ADMISSIBILITY_BOUNDED_ONLY,
    ADMISSIBILITY_ANSWERABLE,
)
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat()


def _make_result(title, url, snippet, rank=1):
    return SearchResult(
        title=title,
        url=url,
        snippet=snippet,
        source_name=url.split("/")[2],
        fetched_at=_now(),
        rank=rank,
        provider="vertex",
    )


# ── extract_central_claim ─────────────────────────────────────────────────────

def test_extract_central_claim_returns_first_sentence():
    snippet = "The prime minister met officials today. Further talks are planned."
    result = extract_central_claim(snippet)
    assert result == "The prime minister met officials today."


def test_extract_central_claim_no_sentence_boundary():
    snippet = "No punctuation here"
    assert extract_central_claim(snippet) == "No punctuation here"


def test_extract_central_claim_empty():
    assert extract_central_claim("") == ""


def test_extract_central_claim_is_deterministic():
    snippet = "Tokyo confirmed the plan. Details to follow."
    assert extract_central_claim(snippet) == extract_central_claim(snippet)


# ── adjudicate_evidence ───────────────────────────────────────────────────────

def test_empty_response_returns_failed():
    response = SearchResponse(
        query="test", provider="vertex", success=False, results=[]
    )
    result = adjudicate_evidence(response, "test")
    assert result.admissibility == ADMISSIBILITY_FAILED


def test_single_result_returns_adjudicated_set():
    response = SearchResponse(
        query="PM of Japan",
        provider="vertex",
        success=True,
        results=[
            _make_result(
                "Japan PM",
                "https://reuters.com/world/japan",
                "The current prime minister of Japan is X as of this week.",
            )
        ],
    )
    result = adjudicate_evidence(response, "Who is the PM of Japan?")
    assert result.source_count == 1
    assert result.admissibility in (
        ADMISSIBILITY_ANSWERABLE,
        ADMISSIBILITY_BOUNDED_ONLY,
        ADMISSIBILITY_FAILED,
    )


def test_open_conflict_in_snippets_limits_admissibility():
    response = SearchResponse(
        query="policy update",
        provider="vertex",
        success=True,
        results=[
            _make_result(
                "A says yes",
                "https://reuters.com/a",
                "The policy was approved. However, critics dispute the claim.",
            ),
            _make_result(
                "B contradicts",
                "https://apnews.com/b",
                "Contrary to earlier reports, the policy contradicts prior rules.",
                rank=2,
            ),
            _make_result(
                "C also disputes",
                "https://bbc.com/c",
                "At odds with official statements, the policy disputes current rules.",
                rank=3,
            ),
        ],
    )
    result = adjudicate_evidence(response, "What changed in the policy?")
    # open-conflict or bounded-only — must not be answerable
    assert result.admissibility != ADMISSIBILITY_ANSWERABLE


def test_rationale_is_populated():
    response = SearchResponse(
        query="test",
        provider="vertex",
        success=True,
        results=[
            _make_result("X", "https://reuters.com/x", "Some snippet.")
        ],
    )
    result = adjudicate_evidence(response, "test")
    assert len(result.rationale) > 0
