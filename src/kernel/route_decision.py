"""
route_decision.py — Möbius v7.5 Phase A route decision

Rule priority:
  0. Safety → abstain
  1. Under-specified → ask
  2a. Stable structure + KVS PASS → answer (LOW_STAKES_STABLE, KVS-gated)
  2b. Stable structure + KVS FAIL → verify (KVS_STABLE_BLOCKED)
  3. Freshness-sensitive or high uncertainty → verify
  4. Default → answer
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Literal

from .appraisal import AppraisalState
from .reason_codes import ReasonCode

Route = Literal["answer", "ask", "verify", "abstain"]
AnswerShape = Literal["low_movement_answer", "admissible_reframing_answer"]


@dataclass
class RouteDecision:
    route:              Route
    reason_codes:       List[str] = field(default_factory=list)
    confidence_posture: str = "bounded"
    answer_shape:       Optional[AnswerShape] = None

    @property
    def reason_code(self) -> str:
        """Phase G.8 — convenience singular reason code.

        Returns the primary (first) reason code if any. UI/observability
        callers that want a single representative code should use this
        rather than silently dropping the list. Empty string when no
        reason codes have been recorded, which itself signals a routing
        path that did not emit any — usually a bug worth surfacing."""
        return self.reason_codes[0] if self.reason_codes else ""


def _apply_continuity_intent(appraisal: AppraisalState,
                              decision: RouteDecision) -> RouteDecision:
    """Phase G.9: when the appraisal flags `continuity_save_intent`,
    append an inspectable reason code to the decision. The actual save
    action happens in the UI post-response hook (trigger_manual_checkpoint);
    route taxonomy is NOT altered."""
    if getattr(appraisal, "continuity_save_intent", False):
        if ReasonCode.CONTINUITY_INTENT_DETECTED.value not in decision.reason_codes:
            decision.reason_codes.append(ReasonCode.CONTINUITY_INTENT_DETECTED.value)
    return decision


def _apply_casual_greeting_override(query: Optional[str],
                                     decision: RouteDecision) -> RouteDecision:
    """Stage B (cyc_20260424_stage_abc_trilingual_complete) — when the
    raw user query is a pure casual greeting (JA/EN/ZH), escape the
    under-specified ask gate and route to `answer` so the fast path in
    `_handle_answer` / `_prepare_answer_stream` can fire.

    Root cause: `_select_route_inner`'s Rule 1 fires on
    `completeness < 0.6`, which is true for "hello" / "你好" (1-2 word
    queries). The downstream casual_greeting fast path never runs
    because the engine dispatches an ask-route to
    `compose_non_answer_response("ask")` instead. This override bridges
    the appraisal-level under_specified signal to the routing-level
    fast-path eligibility, narrowly and reversibly.

    Conditions:
      - query provided (not None)
      - decision.route == "ask"
      - _is_casual_greeting(query) matches (length ≤ 20 AND no '?'/'？'
        AND strict per-language regex)

    This override is orthogonal to the continuity-save override; the
    casual-greeting helper's strict pattern / length / punctuation
    gates make it a non-overlapping predicate.
    """
    if query is None:
        return decision
    if decision.route != "ask":
        return decision
    try:
        # Late import to avoid a circular dependency (routing_engine
        # imports route_decision at module load).
        from .routing_engine import _is_casual_greeting
    except Exception:
        return decision
    if not _is_casual_greeting(query):
        return decision
    decision.route = "answer"
    if "CASUAL_GREETING_ROUTE_OVERRIDE_ASK" not in decision.reason_codes:
        decision.reason_codes.append("CASUAL_GREETING_ROUTE_OVERRIDE_ASK")
    return decision


def select_route(appraisal: AppraisalState,
                 *, query: Optional[str] = None) -> RouteDecision:
    """Route the appraisal to a downstream action.

    `query` is optional — when supplied, casual-greeting cases can
    override the under-specified ask gate. Existing callers that pass
    only `appraisal` are unaffected (backward compatible).
    """
    _decision = _select_route_inner(appraisal)
    _decision = _apply_continuity_intent(appraisal, _decision)
    _decision = _apply_casual_greeting_override(query, _decision)
    return _decision


def _select_route_inner(appraisal: AppraisalState) -> RouteDecision:
    # Rule 0: Safety — always abstain
    if appraisal.safety_relevant:
        return RouteDecision(
            route="abstain",
            reason_codes=[ReasonCode.SAFETY_ENVELOPE_TRIGGERED.value],
            confidence_posture="withhold",
        )

    # Rule 0.3: User correction — verify before accepting
    if getattr(appraisal, "user_correction", False):
        return RouteDecision(
            route="verify",
            reason_codes=["USER_CORRECTION", ReasonCode.EXTERNAL_DEPENDENCY.value],
            confidence_posture="recover-evidence",
        )

    # Rule 0.5: Self-referential — explain MOBIUS directly
    if getattr(appraisal, "self_referential", False):
        return RouteDecision(
            route="answer",
            reason_codes=["self_referential"],
            answer_shape="low_movement_answer",
        )

    # Rule 1: Under-specified — ask before doing anything
    if appraisal.completeness < 0.6 or appraisal.intent_clarity < 0.6:
        return RouteDecision(
            route="ask",
            reason_codes=[ReasonCode.MISSING_CONSTRAINTS.value],
            confidence_posture="clarify-first",
        )

    # Rule 2: Stable fact routing — KVS-gated (v7.5)
    # Only route to answer if BOTH structural stability AND KVS pass.
    # If structurally stable but KVS fails, route to verify (not answer).
    # This prevents the v3 failure mode (B02/B07).
    if appraisal.kvs is not None:
        kvs = appraisal.kvs
        is_structurally_stable = bool(
            "low-stakes-stable" in appraisal.notes
            or "stable-structure-kvs-blocked" in appraisal.notes
        )
        if is_structurally_stable:
            if kvs.low_stakes_eligible:
                # KVS PASS: answer directly (LOW_STAKES_STABLE)
                return RouteDecision(
                    route="answer",
                    reason_codes=[
                        ReasonCode.LOW_STAKES_STABLE.value,
                        ReasonCode.KVS_PASS_LOW_TVS_HIGH_MKR.value,
                        ReasonCode.SUFFICIENTLY_SPECIFIED.value,
                    ],
                    confidence_posture="bounded",
                    answer_shape="low_movement_answer",
                )
            else:
                # KVS FAIL on structurally stable query:
                # route to verify to compensate for model unreliability.
                # This is the key v7.5 fix for the v3 failure mode.
                fail_code = kvs.kvs_fail_reason or ReasonCode.KVS_STABLE_BLOCKED.value
                return RouteDecision(
                    route="verify",
                    reason_codes=[
                        ReasonCode.KVS_STABLE_BLOCKED.value,
                        fail_code,
                    ],
                    confidence_posture="recover-evidence",
                )
    elif appraisal.stable_fact:
        # Fallback: stable_fact without KVS (backward compatibility)
        return RouteDecision(
            route="answer",
            reason_codes=[
                ReasonCode.LOW_STAKES_STABLE.value,
                ReasonCode.SUFFICIENTLY_SPECIFIED.value,
            ],
            confidence_posture="bounded",
            answer_shape="low_movement_answer",
        )

    # Rule 3: Freshness-sensitive or high uncertainty → verify
    if appraisal.freshness_sensitive or appraisal.uncertainty >= 0.7:
        return RouteDecision(
            route="verify",
            reason_codes=[
                ReasonCode.FRESHNESS_SENSITIVE.value,
                ReasonCode.EXTERNAL_DEPENDENCY.value,
            ],
            confidence_posture="recover-evidence",
        )

    # Phase G.8 — Rule 3.5: Definitional query (bare "what is X?" / "Xとは？").
    # These are not structural stable_facts (no hardcoded pattern) but they
    # benefit from an inspectable reason code, and — when KVS says the
    # domain is genuinely volatile — from the grounded verify path.
    #
    # Narrowed after QK-T02 regression: MKR_PRIOR-only failures (weak
    # prior recall) do NOT route to verify. Only volatility-class fails
    # (TVS / freshness downrev) escalate to verify. This keeps stable
    # scientific facts ("水の沸点は？") on the direct-answer path while
    # still grounding freshness-adjacent definitional queries.
    if getattr(appraisal, "definitional_query", False):
        if appraisal.kvs is not None and appraisal.kvs.low_stakes_eligible:
            return RouteDecision(
                route="answer",
                reason_codes=[
                    ReasonCode.DEFINITIONAL_QUERY.value,
                    ReasonCode.KVS_PASS_LOW_TVS_HIGH_MKR.value,
                    ReasonCode.SUFFICIENTLY_SPECIFIED.value,
                ],
                confidence_posture="bounded",
                answer_shape="low_movement_answer",
            )
        # KVS fail case — only escalate to verify for volatility-class fails.
        _volatility_fail_codes = {
            ReasonCode.KVS_FAIL_TVS.value,
            ReasonCode.KVS_DOWNREV_FRESH.value,
            ReasonCode.KVS_DOWNREV_HIST.value,
            ReasonCode.KVS_DYNAMIC_DOWNREV.value,
        }
        _fail = (appraisal.kvs.kvs_fail_reason
                  if appraisal.kvs is not None else None)
        if appraisal.kvs is not None and _fail in _volatility_fail_codes:
            return RouteDecision(
                route="verify",
                reason_codes=[
                    ReasonCode.DEFINITIONAL_NEEDS_EVIDENCE.value,
                    _fail,
                ],
                confidence_posture="recover-evidence",
            )
        # Default: still answer, but expose DEFINITIONAL_QUERY for
        # observability. Covers MKR_PRIOR borderline recall and the
        # no-KVS path.
        reasons = [
            ReasonCode.DEFINITIONAL_QUERY.value,
            ReasonCode.SUFFICIENTLY_SPECIFIED.value,
        ]
        if _fail:
            reasons.append(_fail)
        return RouteDecision(
            route="answer",
            reason_codes=reasons,
            confidence_posture="bounded",
            answer_shape="low_movement_answer",
        )

    # Rule 4: Default — answer
    return RouteDecision(
        route="answer",
        reason_codes=[
            ReasonCode.LOW_STAKES_STABLE.value,
            ReasonCode.SUFFICIENTLY_SPECIFIED.value,
        ],
        confidence_posture="bounded",
    )
