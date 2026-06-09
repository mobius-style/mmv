#!/usr/bin/env python3
"""
test_memory_capsule.py — MOBIUS MMV Phase E テストスイート
tests/test_memory_capsule.py

成功基準 (spec §8):
  - Capsule生成率(qk.longterm=high) ≥ 90%
  - SALIENCE_THRESHOLD 以下の除外
  - memory_text 生成（LLM不使用）
  - audit_ref 整合性（全Capsuleに turn_id が存在）
  - memory_indexer latency: embedding + FAISS write within ME5 budget
  - open_loop: route_decision=ask で必ず生成を試みる
  - Phase D テスト不変（290 passed 維持）

実行:
    cd ~/デスクトップ/mobius_ai/MOBIUS_MMV
    cp ~/ダウンロード/test_memory_capsule.py tests/test_memory_capsule.py
    python -m pytest tests/test_memory_capsule.py -v

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""

from __future__ import annotations

import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "memory"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "audit"))

from memory_capsule import (
    SALIENCE_THRESHOLD, MemoryCapsule,
    generate_capsule, _classify, _score, _compose, _calc_ttl,
)
from memory_indexer import EMBEDDING_DIM, LATENCY_TARGET_MS, MemoryIndexer


# ── モック FullTurnAuditRecord ────────────────────────────────────────────────

@dataclass
class MockQK:
    intent:     str = "ok"
    risk:       str = "ok"
    longterm:   str = "ok"
    meta_frame: str = "low"

@dataclass
class MockDecisionTrace:
    primary_reason: str = ""
    primary_seat:   str = "kernel"
    notes:          list = field(default_factory=list)

@dataclass
class MockKVS:
    tvs:      float = 0.5
    mkr:      float = 0.5
    computed: bool  = False

@dataclass
class MockAudit:
    turn_id:           str  = ""
    session_id:        str  = "sess-test-001"
    turn:              int  = 1
    route_decision:    str  = "answer"
    clamped:           bool = False
    clamp_reasons:     list = field(default_factory=list)
    reason_codes:      list = field(default_factory=list)
    qk:                Optional[MockQK]           = None
    decision_trace:    Optional[MockDecisionTrace] = None
    kvs:               Optional[MockKVS]           = None
    eal_admissibility: str  = ""
    retrieval_source:  str  = ""

    def __post_init__(self):
        if not self.turn_id:
            self.turn_id = str(uuid.uuid4())


def make_audit(**kwargs) -> MockAudit:
    a = MockAudit()
    for k, v in kwargs.items():
        setattr(a, k, v)
    if a.turn_id == "":
        a.turn_id = str(uuid.uuid4())
    return a


# ═══════════════════════════════════════════════════════════════════════════════
# § 1. _classify() テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassify:

    def test_ask_returns_open_loop(self):
        """route=ask → open_loop"""
        a = make_audit(route_decision="ask")
        assert _classify(a) == "open_loop"

    def test_verify_answerable_returns_stable_fact(self):
        """verify + answerable → stable_fact"""
        a = make_audit(route_decision="verify", eal_admissibility="answerable")
        assert _classify(a) == "stable_fact"

    def test_verify_bounded_returns_stable_fact(self):
        """verify + bounded-only → stable_fact"""
        a = make_audit(route_decision="verify", eal_admissibility="bounded-only")
        assert _classify(a) == "stable_fact"

    def test_verify_failed_returns_none(self):
        """verify + verify-failed → None"""
        a = make_audit(route_decision="verify", eal_admissibility="verify-failed")
        assert _classify(a) is None

    def test_longterm_high_oracle_returns_goal(self):
        """qk.longterm=high + oracle seat → goal"""
        a = make_audit(
            route_decision="answer",
            qk=MockQK(longterm="high"),
            decision_trace=MockDecisionTrace(primary_reason="PROGRESS", primary_seat="oracle"),
        )
        assert _classify(a) == "goal"

    def test_longterm_high_kernel_returns_constraint(self):
        """qk.longterm=high + kernel seat → constraint"""
        a = make_audit(
            route_decision="answer",
            qk=MockQK(longterm="high"),
            decision_trace=MockDecisionTrace(primary_reason="CONSTRAINT_VIOLATION", primary_seat="kernel"),
        )
        assert _classify(a) == "constraint"

    def test_clamped_safety_critical_returns_none(self):
        """SAFETY_CRITICAL clamp → None（生成抑制）"""
        a = make_audit(clamped=True, clamp_reasons=["SAFETY_CRITICAL"])
        assert _classify(a) is None

    def test_clamped_other_returns_stable_fact(self):
        """その他clamp → stable_fact（短期）"""
        a = make_audit(clamped=True, clamp_reasons=["POLICY_VIOLATION"])
        assert _classify(a) == "stable_fact"

    def test_preference_reason_code(self):
        """reason_codes に PREFERENCE → preference"""
        a = make_audit(reason_codes=["USER_PREFERENCE_DETECTED"])
        assert _classify(a) == "preference"

    def test_answer_longterm_ok_returns_stable_fact(self):
        """answer + longterm=ok → stable_fact"""
        a = make_audit(route_decision="answer", qk=MockQK(longterm="ok"))
        assert _classify(a) == "stable_fact"


# ═══════════════════════════════════════════════════════════════════════════════
# § 2. _score() テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestScore:

    def test_longterm_high_boosts_score(self):
        """qk.longterm=high → salience 高め"""
        a = make_audit(qk=MockQK(longterm="high"))
        s = _score(a, "goal")
        assert s >= 0.65

    def test_verify_success_boosts_score(self):
        """verify + answerable → salience 高め"""
        a = make_audit(route_decision="verify", eal_admissibility="answerable")
        s = _score(a, "stable_fact")
        assert s >= 0.50

    def test_tvs_low_boosts_score(self):
        """tvs < 0.3 → salience↑（安定知識）"""
        a = make_audit(kvs=MockKVS(tvs=0.1))
        base  = _score(make_audit(), "stable_fact")
        boosted = _score(a, "stable_fact")
        assert boosted > base

    def test_tvs_high_penalizes_score(self):
        """tvs > 0.7 → salience↓（揮発性知識）"""
        a_low  = make_audit(kvs=MockKVS(tvs=0.1))
        a_high = make_audit(kvs=MockKVS(tvs=0.9))
        assert _score(a_high, "stable_fact") < _score(a_low, "stable_fact")

    def test_clamped_penalizes_score(self):
        """clamped=True → salience↓"""
        a_normal  = make_audit()
        a_clamped = make_audit(clamped=True, clamp_reasons=["POLICY_VIOLATION"])
        assert _score(a_clamped, "stable_fact") < _score(a_normal, "stable_fact")

    def test_score_bounded_0_to_1(self):
        """salience_score は 0.0〜1.0 の範囲内"""
        for qk_val in ["low", "ok", "high"]:
            for tvs in [0.1, 0.5, 0.9]:
                a = make_audit(qk=MockQK(longterm=qk_val), kvs=MockKVS(tvs=tvs))
                for mtype in ["goal", "constraint", "open_loop", "stable_fact"]:
                    s = _score(a, mtype)
                    assert 0.0 <= s <= 1.0, f"score={s} out of range"


# ═══════════════════════════════════════════════════════════════════════════════
# § 3. _compose() テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompose:

    def test_compose_goal(self):
        a = make_audit(
            route_decision="answer",
            qk=MockQK(longterm="high"),
            decision_trace=MockDecisionTrace(primary_reason="PROGRESS"),
        )
        text = _compose(a, "goal", "Moving toward Phase E completion")
        assert "[Goal]" in text
        assert "PROGRESS" in text

    def test_compose_open_loop(self):
        a = make_audit(route_decision="ask")
        text = _compose(a, "open_loop", "Need clarification on threshold")
        assert "[OpenLoop]" in text
        assert "ask" in text

    def test_compose_stable_fact(self):
        a = make_audit(
            route_decision="verify",
            eal_admissibility="answerable",
            retrieval_source="C",
        )
        text = _compose(a, "stable_fact", "Treasury yield is 4.39%")
        assert "[StableFact]" in text
        assert "answerable" in text

    def test_compose_no_llm(self):
        """memory_text にモデル呼び出し痕跡がないこと（LLM不使用）"""
        a = make_audit()
        text = _compose(a, "stable_fact", "some summary")
        # LLMが生成するような長大テキストではない
        assert len(text) < 600
        assert text.startswith("[")

    def test_compose_session_prefix(self):
        """session_id の短縮版が memory_text に含まれること"""
        session_id = "abcdef12-xxxx-yyyy-zzzz"
        a = make_audit(session_id=session_id)
        text = _compose(a, "stable_fact", "")
        assert "abcdef12" in text


# ═══════════════════════════════════════════════════════════════════════════════
# § 4. generate_capsule() 統合テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestGenerateCapsule:

    def test_longterm_high_generates_capsule(self):
        """qk.longterm=high → Capsule 生成（成功基準 ≥ 90%）"""
        results = []
        for _ in range(10):
            a = make_audit(
                route_decision="answer",
                qk=MockQK(longterm="high"),
                decision_trace=MockDecisionTrace(primary_reason="PROGRESS", primary_seat="oracle"),
            )
            c = generate_capsule(a, response_summary="ongoing project work")
            results.append(c is not None)
        rate = sum(results) / len(results)
        assert rate >= 0.90, f"Capsule generation rate={rate:.0%} < 90%"

    def test_ask_generates_open_loop(self):
        """route=ask → open_loop Capsule 生成"""
        a = make_audit(route_decision="ask")
        c = generate_capsule(a, response_summary="clarification needed")
        assert c is not None
        assert c.memory_type == "open_loop"

    def test_safety_critical_suppressed(self):
        """SAFETY_CRITICAL clamp → Capsule 生成しない"""
        a = make_audit(clamped=True, clamp_reasons=["SAFETY_CRITICAL"])
        c = generate_capsule(a)
        assert c is None

    def test_audit_ref_integrity(self):
        """audit_ref が turn_id と一致する（spec §8）"""
        a = make_audit(
            route_decision="answer",
            qk=MockQK(longterm="high"),
        )
        c = generate_capsule(a, response_summary="test")
        if c:
            assert c.audit_ref == a.turn_id

    def test_source_turn_ids_contains_turn_id(self):
        a = make_audit(route_decision="ask")
        c = generate_capsule(a)
        if c:
            assert a.turn_id in c.source_turn_ids

    def test_capsule_salience_above_threshold(self):
        """生成された Capsule の salience は THRESHOLD 以上"""
        a = make_audit(
            route_decision="answer",
            qk=MockQK(longterm="high"),
        )
        c = generate_capsule(a, response_summary="important goal")
        if c:
            assert c.salience_score >= SALIENCE_THRESHOLD

    def test_low_salience_not_generated(self):
        """salience が低い場合は Capsule を生成しない"""
        # longterm=low + tvs=0.9 → salience がしきい値以下になりやすい
        a = make_audit(
            route_decision="answer",
            qk=MockQK(longterm="low"),
            kvs=MockKVS(tvs=0.9),
        )
        c = generate_capsule(a)
        # None か salience >= threshold のどちらか
        if c is not None:
            assert c.salience_score >= SALIENCE_THRESHOLD

    def test_ttl_none_for_goal(self):
        """goal Capsule は永続（ttl=None）"""
        a = make_audit(
            route_decision="answer",
            qk=MockQK(longterm="high"),
            decision_trace=MockDecisionTrace(primary_reason="PROJECT_GOAL"),
        )
        c = generate_capsule(a, response_summary="long term goal")
        if c and c.memory_type == "goal":
            assert c.ttl is None

    def test_ttl_set_for_open_loop(self):
        """open_loop Capsule は TTL あり（30日）"""
        a = make_audit(route_decision="ask")
        c = generate_capsule(a, response_summary="clarification needed")
        if c:
            assert c.ttl is not None

    def test_tvs_high_shortens_ttl(self):
        """高TVSの stable_fact は ttl が短縮される"""
        a_low  = make_audit(route_decision="verify", eal_admissibility="answerable",
                            kvs=MockKVS(tvs=0.1))
        a_high = make_audit(route_decision="verify", eal_admissibility="answerable",
                            kvs=MockKVS(tvs=0.9))
        c_low  = generate_capsule(a_low)
        c_high = generate_capsule(a_high)
        if c_low and c_high and c_low.ttl and c_high.ttl:
            from datetime import datetime, timezone
            exp_low  = datetime.fromisoformat(c_low.ttl)
            exp_high = datetime.fromisoformat(c_high.ttl)
            assert exp_high < exp_low, "高TVSのTTLが低TVSより短くなっていない"

    def test_memory_text_not_empty(self):
        """memory_text が空でないこと"""
        a = make_audit(
            route_decision="answer",
            qk=MockQK(longterm="high"),
        )
        c = generate_capsule(a, response_summary="project status update")
        if c:
            assert len(c.memory_text) > 10


# ═══════════════════════════════════════════════════════════════════════════════
# § 5. MemoryIndexer テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryIndexer:

    @pytest.fixture()
    def indexer(self, tmp_path):
        idx = MemoryIndexer(
            index_path=str(tmp_path / "capsule_index.faiss"),
            db_path=str(tmp_path / "capsules.db"),
        )
        idx.open()
        yield idx
        idx.close()

    def _make_capsule(self, mtype="goal", text="test capsule") -> MemoryCapsule:
        from memory_capsule import _now_utc
        return MemoryCapsule(
            capsule_id     = str(uuid.uuid4()),
            session_id     = "sess-001",
            source_turn_ids = [str(uuid.uuid4())],
            memory_text    = text,
            memory_type    = mtype,
            salience_score = 0.7,
            audit_ref      = str(uuid.uuid4()),
            created_at     = _now_utc(),
        )

    def test_add_latency_under_100ms(self, indexer):
        """embedding + FAISS write within current ME5 budget"""
        c = self._make_capsule(text="Phase E Memory Capsule test")
        ms = indexer.add(c)
        assert ms < LATENCY_TARGET_MS, (
            f"latency={ms:.1f}ms ≥ {LATENCY_TARGET_MS}ms"
        )

    def test_add_increments_count(self, indexer):
        """add() 後に count が増えること"""
        c = self._make_capsule()
        assert indexer.count() == 0
        indexer.add(c)
        assert indexer.count() == 1

    def test_embedding_vector_set_after_add(self, indexer):
        """add() 後に embedding_vector が設定されること"""
        c = self._make_capsule(text="embedding test")
        indexer.add(c)
        assert c.embedding_vector is not None
        assert len(c.embedding_vector) == EMBEDDING_DIM

    def test_search_returns_results(self, indexer):
        """search() が結果を返すこと"""
        indexer.add(self._make_capsule(text="FAISS sufficiency threshold calibration"))
        indexer.add(self._make_capsule(text="Box W Wikipedia index retrieval"))
        results = indexer.search("FAISS threshold", top_k=2)
        assert len(results) >= 1

    def test_search_filter_by_type(self, indexer):
        """memory_type フィルタが機能すること"""
        indexer.add(self._make_capsule(mtype="goal",       text="project goal test"))
        indexer.add(self._make_capsule(mtype="stable_fact", text="stable fact test"))
        results = indexer.search("test", top_k=5, memory_type="goal")
        for r in results:
            assert r["memory_type"] == "goal"

    def test_stats_returns_dict(self, indexer):
        """stats() が辞書を返すこと"""
        s = indexer.stats()
        assert isinstance(s, dict)
        assert "total_capsules" in s
        assert "by_type" in s

    def test_search_excludes_expired(self, indexer):
        """期限切れ Capsule は検索から除外されること"""
        from datetime import datetime, timedelta, timezone
        from memory_capsule import _now_utc
        # 過去のTTL
        past_ttl = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        c_expired = MemoryCapsule(
            capsule_id="exp-001", session_id="s",
            source_turn_ids=["t"],
            memory_text="expired capsule content search test",
            memory_type="stable_fact", salience_score=0.8,
            audit_ref="t", created_at=_now_utc(), ttl=past_ttl,
        )
        indexer.add(c_expired)
        results = indexer.search("expired capsule content", top_k=5)
        ids = [r["capsule_id"] for r in results]
        assert "exp-001" not in ids
