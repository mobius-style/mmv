"""Tests for scripts/pattern_autogen/xling_query_generator.py."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts.pattern_autogen.groq_client import (
    ConsensusResult, JudgeCall,
)
from scripts.pattern_autogen.xling_query_generator import (
    DEFAULT_MIN_COSINE, QUALITY_THRESHOLD, XlingGenerator,
)
from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Origin, Pattern, RouteConfig,
)


def _now():
    return datetime.now(timezone.utc)


def _make_pattern() -> Pattern:
    return Pattern(
        id="pat_concept_explain_001",
        topic="conceptual_explain",
        intent="explain_mobius_concept",
        examples=["What is MOBIUS", "Explain MOBIUS",
                  "Tell me about MOBIUS", "Define MOBIUS",
                  "How does MOBIUS work"],
        negative_examples=["What is a Möbius strip"],
        route=RouteConfig(primary_box="box_0",
                           synthesis_mode="conceptual_explanation"),
        cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="MOBIUSとは",
                                   expected_match=True, min_cosine=0.62),
            CrossLingualTestQuery(lang="ja", query="メビウス環について",
                                   expected_match=False),
            CrossLingualTestQuery(lang="zh", query="MOBIUS是什么",
                                   expected_match=True, min_cosine=0.62),
            CrossLingualTestQuery(lang="zh", query="莫比乌斯环",
                                   expected_match=False),
        ],
        origin=Origin(type="manual", date=_now()),
    )


class _FakeGroq:
    def __init__(self) -> None:
        self.scripted: list[ConsensusResult] = []

    def _make(self, parsed_per_call) -> ConsensusResult:
        calls = [
            JudgeCall(
                temperature=t, text=json.dumps(parsed),
                parsed=parsed, model="openai/gpt-oss-120b",
                latency_ms=1, error=None, usage=None,
            )
            for t, parsed in zip((0.3, 0.7, 1.0), parsed_per_call)
        ]
        return ConsensusResult(
            calls=calls, primary_used=True, accepted=True,
            batch_id="bat", groq_run_id="run", prompt_version="t",
            started_at="", finished_at="",
        )

    def consensus(self, system_prompt, user_prompt, **kw):
        if self.scripted:
            return self.scripted.pop(0)
        return self._make([{}, {}, {}])


# ─────────────────────────────────────────────────────────────────────

def test_default_min_cosine_for_positives() -> None:
    """expected_match=true with no min_cosine → default 0.62."""
    fake = _FakeGroq()
    fake.scripted.append(fake._make([
        {"queries": [{"lang": "ja", "query": "MOBIUSの定義",
                      "expected_match": True}]},  # no min_cosine
        {"queries": []},
        {"queries": []},
    ]))
    fake.scripted.append(fake._make([
        {"grades": [{"variant": "MOBIUSの定義", "score": 5}]},
        {"grades": [{"variant": "MOBIUSの定義", "score": 5}]},
        {"grades": [{"variant": "MOBIUSの定義", "score": 4}]},
    ]))
    g = XlingGenerator(client=fake)
    r = g.generate(_make_pattern(), n=3)
    accepted_ja = [q for q in r.accepted if q.lang == "ja" and q.expected_match]
    assert any(q.min_cosine == DEFAULT_MIN_COSINE for q in accepted_ja)


def test_negative_min_cosine_forced_to_none() -> None:
    """expected_match=false → min_cosine=None even if model emitted a value."""
    fake = _FakeGroq()
    fake.scripted.append(fake._make([
        {"queries": [{"lang": "ja", "query": "メビウスの帯の歴史",
                      "expected_match": False, "min_cosine": 0.4}]},
        {"queries": []},
        {"queries": []},
    ]))
    fake.scripted.append(fake._make([
        {"grades": [{"variant": "メビウスの帯の歴史", "score": 5}]},
        {"grades": [{"variant": "メビウスの帯の歴史", "score": 5}]},
        {"grades": [{"variant": "メビウスの帯の歴史", "score": 4}]},
    ]))
    g = XlingGenerator(client=fake)
    r = g.generate(_make_pattern(), n=3)
    neg = [q for q in r.accepted if not q.expected_match]
    assert len(neg) == 1
    assert neg[0].min_cosine is None


def test_dedup_against_existing_xling() -> None:
    """If Groq emits a query already in pattern.cross_lingual_test_queries,
    dedup drops it (case/whitespace-insensitive)."""
    fake = _FakeGroq()
    fake.scripted.append(fake._make([
        {"queries": [
            {"lang": "ja", "query": "  MOBIUSとは ",  # already exists
             "expected_match": True},
            {"lang": "zh", "query": "MOBIUS这个概念",  # new
             "expected_match": True},
        ]},
        {"queries": []},
        {"queries": []},
    ]))
    fake.scripted.append(fake._make([
        {"grades": [{"variant": "MOBIUS这个概念", "score": 5}]},
        {"grades": [{"variant": "MOBIUS这个概念", "score": 5}]},
        {"grades": [{"variant": "MOBIUS这个概念", "score": 4}]},
    ]))
    g = XlingGenerator(client=fake)
    r = g.generate(_make_pattern(), n=3)
    accepted_queries = {q.query for q in r.accepted}
    assert "MOBIUSとは" not in accepted_queries
    assert "MOBIUS这个概念" in accepted_queries


def test_invalid_lang_dropped() -> None:
    """Pydantic-invalid lang code → schema fail rejection."""
    fake = _FakeGroq()
    fake.scripted.append(fake._make([
        {"queries": [
            {"lang": "klingon",  # not in Literal
             "query": "tlhIngan Hol",
             "expected_match": True},
            {"lang": "ja", "query": "良いクエリ",
             "expected_match": True},
        ]},
        {"queries": []},
        {"queries": []},
    ]))
    fake.scripted.append(fake._make([
        {"grades": [{"variant": "良いクエリ", "score": 5}]},
        {"grades": [{"variant": "良いクエリ", "score": 5}]},
        {"grades": [{"variant": "良いクエリ", "score": 4}]},
    ]))
    g = XlingGenerator(client=fake)
    r = g.generate(_make_pattern(), n=3)
    # klingon entry rejected at schema validation
    rejected_queries = [c.get("query") for c, _ in r.rejected]
    assert "tlhIngan Hol" in rejected_queries
    accepted_queries = {q.query for q in r.accepted}
    assert "良いクエリ" in accepted_queries


def test_empty_groq_response_no_crash() -> None:
    fake = _FakeGroq()
    fake.scripted.append(ConsensusResult(
        calls=[
            JudgeCall(temperature=0.3, text="", parsed=None,
                      model="x", latency_ms=1, error="x", usage=None),
            JudgeCall(temperature=0.7, text="", parsed=None,
                      model="x", latency_ms=1, error="x", usage=None),
            JudgeCall(temperature=1.0, text="", parsed=None,
                      model="x", latency_ms=1, error="x", usage=None),
        ],
        primary_used=False, accepted=False,
        batch_id="b", groq_run_id="r", prompt_version="t",
        started_at="", finished_at="",
    ))
    g = XlingGenerator(client=fake)
    r = g.generate(_make_pattern(), n=3)
    assert r.accepted == []
    assert r.raw_candidate_count == 0


def test_low_quality_grades_rejected() -> None:
    fake = _FakeGroq()
    fake.scripted.append(fake._make([
        {"queries": [{"lang": "ja", "query": "ぐだぐだ",
                      "expected_match": True}]},
        {"queries": []},
        {"queries": []},
    ]))
    fake.scripted.append(fake._make([
        {"grades": [{"variant": "ぐだぐだ", "score": 1}]},
        {"grades": [{"variant": "ぐだぐだ", "score": 2}]},
        {"grades": [{"variant": "ぐだぐだ", "score": 1}]},
    ]))
    g = XlingGenerator(client=fake)
    r = g.generate(_make_pattern(), n=3)
    assert not any(q.query == "ぐだぐだ" for q in r.accepted)
    assert any("quality grade" in reason for _, reason in r.rejected)


def test_constants_match_spec() -> None:
    assert QUALITY_THRESHOLD == 4
    assert DEFAULT_MIN_COSINE == 0.62
