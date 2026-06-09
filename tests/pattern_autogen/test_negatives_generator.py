"""Tests for scripts/pattern_autogen/negatives_generator.py."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pytest

from scripts.pattern_autogen.groq_client import (
    ConsensusResult, JudgeCall,
)
from scripts.pattern_autogen.negatives_generator import (
    NEG_DUP_MAX, POS_DRIFT_MAX, QUALITY_THRESHOLD, NegativesGenerator,
)
from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Origin, Pattern, RouteConfig,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_pattern() -> Pattern:
    return Pattern(
        id="pat_concept_explain_001",
        topic="conceptual_explain",
        intent="explain_mobius_concept",
        examples=[
            "What is MOBIUS",
            "Explain MOBIUS",
            "Tell me about MOBIUS",
            "Define MOBIUS",
            "How does MOBIUS work",
        ],
        negative_examples=["What is a Möbius strip"],
        route=RouteConfig(primary_box="box_0",
                           synthesis_mode="conceptual_explanation"),
        cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="x", expected_match=True),
            CrossLingualTestQuery(lang="ja", query="y", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="z", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="w", expected_match=True),
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


class _FakeEncoder:
    def __init__(self, vectors):
        self.vectors = vectors

    def encode(self, texts, **kw):
        out = []
        for t in texts:
            key = t[len("passage: "):] if t.startswith("passage: ") else t
            out.append(self.vectors.get(key, [0.0, 0.0, 0.5, 0.5]))
        return np.asarray(out, dtype="float32")


def _norm(v):
    arr = np.asarray(v, dtype="float64")
    n = np.linalg.norm(arr)
    return (arr / n).tolist() if n > 0 else v


# ─────────────────────────────────────────────────────────────────────

def test_constants_match_spec() -> None:
    # POS_DRIFT_MAX = 0.97: good surface-similar disambiguators
    # (cos 0.85-0.93 to positives) are kept; only literal paraphrases of
    # positives are dropped.
    # NEG_DUP_MAX = 0.97: candidates conceptually adjacent to existing
    # negatives (e.g. Möbius strip vs Möbius function — both
    # mathematical, cluster at 0.92-0.96) are kept; only near-identical
    # negatives are dropped. The runtime NEG_MARGIN handles the actual
    # disambiguation gate.
    assert POS_DRIFT_MAX == 0.97
    assert NEG_DUP_MAX == 0.97
    assert QUALITY_THRESHOLD == 4


def test_pos_drift_gate_drops_too_close_to_positive() -> None:
    fake = _FakeGroq()
    fake.scripted.append(fake._make([
        {"negatives": ["What is the MOBIUS framework"]},  # too close to positive
        {"negatives": []},
        {"negatives": []},
    ]))
    p = _make_pattern()
    pos_v = _norm([1.0, 0.0, 0.0])
    near_pos = _norm([0.999, 0.01, 0.0])  # cos > 0.97 to positive
    encoder = _FakeEncoder({
        "What is MOBIUS": pos_v, "Explain MOBIUS": pos_v,
        "Tell me about MOBIUS": pos_v, "Define MOBIUS": pos_v,
        "How does MOBIUS work": pos_v,
        "What is a Möbius strip": _norm([0.0, 1.0, 0.0]),
        "What is the MOBIUS framework": near_pos,
    })
    g = NegativesGenerator(client=fake, encoder=encoder)
    r = g.generate(p, n=5)
    assert r.accepted == []
    assert any("too close to a positive" in reason
               for _, reason in r.rejected)


def test_neg_dup_gate_drops_existing_neg_duplicate() -> None:
    fake = _FakeGroq()
    fake.scripted.append(fake._make([
        {"negatives": ["The Mobius strip in topology"]},
        {"negatives": []},
        {"negatives": []},
    ]))
    p = _make_pattern()
    pos_v = _norm([1.0, 0.0, 0.0])
    existing_neg = _norm([0.0, 1.0, 0.0])
    near_existing_neg = _norm([0.0, 0.99, 0.05])
    encoder = _FakeEncoder({
        "What is MOBIUS": pos_v, "Explain MOBIUS": pos_v,
        "Tell me about MOBIUS": pos_v, "Define MOBIUS": pos_v,
        "How does MOBIUS work": pos_v,
        "What is a Möbius strip": existing_neg,
        "The Mobius strip in topology": near_existing_neg,
    })
    g = NegativesGenerator(client=fake, encoder=encoder)
    r = g.generate(p, n=5)
    assert r.accepted == []
    assert any("duplicate negative" in reason
               for _, reason in r.rejected)


def test_happy_path_far_neg_passes_grade() -> None:
    fake = _FakeGroq()
    fake.scripted.append(fake._make([
        {"negatives": ["Tell me about Mobius the Marvel character"]},
        {"negatives": []},
        {"negatives": []},
    ]))
    fake.scripted.append(fake._make([
        {"grades": [{"variant": "Tell me about Mobius the Marvel character", "score": 5}]},
        {"grades": [{"variant": "Tell me about Mobius the Marvel character", "score": 5}]},
        {"grades": [{"variant": "Tell me about Mobius the Marvel character", "score": 4}]},
    ]))
    p = _make_pattern()
    pos_v = _norm([1.0, 0.0, 0.0])
    far_neg = _norm([0.1, 0.1, 1.0])  # cos < 0.80 to positives
    encoder = _FakeEncoder({
        "What is MOBIUS": pos_v, "Explain MOBIUS": pos_v,
        "Tell me about MOBIUS": pos_v, "Define MOBIUS": pos_v,
        "How does MOBIUS work": pos_v,
        "What is a Möbius strip": _norm([0.0, 1.0, 0.0]),
        "Tell me about Mobius the Marvel character": far_neg,
    })
    g = NegativesGenerator(client=fake, encoder=encoder)
    r = g.generate(p, n=5)
    assert "Tell me about Mobius the Marvel character" in r.accepted


def test_low_quality_negative_rejected() -> None:
    fake = _FakeGroq()
    fake.scripted.append(fake._make([
        {"negatives": ["What is the capital of France"]},  # unrelated trivial
        {"negatives": []},
        {"negatives": []},
    ]))
    fake.scripted.append(fake._make([
        {"grades": [{"variant": "What is the capital of France", "score": 2}]},
        {"grades": [{"variant": "What is the capital of France", "score": 2}]},
        {"grades": [{"variant": "What is the capital of France", "score": 2}]},
    ]))
    p = _make_pattern()
    encoder = _FakeEncoder({
        "What is MOBIUS": _norm([1.0, 0.0, 0.0]),
        "Explain MOBIUS": _norm([1.0, 0.0, 0.0]),
        "Tell me about MOBIUS": _norm([1.0, 0.0, 0.0]),
        "Define MOBIUS": _norm([1.0, 0.0, 0.0]),
        "How does MOBIUS work": _norm([1.0, 0.0, 0.0]),
        "What is a Möbius strip": _norm([0.0, 1.0, 0.0]),
        "What is the capital of France": _norm([0.0, 0.0, 1.0]),
    })
    g = NegativesGenerator(client=fake, encoder=encoder)
    r = g.generate(p, n=5)
    assert "What is the capital of France" not in r.accepted
    assert any("quality grade" in reason
               for _, reason in r.rejected)


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
    p = _make_pattern()
    g = NegativesGenerator(client=fake, encoder=_FakeEncoder({}))
    r = g.generate(p, n=5)
    assert r.accepted == []
    assert r.raw_candidate_count == 0


def test_pattern_with_no_existing_negatives_works() -> None:
    """When pattern has empty negative_examples, only POS_DRIFT_MAX
    gate applies; NEG_DUP gate is a no-op."""
    fake = _FakeGroq()
    fake.scripted.append(fake._make([
        {"negatives": ["A novel disambiguator"]},
        {"negatives": []},
        {"negatives": []},
    ]))
    fake.scripted.append(fake._make([
        {"grades": [{"variant": "A novel disambiguator", "score": 5}]},
        {"grades": [{"variant": "A novel disambiguator", "score": 5}]},
        {"grades": [{"variant": "A novel disambiguator", "score": 4}]},
    ]))
    p = Pattern(
        id="pat_self_ref_identity_001", topic="self_reference",
        intent="x", examples=["a", "b", "c", "d", "e"],
        negative_examples=[],  # no existing negatives
        route=RouteConfig(primary_box="box_0", synthesis_mode="x"),
        cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="x", expected_match=True),
            CrossLingualTestQuery(lang="ja", query="y", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="z", expected_match=True),
            CrossLingualTestQuery(lang="zh", query="w", expected_match=True),
        ],
        origin=Origin(type="manual", date=_now()),
    )
    pos_v = _norm([1.0, 0.0, 0.0])
    far = _norm([0.0, 1.0, 0.0])
    encoder = _FakeEncoder({
        "a": pos_v, "b": pos_v, "c": pos_v, "d": pos_v, "e": pos_v,
        "A novel disambiguator": far,
    })
    g = NegativesGenerator(client=fake, encoder=encoder)
    r = g.generate(p, n=3)
    assert "A novel disambiguator" in r.accepted
