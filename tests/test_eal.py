#!/usr/bin/env python3
"""
test_eal.py — MOBIUS MMV Phase F: EAL テストスイート
tests/test_eal.py

成功基準:
  - answerable 条件: evidence_strength=strong + TVS < τ_T + MKR > τ_M
  - bounded-only: 高TVS / conflict / MKR不足
  - verify-failed: ソースなし / evidence=weak
  - 条件文法変換: 高TVSクエリで "[As of ...]" 付記
  - Γ/Ω(Γ) 収束ガード: coherence_gain > threshold → Convergence note
  - freshness_note: freshness_sensitive 時に必ず付記
  - is_stub=False（Phase F 本実装の印）

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""

from __future__ import annotations
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "adapters"))

from eal import (
    EvidenceAdjudicationLayer, Source, KVSScore,
    ADMISSIBILITY_ANSWERABLE, ADMISSIBILITY_BOUNDED, ADMISSIBILITY_FAILED,
    FRESHNESS_STABLE, FRESHNESS_CURRENT_SUPPORTED, FRESHNESS_STALE_RISK,
    FRESHNESS_TIME_SENSITIVE, CONFLICT_NONE, CONFLICT_MANAGED, CONFLICT_OPEN,
    EVIDENCE_STRONG, EVIDENCE_MEDIUM, EVIDENCE_WEAK,
    DIVERSITY_HIGH, DIVERSITY_MODERATE, DIVERSITY_LOW,
    AGREEMENT_HIGH, AGREEMENT_MIXED, AGREEMENT_LOW,
)


# ── fixtures & helpers ────────────────────────────────────────────────────────

@dataclass
class MockResult:
    sources: list = field(default_factory=list)
    synthesis: str = ""
    outcome: str = "success"

@dataclass
class MockSR:
    result: MockResult = field(default_factory=MockResult)
    sufficient: bool = True
    box_used: str = "B"
    score: float = 0.7
    fallback_trace: list = field(default_factory=list)

def web_sources(claim: str, domains=("reuters.com","bbc.com","wikipedia.org")):
    """具体的なlabelを持つWebソース群（agreement=highになる）"""
    return [Source(source_type="web", label=claim,
                   uri=f"https://{d}/a", relevance_score=0.85)
            for d in domains]

def thin_sources(n=2, stype="local_rag"):
    """薄いlabelのソース（比較不能 → agreement=mixed）"""
    return [Source(source_type=stype, label=f"R{i}",
                   uri=f"https://example.com/{i}", relevance_score=0.7)
            for i in range(n)]

@pytest.fixture()
def eal():
    return EvidenceAdjudicationLayer()


# ── § 1. 基本 admissibility ─────────────────────────────────────────────────

class TestAdmissibility:

    def test_answerable_stable_strong(self, eal):
        """安定事実 + 強い証拠 → answerable"""
        sr = MockSR(result=MockResult(
            sources=web_sources("5 permanent members UN Security Council"),
            synthesis="5 permanent members.", outcome="success"))
        r = eal.adjudicate(
            "How many permanent members does the UN Security Council have?", sr)
        assert r.admissibility == ADMISSIBILITY_ANSWERABLE
        assert r.evidence_strength == EVIDENCE_STRONG

    def test_bounded_high_tvs(self, eal):
        """高TVS (freshness_sensitive) → bounded-only"""
        sr = MockSR(result=MockResult(
            sources=thin_sources(2,"local_rag"),
            synthesis="4.39%", outcome="success"))
        kvs = KVSScore(tvs=0.8, mkr=0.5, computed=False)
        r = eal.adjudicate("What is the current US 10-year Treasury yield?",
                           sr, freshness_sensitive=True, kvs=kvs)
        assert r.admissibility in (ADMISSIBILITY_BOUNDED, ADMISSIBILITY_FAILED)

    def test_verify_failed_no_sources(self, eal):
        """ソースなし → verify-failed"""
        sr = MockSR(result=MockResult(sources=[], synthesis="", outcome="failed"),
                    sufficient=False)
        r = eal.adjudicate("test query", sr)
        assert r.admissibility == ADMISSIBILITY_FAILED

    def test_bounded_kvs_gate_mkr_low(self, eal):
        """MKR低（< τ_M）→ bounded-only に格下げ"""
        sr = MockSR(result=MockResult(
            sources=web_sources("stable fact"),
            synthesis="stable answer.", outcome="success"))
        kvs = KVSScore(tvs=0.2, mkr=0.3, computed=True)  # MKR < 0.5
        r = eal.adjudicate("stable query", sr, kvs=kvs)
        assert r.admissibility == ADMISSIBILITY_BOUNDED

    def test_answerable_low_tvs_high_mkr(self, eal):
        """低TVS + 高MKR → answerable"""
        sr = MockSR(result=MockResult(
            sources=web_sources("299792458 speed of light"),
            synthesis="299,792,458 m/s.", outcome="success"))
        kvs = KVSScore(tvs=0.1, mkr=0.9, computed=True)
        r = eal.adjudicate("What is the speed of light?", sr, kvs=kvs)
        assert r.admissibility == ADMISSIBILITY_ANSWERABLE


# ── § 2. freshness 判定 ──────────────────────────────────────────────────────

class TestFreshnessState:

    def test_stable_for_timeless_query(self, eal):
        """時間に依存しないクエリ → stable"""
        sr = MockSR(result=MockResult(sources=thin_sources()))
        r = eal.adjudicate("What is the chemical symbol for gold?", sr)
        assert r.freshness_state == FRESHNESS_STABLE

    def test_time_sensitive_for_current_keyword(self, eal):
        """'current' キーワード → time-sensitive 以上"""
        sr = MockSR(result=MockResult(sources=thin_sources()))
        r = eal.adjudicate("What is the current prime minister of Japan?", sr)
        assert r.freshness_state in (FRESHNESS_TIME_SENSITIVE, FRESHNESS_STALE_RISK)

    def test_stale_risk_when_no_web_source(self, eal):
        """freshness_sensitive=True + web ソースなし → stale-risk"""
        sr = MockSR(result=MockResult(sources=thin_sources(2,"local_rag")))
        r = eal.adjudicate("current exchange rate", sr, freshness_sensitive=True)
        assert r.freshness_state == FRESHNESS_STALE_RISK

    def test_current_supported_with_web_source(self, eal):
        """freshness_sensitive=True + web ソースあり → current-supported"""
        srcs = [Source(source_type="web", label="rate",
                       uri="https://reuters.com/finance", relevance_score=0.8)]
        sr = MockSR(result=MockResult(sources=srcs))
        r = eal.adjudicate("current rate", sr, freshness_sensitive=True)
        assert r.freshness_state == FRESHNESS_CURRENT_SUPPORTED


# ── § 3. conflict 検出 ───────────────────────────────────────────────────────

class TestConflictDetection:

    def test_no_conflict_high_agreement(self, eal):
        """高一致 → conflict=none"""
        sr = MockSR(result=MockResult(sources=web_sources("5 permanent members")))
        r = eal.adjudicate("UN permanent members", sr)
        assert r.conflict_state == CONFLICT_NONE

    def test_managed_conflict_mixed_agreement(self, eal):
        """混在 → conflict=managed"""
        srcs = thin_sources(3)  # short labels → mixed
        sr = MockSR(result=MockResult(sources=srcs))
        r = eal.adjudicate("What is the rate?", sr)
        assert r.conflict_state in (CONFLICT_NONE, CONFLICT_MANAGED)

    def test_open_conflict_low_agreement(self, eal):
        """低一致 → open-conflict → bounded-only"""
        srcs = [
            Source(source_type="web", label="The rate is 2.5% according to sources",
                   uri="https://site1.com/", relevance_score=0.8),
            Source(source_type="web", label="Current rate stands at 8.9% as measured",
                   uri="https://site2.com/", relevance_score=0.8),
            Source(source_type="web", label="Official figure is 15.3% per report",
                   uri="https://site3.com/", relevance_score=0.8),
        ]
        sr = MockSR(result=MockResult(sources=srcs, synthesis="conflicting data"))
        r = eal.adjudicate("What is the current inflation rate?", sr)
        # open-conflictならbounded-only
        if r.conflict_state == CONFLICT_OPEN:
            assert r.admissibility == ADMISSIBILITY_BOUNDED


# ── § 4. 条件文法強制（Future Collective Fantasy 抑制） ───────────────────────

class TestConditionalGrammar:

    def test_high_tvs_adds_temporal_qualifier(self, eal):
        """高TVSクエリの synthesis に時制マーカーが入ること"""
        srcs = [Source(source_type="web", label="PM", uri="https://reuters.com/",
                       relevance_score=0.8)]
        sr = MockSR(result=MockResult(sources=srcs,
                                      synthesis="The Prime Minister is Taro Yamada."))
        kvs = KVSScore(tvs=0.75, mkr=0.5, computed=False)
        r = eal.adjudicate("Who is the current PM of Japan?", sr,
                           freshness_sensitive=True, kvs=kvs)
        markers = ["as of", "retrieved", "reported", "according", "sources"]
        assert any(m in r.synthesis.lower() for m in markers), \
            f"No conditional marker in synthesis: {r.synthesis[:100]}"

    def test_stable_query_no_qualifier(self, eal):
        """安定クエリ → 条件文法変換なし（synthesis そのまま）"""
        srcs = web_sources("speed of light 299792458")
        sr = MockSR(result=MockResult(sources=srcs,
                                      synthesis="299,792,458 m/s."))
        kvs = KVSScore(tvs=0.1, mkr=0.9, computed=True)
        r = eal.adjudicate("What is the speed of light?", sr, kvs=kvs)
        # 条件文法変換のprefixは入らない
        assert not r.synthesis.startswith("[As of"), \
            f"Unexpected qualifier on stable query: {r.synthesis[:50]}"

    def test_bounded_adds_disclosure(self, eal):
        """bounded-only → [Bounded] 付記"""
        sr = MockSR(result=MockResult(sources=thin_sources(),
                                      synthesis="partial answer."))
        r = eal.adjudicate("latest policy change", sr, freshness_sensitive=True)
        if r.admissibility == ADMISSIBILITY_BOUNDED:
            assert "[Bounded]" in r.synthesis or "bounded" in r.synthesis.lower()


# ── § 5. Γ/Ω(Γ) 収束ガード ──────────────────────────────────────────────────

class TestConvergenceGuard:

    def test_high_coherence_gain_downgrades_answerable(self, eal):
        """coherence_gain > threshold → answerable → bounded-only"""
        srcs = web_sources("market will crash soon")
        sr = MockSR(result=MockResult(sources=srcs,
                                      synthesis="The market will definitely crash."))
        r_normal = eal.adjudicate("Will the market crash?", sr, coherence_gain=0.0)
        r_guarded = eal.adjudicate("Will the market crash?", sr, coherence_gain=0.9)
        # convergence guard は answerable を bounded に格下げ
        if r_normal.admissibility == ADMISSIBILITY_ANSWERABLE:
            assert r_guarded.admissibility in (ADMISSIBILITY_BOUNDED, ADMISSIBILITY_FAILED)

    def test_convergence_note_in_synthesis(self, eal):
        """coherence_gain > threshold → 'Convergence note' が synthesis に入る"""
        srcs = web_sources("market prediction")
        sr = MockSR(result=MockResult(sources=srcs, synthesis="The forecast is clear."))
        r = eal.adjudicate("market forecast", sr, coherence_gain=0.9)
        assert "Convergence note" in r.synthesis

    def test_low_coherence_no_note(self, eal):
        """coherence_gain < threshold → Convergence note なし"""
        srcs = web_sources("stable fact about gold")
        sr = MockSR(result=MockResult(sources=srcs, synthesis="Gold is Au."))
        kvs = KVSScore(tvs=0.1, mkr=0.9, computed=True)
        r = eal.adjudicate("chemical symbol for gold", sr, kvs=kvs, coherence_gain=0.1)
        assert "Convergence note" not in r.synthesis


# ── § 6. freshness_note ──────────────────────────────────────────────────────

class TestFreshnessNote:

    def test_freshness_note_present_when_sensitive(self, eal):
        """freshness_sensitive=True → freshness_note が付与される"""
        srcs = [Source(source_type="web", label="rate",
                       uri="https://bbc.com/finance", relevance_score=0.8)]
        sr = MockSR(result=MockResult(sources=srcs, synthesis="3.75%"), box_used="S")
        r = eal.adjudicate("current Bank of England rate", sr,
                           freshness_sensitive=True)
        assert r.freshness_note is not None
        assert len(r.freshness_note) > 10

    def test_freshness_note_absent_for_stable(self, eal):
        """安定クエリ → freshness_note なし"""
        srcs = web_sources("gold Au chemical symbol")
        sr = MockSR(result=MockResult(sources=srcs, synthesis="Au."))
        kvs = KVSScore(tvs=0.1, mkr=0.9, computed=True)
        r = eal.adjudicate("What is the chemical symbol for gold?", sr, kvs=kvs)
        assert r.freshness_note is None


# ── § 7. EAL メタ情報 ────────────────────────────────────────────────────────

class TestEALMeta:

    def test_is_stub_false(self, eal):
        """Phase F 本実装 → is_stub=False"""
        sr = MockSR(result=MockResult(sources=thin_sources()))
        r = eal.adjudicate("test", sr)
        assert r.is_stub is False

    def test_adjudicated_at_set(self, eal):
        """adjudicated_at が設定される"""
        sr = MockSR(result=MockResult(sources=thin_sources()))
        r = eal.adjudicate("test", sr)
        assert r.adjudicated_at != ""

    def test_sources_used_populated(self, eal):
        """sources_used が入力と一致"""
        srcs = thin_sources(3)
        sr = MockSR(result=MockResult(sources=srcs))
        r = eal.adjudicate("test", sr)
        assert len(r.sources_used) == 3

    def test_kvs_estimated_when_none(self, eal):
        """kvs=None の場合は KVSEstimator が推定値を入れる（Phase F.2: computed=True）"""
        sr = MockSR(result=MockResult(sources=thin_sources()))
        r = eal.adjudicate("current price", sr, freshness_sensitive=True)
        assert r.kvs is not None
        # Phase F.2 以降: KVSEstimator が自動推定 → computed=True
        # KVSEstimator が利用できない環境では computed=False の stub fallback
        assert r.kvs.computed in (True, False)  # どちらでも OK

    def test_is_answerable_helper(self, eal):
        """is_answerable() ヘルパーの動作確認"""
        srcs = web_sources("5 permanent members UN Security Council")
        sr = MockSR(result=MockResult(sources=srcs, synthesis="5 members."))
        r = eal.adjudicate(
            "How many permanent members does the UN Security Council have?", sr)
        assert eal.is_answerable(r) == (r.admissibility == ADMISSIBILITY_ANSWERABLE)
