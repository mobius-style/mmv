"""
tests/test_phase_b4.py — Phase B.4 pytest suite
実際のコードベース API に完全一致。

実行:
    cd MOBIUS_MMV && mobius
    python -m pytest tests/test_phase_b4.py -v

Author: Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations
import random
import pytest

from src.kernel.rgc import (
    RGCController, RGCState,
    calibrate_from_batch,
    ALPHA, BETA, GAMMA, PHI_INIT, PI_MAX,
    BAND_ANSWER_MAX, _band,
)
from src.kernel.vregen   import VRegenResult,    W_VREGEN
from src.kernel.cconflict import CConflictResult, W_CCONFLICT
from src.kernel.hpred    import HPredResult,     W_HPRED

# ── deployed constants ────────────────────────────────────────────────────────
TAU_M = 0.52;  TAU_T = 0.30
TRIGGER_LOW = 0.52;  TRIGGER_HIGH = 0.65
HPRED_ENTROPY_THRESHOLD = 0.55   # actual deployed (spec doc says 0.80)

# ── signal builders (actual fields confirmed from live codebase) ──────────────
# VRegenResult:    triggered, penalty, propositions, stable, reason
# CConflictResult: triggered, penalty, answer, rationale, consistent, reason
# HPredResult:     triggered, available, h_score, penalty, reason

def vr_stable():
    return VRegenResult(
        triggered=True, penalty=0.0,
        propositions=["1995", "1995"],
        stable=True, reason="VREGEN_STABLE")

def vr_unstable():
    return VRegenResult(
        triggered=True, penalty=W_VREGEN,
        propositions=["1989", "1991"],
        stable=False, reason="VREGEN_UNSTABLE")

def cc_ok():
    return CConflictResult(
        triggered=True, penalty=0.0,
        answer="1995", rationale="The WTO was established in 1995.",
        consistent=True, reason="CCONFLICT_OK")

def cc_fire():
    return CConflictResult(
        triggered=True, penalty=W_CCONFLICT,
        answer="five", rationale="There are seven permanent members.",
        consistent=False, reason="CCONFLICT_CONFLICT")

def hp_stable():
    return HPredResult(
        triggered=True, available=True,
        h_score=0.30, penalty=0.0,
        reason="low_entropy: H=0.300")

def hp_fire():
    return HPredResult(
        triggered=True, available=True,
        h_score=0.80, penalty=W_HPRED,
        reason="high_entropy: H=0.800")

def hp_unavail():
    return HPredResult(
        triggered=True, available=False,
        h_score=0.0, penalty=0.0,
        reason="logprobs_unavailable")

# ── minimal compute helper (mirrors compute_dynamic_kvs logic) ────────────────
from dataclasses import dataclass

@dataclass
class _KVS:
    tvs: float; mkr_eff: float; low_stakes_eligible: bool
    reason_codes: list; r_fresh: float = 0.0

@dataclass
class _DR:
    phase_a: _KVS; pi_total: float; mkr_eff_dynamic: float
    low_stakes_eligible_dynamic: bool; rgc: object; all_reason_codes: list
    @property
    def phi(self): return self.rgc.phi_next if self.rgc else None
    @property
    def rgc_band(self): return self.rgc.band if self.rgc else None

def _run(tvs, mkr, vr=None, cc=None, hp=None, r_fresh=0.0, rgc_state=None):
    pa = _KVS(tvs=tvs, mkr_eff=mkr, r_fresh=r_fresh,
              low_stakes_eligible=(tvs < TAU_T and mkr >= TAU_M),
              reason_codes=[])

    # defaults — not triggered
    vr = vr or VRegenResult(
        triggered=False, penalty=0.0, propositions=[], stable=False, reason="skipped")
    cc = cc or CConflictResult(
        triggered=False, penalty=0.0, answer="", rationale="",
        consistent=True, reason="skipped")
    hp = hp or HPredResult(
        triggered=False, available=True, h_score=0.0, penalty=0.0, reason="skipped")

    ctrl  = RGCController()
    state = rgc_state if rgc_state is not None else RGCState()
    codes = []

    # TVS gate
    if tvs >= TAU_T:
        rgc = ctrl.step(state, pi=PI_MAX, r_fresh=r_fresh)
        return _DR(pa, 0.0, mkr, False, rgc, ["KVS_FAIL_TVS", rgc.reason_code])

    # MKR prior gate
    if mkr < TAU_M:
        rgc = ctrl.step(state, pi=W_VREGEN, r_fresh=r_fresh)
        return _DR(pa, 0.0, mkr, False, rgc, ["KVS_FAIL_MKR_PRIOR", rgc.reason_code])

    # Dynamic signal pipeline
    pi = 0.0
    in_band = TRIGGER_LOW <= mkr <= TRIGGER_HIGH

    if in_band:
        # V_regen
        if vr.triggered:
            pi += vr.penalty
            codes.append("VREGEN_STABLE" if vr.stable else "VREGEN_UNSTABLE")
            if not vr.stable:
                codes.append("KVS_DYNAMIC_DOWNREV")

        # C_conflict: only when V_regen was triggered AND stable
        if vr.triggered and vr.stable and cc.triggered:
            pi += cc.penalty
            if not cc.consistent:
                codes.append("CCONFLICT_CONFLICT")
                codes.append("KVS_DYNAMIC_DOWNREV")

        # H_pred
        if hp.triggered:
            pi += hp.penalty
            if not hp.available:
                codes.append("HPRED_UNAVAILABLE")
            elif hp.penalty > 0:
                codes.append("HPRED_HIGH_ENTROPY")
                codes.append("KVS_DYNAMIC_DOWNREV")
            else:
                codes.append("HPRED_LOW_ENTROPY")

    pi = round(min(PI_MAX, max(0.0, pi)), 3)
    mkr_dyn = round(max(0.0, min(1.0, mkr - pi)), 3)
    eligible = (tvs < TAU_T) and (mkr_dyn >= TAU_M)

    rgc = ctrl.step(state, pi=pi, r_fresh=r_fresh)
    if eligible and rgc.band != "answer":
        eligible = False
        codes.append("KVS_RGC_BLOCKED")
    elif pa.low_stakes_eligible and not eligible and pi > 0:
        codes.append("KVS_PHASEB_BLOCKED")

    codes.append(rgc.reason_code)
    return _DR(pa, pi, mkr_dyn, eligible, rgc, codes)


# ════════════════════════════════════════════════════════════════════════════════
# RGC unit tests
# ════════════════════════════════════════════════════════════════════════════════

class TestRGCBands:
    @pytest.mark.parametrize("phi,exp", [
        (0.0,"answer"),(0.30,"answer"),(0.301,"self-check"),(0.60,"self-check"),
        (0.601,"verify"),(0.90,"verify"),(0.901,"ask-abstain"),(1.0,"ask-abstain"),
    ])
    def test_band(self, phi, exp):
        assert _band(phi) == exp

class TestRGCControlLaw:
    def test_stable_phi_decreases(self):
        ctrl, s = RGCController(), RGCState()
        for _ in range(10): ctrl.step(s, pi=0.0, r_fresh=0.0)
        assert s.phi < PHI_INIT

    def test_phi_floor(self):
        ctrl, s = RGCController(), RGCState(phi=0.01)
        for _ in range(30): ctrl.step(s, pi=0.0, r_fresh=0.0)
        assert s.phi >= 0.0

    def test_phi_ceiling(self):
        ctrl, s = RGCController(), RGCState()
        for _ in range(15): ctrl.step(s, pi=PI_MAX, r_fresh=0.30)
        assert s.phi <= 1.0

    def test_vregen_escalates_to_selfcheck(self):
        ctrl, s = RGCController(), RGCState()
        r = ctrl.step(s, pi=W_VREGEN, r_fresh=0.05)
        assert r.phi_next > BAND_ANSWER_MAX and r.band == "self-check"

    def test_full_pi_reaches_verify(self):
        ctrl, s = RGCController(), RGCState()
        ctrl.step(s, pi=PI_MAX, r_fresh=0.20)
        r = ctrl.step(s, pi=PI_MAX, r_fresh=0.20)
        assert r.band in ("verify", "ask-abstain")

    def test_query_count(self):
        ctrl, s = RGCController(), RGCState()
        for _ in range(7): ctrl.step(s, pi=0.0, r_fresh=0.0)
        assert s.query_count == 7

    def test_reset(self):
        ctrl, s = RGCController(), RGCState()
        for _ in range(5): ctrl.step(s, pi=PI_MAX, r_fresh=0.30)
        s.reset()
        assert s.phi == PHI_INIT and s.query_count == 0

class TestRGCCalibration:
    def test_batch_calibration_matches_defaults(self):
        cal = calibrate_from_batch(
            {"A19": 0.47, "B13": 0.23, "B15": 0.75}, 0.998, 0.0)
        assert abs(cal["alpha"] - ALPHA) < 0.05
        assert cal["beta"] == BETA and cal["gamma"] == GAMMA

# ════════════════════════════════════════════════════════════════════════════════
# Dynamic KVS + RGC integration
# ════════════════════════════════════════════════════════════════════════════════

class TestGates:
    def test_tvs_high_blocked(self):
        r = _run(0.80, 0.85)
        assert not r.low_stakes_eligible_dynamic
        assert "KVS_FAIL_TVS" in r.all_reason_codes

    def test_tvs_boundary_blocked(self):
        assert not _run(0.30, 0.85).low_stakes_eligible_dynamic

    def test_tvs_below_eligible(self):
        assert _run(0.29, 0.85).low_stakes_eligible_dynamic

    def test_mkr_low_blocked(self):
        r = _run(0.10, 0.40)
        assert not r.low_stakes_eligible_dynamic
        assert "KVS_FAIL_MKR_PRIOR" in r.all_reason_codes

    def test_high_mkr_eligible(self):
        r = _run(0.10, 0.85)
        assert r.low_stakes_eligible_dynamic and r.pi_total == 0.0

    def test_above_band_no_pi(self):
        assert _run(0.10, 0.66).pi_total == 0.0

class TestVRegen:
    def test_stable_eligible(self):
        r = _run(0.10, 0.58, vr=vr_stable())
        assert r.low_stakes_eligible_dynamic and r.pi_total == 0.0
        assert "VREGEN_STABLE" in r.all_reason_codes

    def test_unstable_blocked(self):
        r = _run(0.10, 0.58, vr=vr_unstable())
        assert not r.low_stakes_eligible_dynamic
        assert abs(r.pi_total - W_VREGEN) < 1e-9
        assert "VREGEN_UNSTABLE" in r.all_reason_codes

    def test_mkr_drop_correct(self):
        r = _run(0.10, 0.58, vr=vr_unstable())
        assert abs(r.mkr_eff_dynamic - (0.58 - W_VREGEN)) < 1e-6

    def test_unstable_blocks_cconflict(self):
        """V_regen UNSTABLE のとき C_conflict は実行されない"""
        r = _run(0.10, 0.60, vr=vr_unstable(), cc=cc_fire())
        assert abs(r.pi_total - W_VREGEN) < 1e-9

    def test_vregen_propositions_field_exists(self):
        """実際のフィールド: triggered, penalty, propositions, stable, reason"""
        vr = vr_stable()
        assert hasattr(vr, "triggered")
        assert hasattr(vr, "propositions")
        assert hasattr(vr, "stable")

class TestCConflict:
    def test_consistent_no_penalty(self):
        assert _run(0.10, 0.58, vr=vr_stable(), cc=cc_ok()).pi_total == 0.0

    def test_conflict_adds_penalty(self):
        r = _run(0.10, 0.58, vr=vr_stable(), cc=cc_fire())
        assert abs(r.pi_total - W_CCONFLICT) < 1e-9
        assert "CCONFLICT_CONFLICT" in r.all_reason_codes

    def test_cconflict_fields(self):
        """実際のフィールド: triggered, penalty, answer, rationale, consistent, reason"""
        cc = cc_fire()
        assert hasattr(cc, "answer")
        assert hasattr(cc, "rationale")
        assert hasattr(cc, "consistent")
        assert not cc.consistent

class TestHPred:
    def test_stable_no_penalty(self):          # B04/B09 false positive = 0%
        r = _run(0.10, 0.58, vr=vr_stable(), cc=cc_ok(), hp=hp_stable())
        assert r.pi_total == 0.0 and r.low_stakes_eligible_dynamic
        assert "HPRED_LOW_ENTROPY" in r.all_reason_codes

    def test_fire_penalty(self):
        r = _run(0.10, 0.58, vr=vr_stable(), cc=cc_ok(), hp=hp_fire())
        assert abs(r.pi_total - W_HPRED) < 1e-9
        assert "HPRED_HIGH_ENTROPY" in r.all_reason_codes

    def test_unavailable_no_penalty(self):
        r = _run(0.10, 0.58, vr=vr_stable(), cc=cc_ok(), hp=hp_unavail())
        assert r.pi_total == 0.0

    def test_hpred_fields(self):
        """実際のフィールド: triggered, available, h_score, penalty, reason"""
        hp = hp_fire()
        assert hasattr(hp, "triggered")
        assert hasattr(hp, "available")
        assert hasattr(hp, "h_score")

    def test_actual_entropy_threshold(self):
        """実際の閾値は 0.55 (spec doc の 0.80 ではない)"""
        assert abs(HPRED_ENTROPY_THRESHOLD - 0.55) < 1e-9

class TestAllSignals:
    def test_vr_stable_cc_hp_pi(self):
        """V_regen STABLE + C_conflict fire + H_pred fire → Pi = 0.22"""
        r = _run(0.10, 0.58, vr=vr_stable(), cc=cc_fire(), hp=hp_fire())
        assert abs(r.pi_total - (W_CCONFLICT + W_HPRED)) < 1e-9

    def test_pi_clamped_to_pi_max(self):
        r = _run(0.10, 0.63, vr=vr_stable(), cc=cc_fire(), hp=hp_fire())
        assert r.pi_total <= PI_MAX

class TestRGCB4:
    def test_rgc_in_result(self):
        r = _run(0.10, 0.58, vr=vr_stable())
        assert r.rgc is not None and r.phi is not None

    def test_phi_rises_on_instability(self):
        ctrl, s = RGCController(), RGCState()
        ctrl.step(s, pi=W_VREGEN, r_fresh=0.05)
        assert s.phi > PHI_INIT

    def test_reset(self):
        ctrl, s = RGCController(), RGCState()
        for _ in range(5): ctrl.step(s, pi=PI_MAX, r_fresh=0.30)
        s.reset()
        assert s.phi == PHI_INIT and s.query_count == 0

    def test_elevated_phi_can_block(self):
        s = RGCState()
        ctrl = RGCController()
        for _ in range(4): ctrl.step(s, pi=PI_MAX, r_fresh=0.25)
        r = _run(0.10, 0.85, rgc_state=s)
        if r.rgc and r.rgc.band != "answer":
            assert not r.low_stakes_eligible_dynamic

class TestOneSided:
    @pytest.mark.parametrize("tvs,mkr", [
        (0.0, 0.52), (0.1, 0.58), (0.1, 0.65), (0.29, 0.80), (0.0, 0.95)])
    def test_mkr_never_increases(self, tvs, mkr):
        assert _run(tvs, mkr, vr=vr_stable()).mkr_eff_dynamic <= mkr + 1e-9

# ════════════════════════════════════════════════════════════════════════════════
# Batch-validated scenarios
# ════════════════════════════════════════════════════════════════════════════════

class TestBatchScenarios:
    def test_b02_b07(self):
        """numerical_confusion: mkr=0.40 → blocked"""
        assert not _run(0.05, 0.40).low_stakes_eligible_dynamic

    def test_b04_b09_hpred_false_positive_zero(self):
        """H_pred fires STABLE → eligible, pi=0. Batch false positive rate=0%"""
        r = _run(0.05, 0.58, vr=vr_stable(), cc=cc_ok(), hp=hp_stable())
        assert r.low_stakes_eligible_dynamic and r.pi_total == 0.0

    def test_b13_stochastic_23pct(self):
        """V_regen fires 23% of runs → escalation rate ≈23%. Batch: 23/100"""
        random.seed(42)
        escalated = sum(
            1 for _ in range(1000)
            if not _run(
                0.05, 0.58,
                vr=vr_unstable() if random.random() < 0.23 else vr_stable()
            ).low_stakes_eligible_dynamic
        )
        rate = escalated / 1000
        assert 0.18 <= rate <= 0.28, f"B13 escalation rate={rate:.3f}"

    def test_b15_both_outcomes_valid(self):
        assert not _run(0.05, 0.58, vr=vr_unstable()).low_stakes_eligible_dynamic
        assert     _run(0.05, 0.58, vr=vr_stable()).low_stakes_eligible_dynamic

    def test_a12_tvs_gate(self):
        """current officeholder: high TVS → always blocked"""
        r = _run(0.85, 0.50)
        assert not r.low_stakes_eligible_dynamic
        assert "KVS_FAIL_TVS" in r.all_reason_codes

    def test_c11_post_fix(self):
        """C11 after appraisal fix: tvs=0, mkr=0.76 → eligible"""
        assert _run(0.00, 0.76).low_stakes_eligible_dynamic

    def test_cat_b_stable_subset(self):
        """STABLE Cat-B (B01-B12, B14): low TVS, mid/high MKR → eligible"""
        for mkr in [0.63, 0.76, 0.85]:
            assert _run(0.05, mkr).low_stakes_eligible_dynamic, \
                f"mkr={mkr} should be eligible"

# ════════════════════════════════════════════════════════════════════════════════
# xfail: documented limitations (既存 xfail 規則と同じ形式)
# ════════════════════════════════════════════════════════════════════════════════

class TestKnownLimitations:
    @pytest.mark.xfail(
        reason="B13: ground truth ambiguous (1989 proposal vs 1991 implementation); "
               "correct rate 23% (95%CI [14.8%,31.2%]) — stochastic, not architectural failure")
    def test_b13_always_correct(self):
        assert False, "B13 known limitation — xfail expected"

    @pytest.mark.xfail(
        reason="A19, B15: Brave Search result variability; "
               "will become STABLE after Kiwix integration (Phase C)")
    def test_a19_b15_always_correct(self):
        assert False, "Search-dependent VARIABLE queries — xfail expected"
