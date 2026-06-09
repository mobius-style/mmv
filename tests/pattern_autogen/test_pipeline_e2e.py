"""End-to-end pipeline tests — variants → negatives → xling → grader →
conflict checker.

Phase 2 Commit 17. Mock Groq + encoder; assert the data flow connects."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from scripts.pattern_autogen.conflict_checker import (
    CONFLICT_THRESHOLD, ConflictChecker,
)
from scripts.pattern_autogen.groq_client import (
    ConsensusResult, JudgeCall,
)
from scripts.pattern_autogen.negatives_generator import (
    NegativesGenerator,
)
from scripts.pattern_autogen.quality_grader import (
    QUALITY_THRESHOLD, QualityGrader,
)
from scripts.pattern_autogen.variants_generator import (
    VariantsGenerator,
)
from scripts.pattern_autogen.xling_query_generator import (
    XlingGenerator,
)
from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Origin, Pattern, RouteConfig,
)


def _now():
    return datetime.now(timezone.utc)


def _make_pattern(pid: str = "pat_self_ref_identity_001",
                  topic: str = "self_reference",
                  examples=None) -> Pattern:
    return Pattern(
        id=pid, topic=topic, intent="describe_self",
        examples=examples or ["a", "b", "c", "d", "e"],
        negative_examples=["x", "y"],
        route=RouteConfig(primary_box="box_0",
                           synthesis_mode="identity_response"),
        cross_lingual_test_queries=[
            CrossLingualTestQuery(lang="ja", query="ja1",
                                   expected_match=True, min_cosine=0.6),
            CrossLingualTestQuery(lang="ja", query="ja2",
                                   expected_match=False),
            CrossLingualTestQuery(lang="zh", query="zh1",
                                   expected_match=True, min_cosine=0.6),
            CrossLingualTestQuery(lang="zh", query="zh2",
                                   expected_match=False),
        ],
        origin=Origin(type="manual", date=_now()),
    )


class _FakeGroq:
    def __init__(self):
        self.scripted: list[ConsensusResult] = []

    def _make(self, parsed_per_call):
        calls = [
            JudgeCall(temperature=t, text=json.dumps(p), parsed=p,
                       model="x", latency_ms=1, error=None, usage=None)
            for t, p in zip((0.3, 0.7, 1.0), parsed_per_call)
        ]
        return ConsensusResult(
            calls=calls, primary_used=True, accepted=True,
            batch_id="b", groq_run_id="r", prompt_version="t",
            started_at="", finished_at="",
        )

    def consensus(self, sys_p, user_p, **kw):
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


# ─── QualityGrader ────────────────────────────────────────────────────

def test_quality_grader_aggregates_median() -> None:
    fake = _FakeGroq()
    fake.scripted.append(fake._make([
        {"overall": 4, "intent_clarity": 5, "example_coverage": 4,
         "negative_discrimination": 4, "xling_consistency": 4,
         "notes": "good"},
        {"overall": 5, "intent_clarity": 5, "example_coverage": 5,
         "negative_discrimination": 4, "xling_consistency": 5,
         "notes": "great"},
        {"overall": 4, "intent_clarity": 4, "example_coverage": 4,
         "negative_discrimination": 3, "xling_consistency": 4,
         "notes": "fine"},
    ]))
    g = QualityGrader(client=fake)
    score = g.grade(_make_pattern())
    assert score.overall == 4.0  # median of [4, 5, 4]
    assert score.intent_clarity == 5.0
    assert score.passes(threshold=4)


def test_quality_grader_failed_calls_yield_zero() -> None:
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
    g = QualityGrader(client=fake)
    score = g.grade(_make_pattern())
    assert score.overall == 0.0
    assert not score.passes()


def test_quality_threshold_constant() -> None:
    assert QUALITY_THRESHOLD == 4


# ─── ConflictChecker ──────────────────────────────────────────────────

def test_conflict_checker_threshold_constant() -> None:
    assert CONFLICT_THRESHOLD == 0.85


def test_conflict_checker_finds_collision(tmp_path: Path) -> None:
    """Two patterns with overlapping example embeddings → conflict reported."""
    cfg = tmp_path / "config" / "pattern_library"
    cfg.mkdir(parents=True)

    overlap = _norm([1.0, 0.0, 0.0])
    distinct1 = _norm([0.0, 1.0, 0.0])
    distinct2 = _norm([0.0, 0.0, 1.0])
    distinct3 = _norm([0.5, 0.5, 0.0])
    distinct4 = _norm([0.5, 0.0, 0.5])
    encoder = _FakeEncoder({
        "p1_ex": overlap, "p1_other": distinct1,
        "c": distinct2, "d": distinct3, "e": distinct4,
        "p2_ex": overlap,  # collision with p1_ex
        "p2_other": _norm([0.0, 0.0, 1.0]),
        "c2": distinct3, "d2": distinct4, "e2": _norm([0.3, 0.4, 0.5]),
    })

    p1 = _make_pattern(
        pid="pat_self_ref_identity_001",
        examples=["p1_ex", "p1_other", "c", "d", "e"],
    )
    p2 = _make_pattern(
        pid="pat_self_ref_identity_002",
        examples=["p2_ex", "p2_other", "c2", "d2", "e2"],
    )
    f = cfg / "self_reference.jsonl"
    with f.open("w", encoding="utf-8") as fh:
        fh.write(p1.model_dump_json() + "\n")
        fh.write(p2.model_dump_json() + "\n")

    cc = ConflictChecker(config_dir=cfg, encoder=encoder)
    rep = cc.check(p1)
    assert rep.has_conflict
    assert rep.conflicts[0][0] == p2.id


def test_conflict_checker_no_self_collision(tmp_path: Path) -> None:
    cfg = tmp_path / "config" / "pattern_library"
    cfg.mkdir(parents=True)
    p = _make_pattern()
    f = cfg / "self_reference.jsonl"
    with f.open("w", encoding="utf-8") as fh:
        fh.write(p.model_dump_json() + "\n")
    cc = ConflictChecker(config_dir=cfg, encoder=_FakeEncoder({}))
    rep = cc.check(p)  # candidate matches the only pattern (itself)
    assert not rep.has_conflict


def test_scan_pairwise_clean_library(tmp_path: Path) -> None:
    """Two patterns with distinct embeddings → no pairs reported."""
    cfg = tmp_path / "config" / "pattern_library"
    cfg.mkdir(parents=True)

    p1 = _make_pattern(pid="pat_self_ref_identity_001",
                        examples=["a", "b", "c", "d", "e"])
    p2 = _make_pattern(pid="pat_concept_explain_001",
                        topic="conceptual_explain",
                        examples=["x", "y", "z", "w", "v"])
    f = cfg / "test.jsonl"
    with f.open("w", encoding="utf-8") as fh:
        fh.write(p1.model_dump_json() + "\n")
        fh.write(p2.model_dump_json() + "\n")
    encoder = _FakeEncoder({
        "a": _norm([1, 0, 0, 0]), "b": _norm([0.95, 0.1, 0, 0]),
        "c": _norm([0.9, 0.2, 0, 0]), "d": _norm([0.85, 0.3, 0, 0]),
        "e": _norm([0.8, 0.4, 0, 0]),
        "x": _norm([0, 0, 1, 0]), "y": _norm([0, 0, 0.9, 0.2]),
        "z": _norm([0, 0, 0.85, 0.3]), "w": _norm([0, 0, 0.8, 0.4]),
        "v": _norm([0, 0, 0.75, 0.5]),
    })
    cc = ConflictChecker(config_dir=cfg, encoder=encoder)
    rep = cc.scan_pairwise()
    assert rep.pairs == []


# ─── E2E pipeline ─────────────────────────────────────────────────────

def test_pipeline_e2e_chain() -> None:
    """Variants → Negatives → Xling → Grader. Mock all Groq calls."""
    fake_v = _FakeGroq()
    fake_n = _FakeGroq()
    fake_x = _FakeGroq()
    fake_q = _FakeGroq()

    # Variants stage
    fake_v.scripted.append(fake_v._make([
        {"variants": ["new variant 1"]},
        {"variants": ["new variant 2"]},
        {"variants": ["new variant 3"]},
    ]))
    fake_v.scripted.append(fake_v._make([
        {"grades": [
            {"variant": "new variant 1", "score": 5},
            {"variant": "new variant 2", "score": 5},
            {"variant": "new variant 3", "score": 4},
        ]},
        {"grades": [
            {"variant": "new variant 1", "score": 5},
            {"variant": "new variant 2", "score": 4},
            {"variant": "new variant 3", "score": 4},
        ]},
        {"grades": [
            {"variant": "new variant 1", "score": 5},
            {"variant": "new variant 2", "score": 5},
            {"variant": "new variant 3", "score": 4},
        ]},
    ]))
    p = _make_pattern()
    enc = _FakeEncoder({
        "a": _norm([1, 0, 0, 0]), "b": _norm([1, 0, 0, 0]),
        "c": _norm([1, 0, 0, 0]), "d": _norm([1, 0, 0, 0]),
        "e": _norm([1, 0, 0, 0]),
        "new variant 1": _norm([0, 1, 0, 0]),
        "new variant 2": _norm([0, 0, 1, 0]),
        "new variant 3": _norm([0, 0, 0, 1]),
    })
    v_result = VariantsGenerator(client=fake_v, encoder=enc).generate(p, per_call_n=2)
    assert len(v_result.accepted) == 3

    # Negatives stage
    fake_n.scripted.append(fake_n._make([
        {"negatives": ["neg disambig 1"]},
        {"negatives": ["neg disambig 2"]},
        {"negatives": []},
    ]))
    fake_n.scripted.append(fake_n._make([
        {"grades": [
            {"variant": "neg disambig 1", "score": 5},
            {"variant": "neg disambig 2", "score": 4},
        ]},
        {"grades": [
            {"variant": "neg disambig 1", "score": 4},
            {"variant": "neg disambig 2", "score": 5},
        ]},
        {"grades": [
            {"variant": "neg disambig 1", "score": 5},
            {"variant": "neg disambig 2", "score": 4},
        ]},
    ]))
    enc_n = _FakeEncoder({
        "a": _norm([1, 0, 0, 0]), "b": _norm([1, 0, 0, 0]),
        "c": _norm([1, 0, 0, 0]), "d": _norm([1, 0, 0, 0]),
        "e": _norm([1, 0, 0, 0]),
        "x": _norm([0, 1, 0, 0]), "y": _norm([0, 0, 1, 0]),
        "neg disambig 1": _norm([0, 0.5, 0.5, 0]),
        "neg disambig 2": _norm([0, 0.3, 0.7, 0]),
    })
    n_result = NegativesGenerator(client=fake_n, encoder=enc_n).generate(p, n=3)
    assert len(n_result.accepted) >= 1  # at least one accepted

    # Xling stage
    fake_x.scripted.append(fake_x._make([
        {"queries": [{"lang": "ja", "query": "新しい質問",
                      "expected_match": True}]},
        {"queries": [{"lang": "zh", "query": "新问题",
                      "expected_match": True}]},
        {"queries": []},
    ]))
    fake_x.scripted.append(fake_x._make([
        {"grades": [
            {"variant": "新しい質問", "score": 5},
            {"variant": "新问题", "score": 4},
        ]},
        {"grades": [
            {"variant": "新しい質問", "score": 4},
            {"variant": "新问题", "score": 5},
        ]},
        {"grades": [
            {"variant": "新しい質問", "score": 5},
            {"variant": "新问题", "score": 4},
        ]},
    ]))
    x_result = XlingGenerator(client=fake_x).generate(p, n=3)
    assert len(x_result.accepted) >= 1

    # Quality grade
    fake_q.scripted.append(fake_q._make([
        {"overall": 5, "intent_clarity": 5, "example_coverage": 5,
         "negative_discrimination": 4, "xling_consistency": 4,
         "notes": "good"},
        {"overall": 5, "intent_clarity": 5, "example_coverage": 4,
         "negative_discrimination": 5, "xling_consistency": 4,
         "notes": "ok"},
        {"overall": 4, "intent_clarity": 5, "example_coverage": 4,
         "negative_discrimination": 4, "xling_consistency": 4,
         "notes": "fine"},
    ]))
    q_score = QualityGrader(client=fake_q).grade(p)
    assert q_score.passes()  # overall median = 5
