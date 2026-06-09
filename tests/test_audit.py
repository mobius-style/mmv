#!/usr/bin/env python3
"""
test_audit.py — MOBIUS MMV Phase D: Audit モジュール テストスイート
tests/test_audit.py

成功基準 (phase_d_audit_spec.docx §11):
  - Minimum Header が毎ターン生成されること（sampling対象外）
  - Full Turn Audit Record が risk_boost=True 時は 100% 生成されること
  - audit_store の追記レイテンシ < 5ms
  - JSONL の各レコードが独立してパース可能なこと
  - Session Trace Summary がセッション終端で正確に1件生成されること
  - 既存テスト 170 passed, 2 xfailed 維持

実行:
    cd ~/デスクトップ/mobius_ai/MOBIUS_MMV
    cp ~/ダウンロード/test_audit.py tests/test_audit.py
    python -m pytest tests/test_audit.py -v

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""

from __future__ import annotations

import json
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "audit"))

from audit_emitter import AuditEmitter
from audit_sampler import AuditSampler, RATE_COLD_START, RATE_WARM, RATE_STEADY
from audit_schema import (
    AUDIT_MODE_FULL, AUDIT_MODE_OFF, AUDIT_MODE_SHADOW,
    AUDIT_MODE_INCIDENT_ONLY,
    POLICY_VERSION, RECORD_TYPE_HEADER, RECORD_TYPE_TURN_FULL,
    DecisionTrace, FullTurnAuditRecord, IncidentRecord,
    KVSScoreRecord, QKSnapshot, SessionTraceSummary,
)
from audit_store import AuditStore, TURNS_FILE, SESSIONS_FILE, INCIDENTS_FILE


# ═══════════════════════════════════════════════════════════════════════════════
# フィクスチャ
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def tmp_log_dir(tmp_path):
    return tmp_path


@pytest.fixture()
def store(tmp_log_dir):
    s = AuditStore(tmp_log_dir)
    s.open()
    yield s
    s.close()


@pytest.fixture()
def full_emitter(tmp_log_dir):
    """audit_mode=full（全ターン記録）のエミッター"""
    s   = AuditStore(tmp_log_dir)
    smp = AuditSampler(audit_mode=AUDIT_MODE_FULL, seed=42)
    e   = AuditEmitter(store=s, sampler=smp, audit_mode=AUDIT_MODE_FULL)
    e.open()
    e.start_session("sess-001")
    yield e, tmp_log_dir
    e.close()


@pytest.fixture()
def shadow_emitter(tmp_log_dir):
    """audit_mode=shadow（サンプリング）のエミッター"""
    s   = AuditStore(tmp_log_dir)
    smp = AuditSampler(audit_mode=AUDIT_MODE_SHADOW, seed=0)
    e   = AuditEmitter(store=s, sampler=smp, audit_mode=AUDIT_MODE_SHADOW)
    e.open()
    e.start_session("sess-002")
    yield e, tmp_log_dir
    e.close()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    return [json.loads(l) for l in lines if l.strip()]


# ═══════════════════════════════════════════════════════════════════════════════
# § 1. QKSnapshot テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestQKSnapshot:

    def test_high_intent(self):
        qk = QKSnapshot.from_appraisal(0.9, 0.5, False, False)
        assert qk.intent == "high"

    def test_low_intent(self):
        qk = QKSnapshot.from_appraisal(0.2, 0.5, False, False)
        assert qk.intent == "low"

    def test_ok_intent(self):
        qk = QKSnapshot.from_appraisal(0.55, 0.5, False, False)
        assert qk.intent == "ok"

    def test_freshness_sets_risk_high(self):
        """freshness_sensitive=True → risk=high（spec §4.2）"""
        qk = QKSnapshot.from_appraisal(0.9, 0.1, True, False)
        assert qk.risk == "high"

    def test_safety_sets_meta_frame_high(self):
        qk = QKSnapshot.from_appraisal(0.9, 0.5, False, True)
        assert qk.meta_frame == "high"

    def test_uncertainty_inversion(self):
        """uncertainty ≥ 0.70 → risk=low（反転）"""
        qk = QKSnapshot.from_appraisal(0.9, 0.8, False, False)
        assert qk.risk == "low"

    def test_uncertainty_high(self):
        """uncertainty < 0.30 → risk=high"""
        qk = QKSnapshot.from_appraisal(0.9, 0.1, False, False)
        assert qk.risk == "high"


# ═══════════════════════════════════════════════════════════════════════════════
# § 2. FullTurnAuditRecord テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullTurnAuditRecord:

    def test_hash_text(self):
        h = FullTurnAuditRecord.hash_text("hello")
        assert len(h) == 64   # SHA-256 = 64 hex chars
        assert h != "hello"

    def test_hash_deterministic(self):
        assert FullTurnAuditRecord.hash_text("test") == \
               FullTurnAuditRecord.hash_text("test")

    def test_to_dict_has_required_fields(self):
        r = FullTurnAuditRecord(
            turn_id="tid", session_id="sid",
            turn=1, route_decision="answer"
        )
        d = r.to_dict()
        for key in ("turn_id", "session_id", "turn", "route_decision",
                    "audit_mode", "sampled", "record_type"):
            assert key in d, f"Missing: {key}"

    def test_policy_version_format(self):
        """policy_version は mmv-{semver}-{phase_tag} 形式"""
        assert POLICY_VERSION.startswith("mmv-v")
        parts = POLICY_VERSION.split("-")
        assert len(parts) >= 3

    def test_kvs_field_present(self):
        """Phase D 追加フィールド kvs が型定義に存在すること"""
        r = FullTurnAuditRecord(turn_id="t", session_id="s", turn=1,
                                route_decision="verify")
        r.kvs = KVSScoreRecord(tvs=0.8, mkr=0.5, computed=False)
        d = r.to_dict()
        assert "kvs" in d
        assert d["kvs"]["tvs"] == 0.8

    def test_eal_admissibility_field(self):
        """Phase D 追加フィールド eal_admissibility が存在すること"""
        r = FullTurnAuditRecord(turn_id="t", session_id="s", turn=1,
                                route_decision="verify",
                                eal_admissibility="answerable")
        assert r.eal_admissibility == "answerable"


# ═══════════════════════════════════════════════════════════════════════════════
# § 3. IncidentRecord テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestIncidentRecord:

    def test_routing_mismatch_triggers(self):
        assert IncidentRecord.should_emit("answer","abstain",[],0.3,0.3,False)

    def test_same_route_no_trigger(self):
        assert not IncidentRecord.should_emit("answer","answer",[],0.3,0.3,False)

    def test_safety_critical_triggers(self):
        assert IncidentRecord.should_emit(
            "answer","answer",["SAFETY_CRITICAL"],0.3,0.3,False
        )

    def test_exception_triggers(self):
        assert IncidentRecord.should_emit("answer","answer",[],0.3,0.3,True)

    def test_phi_t_high_with_abstain(self):
        assert IncidentRecord.should_emit("verify","abstain",[],0.95,0.3,False)

    def test_phi_t_high_consecutive(self):
        """phi_t > 0.90 が連続2ターン以上 → Incident"""
        assert IncidentRecord.should_emit("answer","answer",[],0.95,0.95,False)

    def test_phi_t_single_high_no_trigger(self):
        """phi_t > 0.90 が単発で route が answer → Incident なし"""
        assert not IncidentRecord.should_emit("answer","answer",[],0.95,0.3,False)


# ═══════════════════════════════════════════════════════════════════════════════
# § 4. AuditStore テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditStore:

    def test_write_sync_latency(self, store, tmp_log_dir):
        """追記レイテンシ < 5ms（spec §11）"""
        r = FullTurnAuditRecord(
            turn_id="t1", session_id="s1", turn=1, route_decision="answer"
        )
        ms = store.write_sync(r)
        assert ms < 5.0, f"latency={ms:.1f}ms ≥ 5ms"

    def test_jsonl_each_line_parseable(self, store, tmp_log_dir):
        """各レコードが独立してパース可能（spec §11）"""
        for i in range(3):
            r = FullTurnAuditRecord(
                turn_id=str(uuid.uuid4()), session_id="s1",
                turn=i, route_decision="answer"
            )
            store.write_sync(r)
        records = _read_jsonl(tmp_log_dir / TURNS_FILE)
        assert len(records) == 3
        for rec in records:
            assert isinstance(rec, dict)
            assert "turn_id" in rec

    def test_session_summary_to_sessions_file(self, store, tmp_log_dir):
        s = SessionTraceSummary(session_id="s99", turn_count=5)
        store.write_sync(s)
        records = _read_jsonl(tmp_log_dir / SESSIONS_FILE)
        assert len(records) == 1
        assert records[0]["session_id"] == "s99"

    def test_incident_to_incidents_file(self, store, tmp_log_dir):
        r = IncidentRecord(session_id="s1", turn=1,
                           expected_route="answer", actual_route="abstain",
                           failure_type="routing_mismatch")
        store.write_sync(r)
        records = _read_jsonl(tmp_log_dir / INCIDENTS_FILE)
        assert len(records) == 1
        assert records[0]["record_type"] == "incident"

    def test_stats_returns_dict(self, store):
        s = store.stats()
        assert isinstance(s, dict)
        assert "queue_depth" in s


# ═══════════════════════════════════════════════════════════════════════════════
# § 5. AuditSampler テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditSampler:

    def test_mode_off_never_records(self):
        smp = AuditSampler(audit_mode=AUDIT_MODE_OFF)
        smp.start_session("s")
        for _ in range(10):
            assert not smp.should_record("answer", False, [], 0.3)

    def test_mode_full_always_records(self):
        smp = AuditSampler(audit_mode=AUDIT_MODE_FULL)
        smp.start_session("s")
        for _ in range(10):
            assert smp.should_record("answer", False, [], 0.3)

    def test_mode_incident_only_never_records(self):
        smp = AuditSampler(audit_mode=AUDIT_MODE_INCIDENT_ONLY)
        smp.start_session("s")
        assert not smp.should_record("answer", False, [], 0.3)

    def test_risk_boost_clamped(self):
        """clamped=True → risk_boost → 必ず記録"""
        smp = AuditSampler(audit_mode=AUDIT_MODE_SHADOW, seed=0)
        smp.start_session("s")
        assert smp.should_record("answer", True, [], 0.3)

    def test_risk_boost_abstain(self):
        """route=abstain → risk_boost → 必ず記録"""
        smp = AuditSampler(audit_mode=AUDIT_MODE_SHADOW, seed=0)
        smp.start_session("s")
        assert smp.should_record("abstain", False, [], 0.3)

    def test_risk_boost_phi_t_high(self):
        """phi_t > 0.90 → risk_boost → 必ず記録"""
        smp = AuditSampler(audit_mode=AUDIT_MODE_SHADOW, seed=0)
        smp.start_session("s")
        assert smp.should_record("answer", False, [], 0.95)

    def test_cold_start_rate(self):
        """最初の3ターンは cold_start rate = 30%"""
        smp = AuditSampler(audit_mode=AUDIT_MODE_SHADOW, seed=0)
        smp.start_session("s")
        rate = smp._current_sample_rate()
        assert rate == RATE_COLD_START

    def test_warm_rate_after_cold_start(self):
        """4〜20ターンは warm rate = 10%"""
        smp = AuditSampler(audit_mode=AUDIT_MODE_SHADOW, seed=0)
        smp.start_session("s")
        for i in range(4):
            smp.update("answer", False, 0.3)
        assert smp._current_sample_rate() == RATE_WARM

    def test_steady_rate_long_session(self):
        """21ターン以上は steady rate = 5%"""
        smp = AuditSampler(audit_mode=AUDIT_MODE_SHADOW, seed=0)
        smp.start_session("s")
        for _ in range(21):
            smp.update("answer", False, 0.3)
        assert smp._current_sample_rate() == RATE_STEADY

    def test_incident_trigger_routing_mismatch(self):
        smp = AuditSampler(audit_mode=AUDIT_MODE_OFF)
        smp.start_session("s")
        assert smp.should_emit_incident("answer","abstain",[],0.3,False)

    def test_session_state_tracking(self):
        smp = AuditSampler(audit_mode=AUDIT_MODE_FULL)
        smp.start_session("s")
        smp.update("verify", False, 0.3)
        smp.update("ask",    True,  0.5)
        state = smp.current_session_state()
        assert state.turn_count   == 2
        assert state.verify_count == 1
        assert state.ask_count    == 1
        assert state.clamp_count  == 1


# ═══════════════════════════════════════════════════════════════════════════════
# § 6. AuditEmitter 統合テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditEmitter:

    def test_minimum_header_always_emitted(self, full_emitter):
        """Minimum Header は毎ターン必ず生成（sampling対象外）"""
        emitter, log_dir = full_emitter
        tid = emitter.emit_minimum_header("sess-001", 1, "verify")
        emitter._store.flush()
        records = _read_jsonl(log_dir / TURNS_FILE)
        headers = [r for r in records if r.get("record_type") == RECORD_TYPE_HEADER]
        assert len(headers) >= 1
        assert headers[0]["sampled"] is False

    def test_minimum_header_record_type(self, full_emitter):
        emitter, log_dir = full_emitter
        emitter.emit_minimum_header("sess-001", 1, "answer")
        emitter._store.flush()
        records = _read_jsonl(log_dir / TURNS_FILE)
        assert any(r["record_type"] == RECORD_TYPE_HEADER for r in records)

    def test_full_record_sampled_true(self, full_emitter):
        """Full Record は sampled=True"""
        emitter, log_dir = full_emitter
        tid = emitter.emit_turn_record(
            session_id="sess-001", turn=1, route_decision="verify",
            user_input="test", output_text="result", phi_t=0.3
        )
        assert tid is not None
        emitter._store.flush()
        records = _read_jsonl(log_dir / TURNS_FILE)
        full = [r for r in records if r.get("record_type") == RECORD_TYPE_TURN_FULL]
        assert len(full) >= 1
        assert full[0]["sampled"] is True

    def test_user_input_hashed(self, full_emitter):
        """生テキストは保存されずハッシュのみ（原則B）"""
        emitter, log_dir = full_emitter
        emitter.emit_turn_record(
            session_id="sess-001", turn=1, route_decision="answer",
            user_input="secret query", output_text="result", phi_t=0.3
        )
        emitter._store.flush()
        raw = (log_dir / TURNS_FILE).read_text()
        assert "secret query" not in raw
        assert "user_input_hash" in raw

    def test_kvs_recorded(self, full_emitter):
        """KVS フィールドが記録されること（Phase D）"""
        emitter, log_dir = full_emitter
        emitter.emit_turn_record(
            session_id="sess-001", turn=1, route_decision="verify",
            kvs=KVSScoreRecord(tvs=0.8, mkr=0.5, computed=False), phi_t=0.3
        )
        emitter._store.flush()
        records = _read_jsonl(log_dir / TURNS_FILE)
        full = [r for r in records if r.get("record_type") == RECORD_TYPE_TURN_FULL]
        assert full[0]["kvs"]["tvs"] == 0.8

    def test_session_summary_exactly_once(self, full_emitter):
        """Session Summary はセッション終端で正確に1件（spec §11）"""
        emitter, log_dir = full_emitter
        emitter.emit_turn_record(
            session_id="sess-001", turn=1, route_decision="answer", phi_t=0.3
        )
        emitter.emit_session_summary("sess-001", phi_t_final=0.3)
        emitter._store.flush()
        records = _read_jsonl(log_dir / SESSIONS_FILE)
        assert len(records) == 1
        assert records[0]["session_id"] == "sess-001"

    def test_session_summary_counts(self, full_emitter):
        """Session Summary の集計値が正確なこと"""
        emitter, log_dir = full_emitter
        emitter.emit_turn_record("sess-001",1,"verify",phi_t=0.3)
        emitter.emit_turn_record("sess-001",2,"ask",phi_t=0.3)
        emitter.emit_turn_record("sess-001",3,"answer",clamped=True,phi_t=0.3)
        summary = emitter.emit_session_summary("sess-001")
        assert summary.turn_count   == 3
        assert summary.verify_count == 1
        assert summary.ask_count    == 1
        assert summary.clamp_count  == 1

    def test_incident_emitted_to_incidents_file(self, full_emitter):
        emitter, log_dir = full_emitter
        emitter.emit_incident(
            session_id="sess-001", turn=1,
            expected_route="answer", actual_route="abstain",
            failure_type="routing_mismatch", phi_t=0.95
        )
        emitter._store.flush()
        records = _read_jsonl(log_dir / INCIDENTS_FILE)
        assert len(records) == 1
        assert records[0]["failure_type"] == "routing_mismatch"

    def test_mode_off_skips_turn_record(self, tmp_log_dir):
        """audit_mode=off では Full Record を生成しない"""
        s   = AuditStore(tmp_log_dir)
        smp = AuditSampler(audit_mode=AUDIT_MODE_OFF, seed=0)
        e   = AuditEmitter(store=s, sampler=smp, audit_mode=AUDIT_MODE_OFF)
        e.open()
        e.start_session("s")
        tid = e.emit_turn_record("s",1,"answer",phi_t=0.3)
        assert tid is None
        e.close()

    def test_jsonl_integrity(self, full_emitter):
        """各 JSONL レコードが独立してパース可能（spec §11）"""
        emitter, log_dir = full_emitter
        for i in range(5):
            emitter.emit_minimum_header("sess-001", i, "answer")
        emitter._store.flush()
        lines = (log_dir / TURNS_FILE).read_text().strip().split("\n")
        for line in lines:
            obj = json.loads(line)
            assert isinstance(obj, dict)

    def test_latency_fields_in_full_record(self, full_emitter):
        """latency_ms の4分解フィールドが存在すること（spec §4.1c）"""
        emitter, log_dir = full_emitter
        emitter.emit_turn_record(
            session_id="sess-001", turn=1, route_decision="answer",
            appraisal_ms=5, generation_ms=100, total_ms=110, phi_t=0.3
        )
        emitter._store.flush()
        records = _read_jsonl(log_dir / TURNS_FILE)
        full = [r for r in records if r.get("record_type") == RECORD_TYPE_TURN_FULL]
        lat = full[0]["latency_ms"]
        for key in ("appraisal_ms","generation_ms","audit_emit_ms","total_ms"):
            assert key in lat, f"Missing: {key}"
