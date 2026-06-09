"""
dynamic_kvs.py — Dynamic KVS Guard for Mobius v7.5 Phase B.1-B.4

Phase B.4 addition: integrated RGC (Reflective Gradient Control) phi_t control law.

Changes (Phase B.4):
  - Import RGCController / RGCState
  - Added rgc_state argument to compute_dynamic_kvs() (optional)
  - Added rgc field to DynamicKVSResult
  - VREGEN_ENABLED=True enables all phases

Existing API from Phase B.1 is fully preserved.
"""
from __future__ import annotations

# ── Feature flags ─────────────────────────────────────────────────────────────
VREGEN_ENABLED: bool = True    # Phase B.1  (False = Phase A routing only)
RGC_ENABLED:    bool = True    # Phase B.4  (False = no phi_t update)

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from .kvs import KVSResult, MKR_THRESHOLD, TVS_THRESHOLD, compute_kvs
from .vregen import VRegenResult, compute_vregen, should_trigger_vregen, vregen_skipped
from .cconflict import CConflictResult, compute_cconflict, should_trigger_cconflict, cconflict_skipped
from .hpred import HPredResult, compute_hpred, should_trigger_hpred, hpred_skipped
from .rgc import RGCController, RGCState, RGCResult, PI_MAX

if TYPE_CHECKING:
    from ..adapters.ollama_adapter import OllamaAdapter

# ── Module-level RGC controller (stateless, shared) ───────────────────────────
_RGC_CTRL = RGCController()


@dataclass
class DynamicKVSResult:
    """
    Full Phase B KVS result.
    Extends Phase A KVSResult with dynamic Pi signals + Phase B.4 RGC.
    """
    # Phase A base
    phase_a:            KVSResult

    # Phase B signals
    vregen:             VRegenResult
    cconflict:          CConflictResult
    hpred:              HPredResult

    # Derived dynamic values
    pi_total:           float           # Total penalty from Phase B signals
    mkr_eff_dynamic:    float           # MKR_eff after Pi
    low_stakes_eligible_dynamic: bool   # Final eligibility after Pi

    # Phase B.4: RGC
    rgc:                Optional[RGCResult] = None  # None if RGC_ENABLED=False

    # Reason codes (Phase A + Phase B + Phase B.4)
    all_reason_codes:   list = field(default_factory=list)

    # ── Phase A pass-through properties ──────────────────────────────────────
    @property
    def tvs(self) -> float:
        return self.phase_a.tvs

    @property
    def mkr_base(self) -> float:
        return self.phase_a.mkr_base

    @property
    def mkr_eff_phase_a(self) -> float:
        return self.phase_a.mkr_eff

    @property
    def model_class(self) -> str:
        return self.phase_a.model_class

    @property
    def domain(self) -> str:
        return self.phase_a.domain

    # ── Phase B.4 convenience ────────────────────────────────────────────────
    @property
    def phi(self) -> Optional[float]:
        """Current phi_t after this query. None if RGC disabled."""
        return self.rgc.phi_next if self.rgc else None

    @property
    def rgc_band(self) -> Optional[str]:
        return self.rgc.band if self.rgc else None

    def trace_dict(self) -> dict:
        """Serializable trace record for audit log."""
        d = {
            "tvs":                      self.phase_a.tvs,
            "mkr_eff_phase_a":          self.phase_a.mkr_eff,
            "vregen_triggered":         self.vregen.triggered,
            "vregen_stable":            getattr(self.vregen, "stable", None),
            "vregen_penalty":           self.vregen.penalty,
            "cconflict_triggered":      self.cconflict.triggered,
            "cconflict_consistent":     getattr(self.cconflict, "consistent", None),
            "cconflict_penalty":        self.cconflict.penalty,
            "hpred_triggered":          self.hpred.triggered,
            "hpred_available":          getattr(self.hpred, "available", None),
            "hpred_h_score":            getattr(self.hpred, "h_score", None),
            "hpred_penalty":            self.hpred.penalty,
            "pi_total":                 self.pi_total,
            "mkr_eff_dynamic":          self.mkr_eff_dynamic,
            "low_stakes_eligible":      self.low_stakes_eligible_dynamic,
            "reason_codes":             self.all_reason_codes,
        }
        if self.rgc:
            d.update({
                "phi_prev":   self.rgc.phi_prev,
                "phi_next":   self.rgc.phi_next,
                "rgc_band":   self.rgc.band,
                "rgc_reason": self.rgc.reason_code,
                "rgc_I_t":    self.rgc.I_t,
                "rgc_P_t":    self.rgc.P_t,
            })
        return d


def compute_dynamic_kvs(
    query:           str,
    model_name:      str,
    original_answer: Optional[str]       = None,
    adapter:         Optional["OllamaAdapter"] = None,
    rgc_state:       Optional[RGCState]  = None,
) -> DynamicKVSResult:
    """
    Compute Dynamic KVS (Phase B.1–B.4).

    Args:
        query:           User query string
        model_name:      Ollama model name (e.g. "phi4-mini:latest")
        original_answer: Pre-generated answer string (None at appraisal time)
        adapter:         OllamaAdapter instance (None → signals skipped)
        rgc_state:       Per-session RGCState. If None and RGC_ENABLED,
                         a fresh state is created (stateless mode).

    Flow:
        1. Phase A: static KVS
        2. Phase B.1: V_regen  (if in trigger band and answer available)
        3. Phase B.2: C_conflict (if V_regen ran and was STABLE)
        4. Phase B.3: H_pred   (if in trigger band)
        5. Pi, MKR_eff_dynamic, eligibility
        6. Phase B.4: RGC phi_t update
    """
    # ── Step 1: Phase A ───────────────────────────────────────────────────────
    phase_a = compute_kvs(query, model_name)
    r_fresh = getattr(phase_a, 'r_fresh', 0.0)

    # ── Step 2: V_regen ───────────────────────────────────────────────────────
    if original_answer is None or adapter is None:
        vr = vregen_skipped("no_answer_yet")
    elif not phase_a.low_stakes_eligible:
        vr = vregen_skipped("phase_a_already_blocked")
    elif not should_trigger_vregen(phase_a.mkr_eff):
        vr = vregen_skipped(
            "mkr_eff_above_upper" if phase_a.mkr_eff >= 0.65
            else "mkr_eff_below_lower"
        )
    elif not VREGEN_ENABLED:
        vr = vregen_skipped("vregen_disabled_by_feature_flag")
    else:
        vr = compute_vregen(
            query=query,
            original_answer=original_answer,
            adapter=adapter,
        )

    # ── Step 3: C_conflict ────────────────────────────────────────────────────
    # Only run when V_regen was triggered AND stable
    vregen_was_stable = vr.triggered and getattr(vr, "stable", False)
    if (VREGEN_ENABLED and vregen_was_stable
            and original_answer is not None and adapter is not None
            and should_trigger_cconflict(phase_a.mkr_eff, True)):
        cc = compute_cconflict(query, original_answer, adapter)
    else:
        reason = "vregen_not_stable_or_disabled" if VREGEN_ENABLED else "vregen_disabled"
        cc = cconflict_skipped(reason)

    # ── Step 4: H_pred ────────────────────────────────────────────────────────
    if VREGEN_ENABLED and should_trigger_hpred(phase_a.mkr_eff):
        if adapter is not None:
            hp = compute_hpred(query, adapter)
        else:
            hp = hpred_skipped("no_adapter")
    else:
        hp = hpred_skipped("trigger_condition_not_met")

    # ── Step 5: Pi, MKR_eff_dynamic, eligibility ─────────────────────────────
    pi_total = round(vr.penalty + cc.penalty + hp.penalty, 3)
    mkr_eff_dynamic = round(max(0.0, min(1.0, phase_a.mkr_eff - pi_total)), 3)
    eligible_dynamic = (
        phase_a.tvs < TVS_THRESHOLD
        and mkr_eff_dynamic >= MKR_THRESHOLD
    )

    # ── Step 6: RGC (Phase B.4) ───────────────────────────────────────────────
    rgc_result: Optional[RGCResult] = None
    if RGC_ENABLED:
        _state = rgc_state if rgc_state is not None else RGCState()
        rgc_result = _RGC_CTRL.step(
            _state,
            pi=pi_total,
            r_fresh=r_fresh,
        )
        # RGC band refines eligibility: even if MKR says answer,
        # elevated phi_t may pull back to self-check.
        # LOW_STAKES_STABLE requires both MKR gate AND phi in answer band.
        if eligible_dynamic and rgc_result.band != "answer":
            eligible_dynamic = False

    # ── Step 7: Reason codes ──────────────────────────────────────────────────
    codes = list(phase_a.reason_codes)

    if vr.triggered:
        codes.append("VREGEN_STABLE" if getattr(vr, "stable", False)
                      else "VREGEN_UNSTABLE")
        if not getattr(vr, "stable", True):
            codes.append("KVS_DYNAMIC_DOWNREV")
    else:
        codes.append(f"VREGEN_SKIPPED:{vr.reason.split(':')[0]}")

    if cc.triggered:
        codes.append("CCONFLICT_CONSISTENT" if getattr(cc, "consistent", True)
                      else "CCONFLICT_CONFLICT")
        if not getattr(cc, "consistent", True):
            codes.append("KVS_DYNAMIC_DOWNREV")

    if hp.triggered:
        if not getattr(hp, "available", True):
            codes.append("HPRED_UNAVAILABLE")
        elif hp.penalty > 0:
            codes.append("HPRED_HIGH_ENTROPY")
            codes.append("KVS_DYNAMIC_DOWNREV")
        else:
            codes.append("HPRED_LOW_ENTROPY")

    if phase_a.low_stakes_eligible and not eligible_dynamic:
        if pi_total > 0:
            codes.append("KVS_PHASEB_BLOCKED")
        elif rgc_result and rgc_result.band != "answer":
            codes.append("KVS_RGC_BLOCKED")

    if rgc_result:
        codes.append(rgc_result.reason_code)

    return DynamicKVSResult(
        phase_a=phase_a,
        vregen=vr,
        cconflict=cc,
        hpred=hp,
        pi_total=pi_total,
        mkr_eff_dynamic=mkr_eff_dynamic,
        low_stakes_eligible_dynamic=eligible_dynamic,
        rgc=rgc_result,
        all_reason_codes=codes,
    )
