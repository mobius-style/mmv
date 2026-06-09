"""Tests for scripts/pattern_autogen/variants_generator.py — mock Groq + encoder."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import numpy as np
import pytest

from scripts.pattern_autogen.groq_client import (
    AutogenGroqClient, ConsensusResult, JudgeCall,
)
from scripts.pattern_autogen.variants_generator import (
    CONFLICT_COSINE, QUALITY_THRESHOLD, VariantsGenerator,
)
from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Origin, Pattern, RouteConfig,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_pattern() -> Pattern:
    return Pattern(
        id="pat_self_ref_identity_001",
        topic="self_reference",
        intent="describe_self",
        examples=[
            "What are your characteristics",
            "Describe yourself",
            "Tell me about yourself",
            "What defines you",
            "Who are you",
        ],
        negative_examples=["What is a Möbius strip"],
        route=RouteConfig(primary_box="box_0",
                           synthesis_mode="identity_response"),
        cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="x", expected_match=True),
            CrossLingualTestQuery(lang="ja", query="y", expected_match=False),
            CrossLingualTestQuery(lang="zh", query="z", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="w", expected_match=False),
        ],
        origin=Origin(type="manual", date=_now()),
    )


# ─── Stubs ────────────────────────────────────────────────────────────

class _FakeGroqAdapter:
    """Substitute for AutogenGroqClient — returns scripted ConsensusResults."""

    def __init__(self) -> None:
        self.scripted: list[ConsensusResult] = []
        self.calls_log: list[tuple[str, str]] = []

    def _make_consensus(
        self, parsed_per_call: list[dict],
        primary_used: bool = True, accepted: bool = True,
    ) -> ConsensusResult:
        calls = [
            JudgeCall(
                temperature=t, text=json.dumps(parsed),
                parsed=parsed, model="openai/gpt-oss-120b",
                latency_ms=1, error=None, usage=None,
            )
            for t, parsed in zip((0.3, 0.7, 1.0), parsed_per_call)
        ]
        return ConsensusResult(
            calls=calls, primary_used=primary_used, accepted=accepted,
            batch_id="bat_test", groq_run_id="run_test",
            prompt_version="test_v1",
            started_at="2026-04-26T00:00:00Z",
            finished_at="2026-04-26T00:00:01Z",
        )

    def consensus(self, system_prompt, user_prompt, **kwargs):
        self.calls_log.append((system_prompt[:30], user_prompt[:60]))
        if self.scripted:
            return self.scripted.pop(0)
        return self._make_consensus(
            [{"variants": []}, {"variants": []}, {"variants": []}],
            primary_used=False, accepted=False,
        )


class _FakeEncoder:
    """Returns deterministic embeddings keyed by string content."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors

    def encode(self, texts, **kwargs):
        out = []
        for t in texts:
            # strip "passage: " prefix
            key = t[len("passage: "):] if t.startswith("passage: ") else t
            v = self.vectors.get(key, [0.0, 0.0, 1.0, 0.0])  # default unique
            out.append(v)
        return np.asarray(out, dtype="float32")


# ─── Helpers ─────────────────────────────────────────────────────────

def _norm_l2(v: list[float]) -> list[float]:
    arr = np.asarray(v, dtype="float64")
    n = np.linalg.norm(arr)
    if n == 0:
        return v
    return (arr / n).tolist()


# ─── Tests ────────────────────────────────────────────────────────────

def test_normalize_collapses_whitespace_and_case() -> None:
    g = VariantsGenerator(client=_FakeGroqAdapter(), encoder=_FakeEncoder({}))
    assert g._normalize("Hello   World") == "hello world"
    assert g._normalize(" PING ") == "ping"


def test_dedup_drops_case_and_whitespace_duplicates() -> None:
    g = VariantsGenerator(client=_FakeGroqAdapter(), encoder=_FakeEncoder({}))
    out = g._dedup([
        "Describe yourself",
        " describe   YOURSELF ",   # dupe
        "Tell me about you",
        "",                        # empty drops
        "tell me about you",       # dupe
    ])
    assert out == ["Describe yourself", "Tell me about you"]


def test_generate_returns_only_high_grade_non_conflicting() -> None:
    fake = _FakeGroqAdapter()
    # Stage 1: generator returns 4 candidates across 3 temperatures
    fake.scripted.append(fake._make_consensus(
        parsed_per_call=[
            {"variants": ["What is your essence", "Explain your purpose"]},
            {"variants": ["What makes you special"]},
            {"variants": ["Tell me more about you", "Describe yourself"]},
        ]
    ))
    # After dedup ("Describe yourself" matches existing example so will be
    # dropped by conflict filter; "Tell me more about you" is unique;
    # others are unique).
    # Stage 3: grader scores each kept candidate
    fake.scripted.append(fake._make_consensus(
        parsed_per_call=[
            {"grades": [
                {"variant": "What is your essence", "score": 5},
                {"variant": "Explain your purpose", "score": 4},
                {"variant": "What makes you special", "score": 3},
                {"variant": "Tell me more about you", "score": 4},
            ]},
            {"grades": [
                {"variant": "What is your essence", "score": 5},
                {"variant": "Explain your purpose", "score": 4},
                {"variant": "What makes you special", "score": 3},
                {"variant": "Tell me more about you", "score": 5},
            ]},
            {"grades": [
                {"variant": "What is your essence", "score": 5},
                {"variant": "Explain your purpose", "score": 4},
                {"variant": "What makes you special", "score": 3},
                {"variant": "Tell me more about you", "score": 4},
            ]},
        ]
    ))
    # Encoder: existing examples on a vector; "Describe yourself" candidate
    # collides with existing; others are far apart
    p = _make_pattern()
    common = _norm_l2([1.0, 0.0, 0.0])
    near_dup = _norm_l2([0.99, 0.05, 0.0])
    far = _norm_l2([0.0, 1.0, 0.0])
    encoder = _FakeEncoder({
        # existing examples
        "What are your characteristics": common,
        "Describe yourself": common,
        "Tell me about yourself": common,
        "What defines you": common,
        "Who are you": common,
        # candidates
        "What is your essence": far,
        "Explain your purpose": far,
        "What makes you special": far,
        "Tell me more about you": far,
        "Describe yourself": near_dup,  # collision via _conflict_filter
    })
    g = VariantsGenerator(client=fake, encoder=encoder)
    result = g.generate(p, per_call_n=2, batch_id="bat_test_xy")

    # 4 unique candidates after dedup ("Describe yourself" was the dupe
    # but it was already in existing examples; cosine 0.99 to a passage of
    # itself but the conflict filter compares CANDIDATE encodings vs
    # EXISTING encodings — we used near_dup for the candidate "Describe
    # yourself" so it gets dropped at the conflict stage).
    assert "Describe yourself" not in result.accepted
    # "What makes you special" was scored 3 — below threshold
    assert "What makes you special" not in result.accepted
    # "What is your essence" all-5 → accepted
    assert "What is your essence" in result.accepted
    # "Explain your purpose" all-4 → accepted
    assert "Explain your purpose" in result.accepted
    # "Tell me more about you" median 4 → accepted
    assert "Tell me more about you" in result.accepted
    # raw count includes the dupe before conflict filtering
    assert result.raw_candidate_count >= 4


def test_generate_handles_empty_groq_response() -> None:
    fake = _FakeGroqAdapter()
    # generator returns nothing parseable
    fake.scripted.append(ConsensusResult(
        calls=[
            JudgeCall(temperature=0.3, text="", parsed=None,
                      model="openai/gpt-oss-120b", latency_ms=1,
                      error="rate_limit", usage=None),
            JudgeCall(temperature=0.7, text="", parsed=None,
                      model="openai/gpt-oss-120b", latency_ms=1,
                      error="rate_limit", usage=None),
            JudgeCall(temperature=1.0, text="", parsed=None,
                      model="openai/gpt-oss-120b", latency_ms=1,
                      error="rate_limit", usage=None),
        ],
        primary_used=False, accepted=False,
        batch_id="bat_e", groq_run_id="run_e", prompt_version="t",
        started_at="", finished_at="",
    ))
    g = VariantsGenerator(client=fake, encoder=_FakeEncoder({}))
    result = g.generate(_make_pattern(), per_call_n=3, batch_id="b")
    assert result.accepted == []
    assert result.rejected == []
    assert result.raw_candidate_count == 0


def test_generate_does_not_crash_on_partial_grader_output() -> None:
    """If grader call returns malformed/missing grades for some candidates,
    those candidates fall to score 0 and get rejected (not crash)."""
    fake = _FakeGroqAdapter()
    fake.scripted.append(fake._make_consensus(
        parsed_per_call=[
            {"variants": ["a", "b"]},
            {"variants": ["a", "b"]},
            {"variants": ["a", "b"]},
        ],
    ))
    # Grader: only "a" graded across calls; "b" never graded
    fake.scripted.append(fake._make_consensus(
        parsed_per_call=[
            {"grades": [{"variant": "a", "score": 5}]},
            {"grades": [{"variant": "a", "score": 4}]},
            {"grades": [{"variant": "a", "score": 4}]},
        ],
    ))
    p = _make_pattern()
    far = _norm_l2([0.0, 1.0, 0.0])
    common = _norm_l2([1.0, 0.0, 0.0])
    encoder = _FakeEncoder({
        "What are your characteristics": common, "Describe yourself": common,
        "Tell me about yourself": common, "What defines you": common,
        "Who are you": common, "a": far, "b": far,
    })
    g = VariantsGenerator(client=fake, encoder=encoder)
    result = g.generate(p, per_call_n=2)
    assert "a" in result.accepted
    assert "b" not in result.accepted
    # "b" rejected because no grade → falls below threshold
    rejected_names = [t for t, _ in result.rejected]
    assert "b" in rejected_names


def test_dedup_in_conflict_filter_with_existing() -> None:
    """A candidate that exactly matches an existing example string-wise
    is still subject to the cosine conflict filter (not an early
    string-equality check). When cosine >= 0.95, drop with
    'duplicate of existing example' reason."""
    fake = _FakeGroqAdapter()
    fake.scripted.append(fake._make_consensus(
        parsed_per_call=[
            {"variants": ["Who are you"]},
            {"variants": []},
            {"variants": []},
        ],
    ))
    fake.scripted.append(fake._make_consensus(
        parsed_per_call=[
            {"grades": [{"variant": "Who are you", "score": 5}]}
            for _ in range(3)
        ],
    ))
    p = _make_pattern()
    common = _norm_l2([1.0, 0.0, 0.0])
    encoder = _FakeEncoder({
        # all existing + candidate same vector → cosine ~1.0
        "What are your characteristics": common, "Describe yourself": common,
        "Tell me about yourself": common, "What defines you": common,
        "Who are you": common,
    })
    g = VariantsGenerator(client=fake, encoder=encoder)
    result = g.generate(p, per_call_n=1)
    assert result.accepted == []
    assert any("duplicate" in reason
               for _, reason in result.rejected)


def test_constants_match_spec() -> None:
    """Spec-mandated thresholds must not drift silently."""
    assert CONFLICT_COSINE == 0.95
    assert QUALITY_THRESHOLD == 4
