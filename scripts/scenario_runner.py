#!/usr/bin/env python3
"""Scenario runner — YAML-defined conversational regression harness.

Per Evolution Log cyc_20260424_stage_abc_trilingual_complete (Stage A).

YAML schema (tests/scenarios/*.yaml):

    name: "self_reference_integrity_ja"
    language: "ja" | "en" | "zh"
    category: "self_reference" | "casual_greeting" | "factual_krillin" | ...
    description: "short human-readable summary"
    active_language_seed: "ja"   # optional — seeds SessionState
    turns:
      - user: "貴方の特徴を教えてください"
        assert:
          route_in: ["answer", "verify"]
          route_not: ["ask", "abstain"]
          intent_type: "meta_question"
          self_referential: true
          box_0_consulted: true
          box_w_consulted: false
          response_must_contain_any: ["MOBIUS", "Möbius", "メビウス", "モビウス"]
          response_must_not_contain: ["clinical note", "chronic disease",
                                      "Yorushika", "ヨルシカ"]
          response_language: "ja"
          response_length_min: 20
          response_length_max: 1200
          reason_codes_must_include: []
          reason_codes_must_not_include: ["CASUAL_GREETING_FAST_PATH"]
          grounding_sources_min: 0
          tvs_max: 1.0

Assertions are ALL deterministic — we do not use an LLM-judge
(semantic_match) at runtime because overnight auto-execution needs
reproducible pass/fail. LLM semantic assessment is reserved for
diagnosis output, not scenario gating.

Usage:
    python scripts/scenario_runner.py tests/scenarios/001_ja_self_reference_integrity.yaml
    python scripts/scenario_runner.py tests/scenarios/           # all
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pseudo_ui_runner import PseudoUISession, TurnResult  # noqa: E402


logger = logging.getLogger(__name__)


# ── Assertion outcome ───────────────────────────────────────────────────────

@dataclass
class AssertionFailure:
    """One failed assertion on one turn."""
    turn_index: int
    assertion: str
    expected: Any
    actual: Any
    detail: str = ""


@dataclass
class ScenarioResult:
    """Result of running a single scenario (one or more turns)."""
    scenario_name: str
    scenario_file: str
    language: str
    category: str
    passed: bool
    failures: List[AssertionFailure] = field(default_factory=list)
    turn_results: List[TurnResult] = field(default_factory=list)
    total_time_ms: float = 0.0

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.scenario_name} ({self.language}/{self.category})"


# ── Assertion engine ────────────────────────────────────────────────────────

def _check_assertion(name: str, spec: Dict[str, Any],
                     turn: TurnResult, turn_idx: int) -> List[AssertionFailure]:
    """Run all assertion checks against one turn. Returns list of
    failures (empty when all pass)."""
    failures: List[AssertionFailure] = []

    def fail(assertion: str, expected: Any, actual: Any, detail: str = ""):
        failures.append(AssertionFailure(
            turn_index=turn_idx, assertion=assertion,
            expected=expected, actual=actual, detail=detail,
        ))

    # ─── Route ───────────────────────────────────────────────────────
    if "route" in spec:
        if turn.route != spec["route"]:
            fail("route", spec["route"], turn.route)
    if "route_in" in spec:
        if turn.route not in spec["route_in"]:
            fail("route_in", spec["route_in"], turn.route)
    if "route_not" in spec:
        if turn.route in spec["route_not"]:
            fail("route_not", spec["route_not"], turn.route)

    # ─── Intent type ─────────────────────────────────────────────────
    if "intent_type" in spec:
        if turn.intent_type != spec["intent_type"]:
            fail("intent_type", spec["intent_type"], turn.intent_type)
    if "intent_type_in" in spec:
        if turn.intent_type not in spec["intent_type_in"]:
            fail("intent_type_in", spec["intent_type_in"], turn.intent_type)

    # ─── Self-ref flag ───────────────────────────────────────────────
    if "self_referential" in spec:
        if bool(turn.self_referential) != bool(spec["self_referential"]):
            fail("self_referential", spec["self_referential"],
                 turn.self_referential)

    # ─── Box consultation flags ─────────────────────────────────────
    # C.3 fix (cyc_20260424_factual_integration_c3_fix) added box_s
    # (Brave / web search). Original 3 box flags retained.
    for flag in ("box_0_consulted", "box_w_consulted",
                 "box_x_consulted", "box_s_consulted"):
        if flag in spec:
            if bool(getattr(turn, flag, False)) != bool(spec[flag]):
                fail(flag, spec[flag], getattr(turn, flag, False))

    # ─── Response content ────────────────────────────────────────────
    if "response_must_contain_any" in spec:
        needles = spec["response_must_contain_any"] or []
        if not any(n in turn.response_text for n in needles):
            fail("response_must_contain_any", needles,
                 turn.response_text[:200] + "...",
                 "none of the required substrings found")
    if "response_must_contain_all" in spec:
        needles = spec["response_must_contain_all"] or []
        missing = [n for n in needles if n not in turn.response_text]
        if missing:
            fail("response_must_contain_all", needles,
                 turn.response_text[:200] + "...",
                 f"missing: {missing}")
    if "response_must_not_contain" in spec:
        for n in (spec["response_must_not_contain"] or []):
            if n in turn.response_text:
                fail("response_must_not_contain", n,
                     turn.response_text[:200] + "...",
                     f"forbidden substring present: {n!r}")

    # ─── Response length ─────────────────────────────────────────────
    if "response_length_min" in spec:
        if len(turn.response_text) < spec["response_length_min"]:
            fail("response_length_min", spec["response_length_min"],
                 len(turn.response_text))
    if "response_length_max" in spec:
        if len(turn.response_text) > spec["response_length_max"]:
            fail("response_length_max", spec["response_length_max"],
                 len(turn.response_text))

    # ─── Response language ───────────────────────────────────────────
    if "response_language" in spec:
        if turn.response_language != spec["response_language"]:
            fail("response_language", spec["response_language"],
                 turn.response_language)

    # ─── Reason codes ────────────────────────────────────────────────
    rc = set(turn.reason_codes)
    if "reason_codes_must_include" in spec:
        for code in (spec["reason_codes_must_include"] or []):
            if code not in rc:
                fail("reason_codes_must_include", code,
                     list(rc), f"missing reason_code: {code}")
    if "reason_codes_must_not_include" in spec:
        for code in (spec["reason_codes_must_not_include"] or []):
            if code in rc:
                fail("reason_codes_must_not_include", code,
                     list(rc), f"forbidden reason_code: {code}")

    # ─── Grounding sources ───────────────────────────────────────────
    if "grounding_sources_min" in spec:
        if len(turn.grounding_sources) < spec["grounding_sources_min"]:
            fail("grounding_sources_min", spec["grounding_sources_min"],
                 len(turn.grounding_sources))

    # ─── TVS bounds ──────────────────────────────────────────────────
    if "tvs_min" in spec and turn.tvs < spec["tvs_min"]:
        fail("tvs_min", spec["tvs_min"], turn.tvs)
    if "tvs_max" in spec and turn.tvs > spec["tvs_max"]:
        fail("tvs_max", spec["tvs_max"], turn.tvs)

    # ─── Error check ─────────────────────────────────────────────────
    if spec.get("must_not_error", True) and turn.error:
        fail("must_not_error", None, turn.error,
             "engine.evaluate raised an exception")

    return failures


# ── Scenario execution ──────────────────────────────────────────────────────

# ── v2 (cyc_20260424_methodology_v2_implementation_and_honest_baseline)
#
# Methodology v2 additions to the YAML schema. v1 (per-turn `assert`
# dicts above) is preserved unchanged; v2 lives in a scenario-level
# `v2_assertions` list and an optional `stochastic_gate` block.
#
#   v2_assertions:
#     - response_must_semantically_contain:
#         concept: "MOBIUS canonical identity (Answer Entitlement / Box / SGP)"
#         min_score: 3                  # 5-point judge scale
#         judge_model: "openai/gpt-oss-120b"
#         apply_to_turn: -1             # -1 = last turn (default)
#     - response_must_not_semantically_contain:
#         concept: "..."
#         max_score: 2                  # contains if judge >= 3 (FAIL)
#         apply_to_turn: -1
#     - response_must_not_cite_source:
#         url_patterns: ["wikipedia.org/wiki/.*disambiguation"]
#         apply_to_turn: -1
#     - multi_turn_identity_consistency:
#         turns: [0, 1, 2]
#         check_prompt: "..."
#         min_score: 3
#     - context_fit_with_prev_turns:
#         apply_to_turn: 1              # which turn to evaluate
#         check_prompt: "..."
#         min_score: 3
#     - shiritori_rule_adherence:
#         user_turn: 1                  # the user's word that sets next syllable
#         response_turn: 1              # which turn's response to evaluate
#         min_score: 3
#
#   stochastic_gate:
#     runs: 5
#     min_pass: 4
#     # When stochastic_gate is set the entire scenario (turns + v2 +
#     # v1 assertions) is run N times. min_pass / runs is required.
#
# All v2 LLM-judge assertions share a single Groq judge helper. URL
# blacklists work against grounding_sources labels AND the response
# text body (citations like "URL: https://...").

import re as _re_v2

_V2_LLM_JUDGE_AVAILABLE = None


def _get_groq_client():
    """Lazy-construct a single Groq client for v2 judge calls."""
    global _V2_LLM_JUDGE_AVAILABLE, _groq_client_singleton
    if _V2_LLM_JUDGE_AVAILABLE is None:
        try:
            from eval.rl_bench.groq_client import GroqClient  # noqa: E402
            _groq_client_singleton = GroqClient()
            _V2_LLM_JUDGE_AVAILABLE = True
        except Exception as e:
            logger.warning(f"[v2] Groq client unavailable: {e}")
            _V2_LLM_JUDGE_AVAILABLE = False
            _groq_client_singleton = None
    return _groq_client_singleton if _V2_LLM_JUDGE_AVAILABLE else None


_V2_JUDGE_SYSTEM = (
    "You are a strict evaluator scoring a conversational AI's response "
    "on a single specified dimension. Rate the response 1-5 (1=very "
    "poor / does not satisfy / 5=excellent / fully satisfies). Return "
    "ONLY a JSON object: {\"score\": 1-5, \"reason\": \"one short sentence\"}. "
    "No prose, no markdown fences."
)


def _llm_judge(check_prompt: str, content: str,
               judge_model: str = "openai/gpt-oss-120b") -> Dict[str, Any]:
    """Single-shot Groq LLM-judge call. Returns dict with score and
    reason; on Groq failure falls back to llama-3.3-70b-versatile;
    on full failure returns score=0 and an error reason (which yields
    a FAIL on min_score>=1)."""
    client = _get_groq_client()
    if client is None:
        return {"score": 0, "reason": "groq client unavailable",
                "_model": "none"}

    user = (
        f"{check_prompt}\n\n"
        f"--- Content to evaluate ---\n{content[:3500]}\n--- End ---"
    )
    msgs = [
        {"role": "system", "content": _V2_JUDGE_SYSTEM},
        {"role": "user", "content": user},
    ]

    def _try(model):
        r = client.chat(model=model, messages=msgs, temperature=0.0,
                        max_tokens=200)
        if r.get("error"):
            return None, r["error"]
        txt = (r.get("text") or "").strip()
        if txt.startswith("```"):
            parts = txt.split("```")
            txt = parts[1] if len(parts) >= 2 else txt
            if txt.startswith("json"):
                txt = txt[4:]
            txt = txt.strip()
        try:
            obj = json.loads(txt)
            if "score" in obj and isinstance(obj["score"], (int, float)):
                obj["_model"] = model
                return obj, None
            return None, f"missing score: {txt[:120]}"
        except Exception as e:
            return None, f"parse: {e} | raw={txt[:120]}"

    parsed, err1 = _try(judge_model)
    if parsed:
        return parsed
    parsed, err2 = _try("llama-3.3-70b-versatile")
    if parsed:
        parsed["_fallback"] = err1
        return parsed
    return {"score": 0, "reason": f"groq fail: {err1} | llama: {err2}",
            "_model": "none"}


def _v2_check_one(item: Dict[str, Any],
                  turn_results: List[TurnResult]) -> List[AssertionFailure]:
    """Evaluate a single v2 assertion item. Returns 0 or 1 failures."""
    if not isinstance(item, dict) or len(item) != 1:
        return [AssertionFailure(
            turn_index=-1, assertion="v2_assertion_shape",
            expected="single-key dict", actual=str(item)[:80],
            detail="each v2_assertions list item must be a single-key dict",
        )]
    assertion_type, spec = next(iter(item.items()))
    spec = spec or {}

    def _resolve_turn(idx_spec: Any) -> int:
        if not turn_results:
            return -1
        if idx_spec is None:
            return len(turn_results) - 1  # last turn
        try:
            i = int(idx_spec)
        except Exception:
            return -1
        if i < 0:
            i = len(turn_results) + i
        return i if 0 <= i < len(turn_results) else -1

    if assertion_type == "response_must_semantically_contain":
        idx = _resolve_turn(spec.get("apply_to_turn"))
        if idx < 0:
            return [AssertionFailure(
                turn_index=-1, assertion=assertion_type,
                expected="valid turn index", actual=spec.get("apply_to_turn"),
            )]
        tr = turn_results[idx]
        concept = spec.get("concept", "")
        min_score = int(spec.get("min_score", 3))
        check_prompt = (
            f"Does the response semantically contain / address the "
            f"following concept? Concept: «{concept}». A high score "
            f"(4-5) requires the response to clearly demonstrate / "
            f"include the concept; a low score (1-2) means the concept "
            f"is absent or only superficially mentioned."
        )
        verdict = _llm_judge(check_prompt, tr.response_text or "",
                             judge_model=spec.get("judge_model",
                                                   "openai/gpt-oss-120b"))
        score = int(verdict.get("score", 0))
        if score < min_score:
            return [AssertionFailure(
                turn_index=idx, assertion=assertion_type,
                expected=f">= {min_score}", actual=score,
                detail=f"concept={concept!r} reason={verdict.get('reason','')[:160]}",
            )]
        return []

    if assertion_type == "response_must_not_semantically_contain":
        idx = _resolve_turn(spec.get("apply_to_turn"))
        if idx < 0:
            return [AssertionFailure(
                turn_index=-1, assertion=assertion_type,
                expected="valid turn index", actual=spec.get("apply_to_turn"),
            )]
        tr = turn_results[idx]
        concept = spec.get("concept", "")
        max_score = int(spec.get("max_score", 2))
        check_prompt = (
            f"Does the response semantically contain the following "
            f"undesired concept? Concept: «{concept}». A high score "
            f"(4-5) means YES the response contains it (this is BAD), "
            f"a low score (1-2) means NO it doesn't (this is GOOD)."
        )
        verdict = _llm_judge(check_prompt, tr.response_text or "",
                             judge_model=spec.get("judge_model",
                                                   "openai/gpt-oss-120b"))
        score = int(verdict.get("score", 0))
        if score > max_score:
            return [AssertionFailure(
                turn_index=idx, assertion=assertion_type,
                expected=f"<= {max_score}", actual=score,
                detail=f"undesired_concept={concept!r} reason={verdict.get('reason','')[:160]}",
            )]
        return []

    if assertion_type == "response_must_not_cite_source":
        idx = _resolve_turn(spec.get("apply_to_turn"))
        if idx < 0:
            return [AssertionFailure(
                turn_index=-1, assertion=assertion_type,
                expected="valid turn index", actual=spec.get("apply_to_turn"),
            )]
        tr = turn_results[idx]
        patterns = spec.get("url_patterns", []) or []
        haystack_parts = [tr.response_text or ""]
        for src in (tr.grounding_sources or []):
            haystack_parts.append(str(src))
        haystack = "\n".join(haystack_parts)
        hits = []
        for pat in patterns:
            try:
                if _re_v2.search(pat, haystack, _re_v2.IGNORECASE):
                    hits.append(pat)
            except _re_v2.error:
                if pat in haystack:
                    hits.append(pat)
        if hits:
            return [AssertionFailure(
                turn_index=idx, assertion=assertion_type,
                expected="no URL matches",
                actual=f"matched: {hits}",
                detail="forbidden URL pattern(s) found in response or grounding",
            )]
        return []

    if assertion_type == "multi_turn_identity_consistency":
        turns_idx = spec.get("turns", list(range(len(turn_results))))
        check = spec.get("check_prompt",
                         "Across these turns, does the assistant maintain "
                         "a consistent identity claim without "
                         "contradicting itself?")
        min_score = int(spec.get("min_score", 3))
        if not turn_results:
            return [AssertionFailure(
                turn_index=-1, assertion=assertion_type,
                expected="some turns", actual=0,
            )]
        dialogue = []
        for i in turns_idx:
            if 0 <= i < len(turn_results):
                tr = turn_results[i]
                dialogue.append(f"[Turn {i}] USER: {tr.user_input}\n"
                                 f"[Turn {i}] ASSISTANT: "
                                 f"{(tr.response_text or '')[:600]}")
        content = "\n\n".join(dialogue)
        verdict = _llm_judge(check, content,
                             judge_model=spec.get("judge_model",
                                                   "openai/gpt-oss-120b"))
        score = int(verdict.get("score", 0))
        if score < min_score:
            return [AssertionFailure(
                turn_index=-1, assertion=assertion_type,
                expected=f">= {min_score}", actual=score,
                detail=f"reason={verdict.get('reason','')[:200]}",
            )]
        return []

    if assertion_type == "context_fit_with_prev_turns":
        # Two accepted forms:
        #   (a) apply_to_turn: N     -> judge turn N against turns [0..N-1]
        #   (b) turns: [i, j, ...]   -> judge the last index against earlier
        turns_list = spec.get("turns")
        if isinstance(turns_list, list) and turns_list:
            idxs = [int(i) for i in turns_list
                    if 0 <= int(i) < len(turn_results)]
            if len(idxs) < 2:
                return [AssertionFailure(
                    turn_index=-1, assertion=assertion_type,
                    expected="at least 2 valid turn indices",
                    actual=idxs,
                )]
            idx = idxs[-1]
            prior_idxs = idxs[:-1]
        else:
            idx = _resolve_turn(spec.get("apply_to_turn"))
            if idx < 0 or idx == 0:
                return [AssertionFailure(
                    turn_index=idx, assertion=assertion_type,
                    expected="turn index >= 1",
                    actual=idx,
                    detail="context_fit requires a prior turn",
                )]
            prior_idxs = list(range(idx))
        check = spec.get("check_prompt",
                         "Does the assistant's response in this turn "
                         "appropriately reference or build on the prior "
                         "turn(s) in the conversation?")
        min_score = int(spec.get("min_score", 3))
        prior_dialogue = []
        for i in prior_idxs:
            tr = turn_results[i]
            prior_dialogue.append(f"USER: {tr.user_input}\n"
                                   f"ASSISTANT: {(tr.response_text or '')[:600]}")
        cur = turn_results[idx]
        content = (
            "Prior turns:\n" + "\n\n".join(prior_dialogue)
            + f"\n\nCurrent turn:\nUSER: {cur.user_input}\n"
            f"ASSISTANT: {(cur.response_text or '')[:600]}"
        )
        verdict = _llm_judge(check, content,
                             judge_model=spec.get("judge_model",
                                                   "openai/gpt-oss-120b"))
        score = int(verdict.get("score", 0))
        if score < min_score:
            return [AssertionFailure(
                turn_index=idx, assertion=assertion_type,
                expected=f">= {min_score}", actual=score,
                detail=f"reason={verdict.get('reason','')[:200]}",
            )]
        return []

    if assertion_type == "shiritori_rule_adherence":
        # Two accepted forms:
        #   (a) user_turn: i, response_turn: j  -> single pair
        #   (b) turns: [i, j, ...]              -> full dialogue judged
        #                                          as a chain
        min_score = int(spec.get("min_score", 3))
        turns_list = spec.get("turns")
        if isinstance(turns_list, list) and turns_list:
            idxs = [int(i) for i in turns_list
                    if 0 <= int(i) < len(turn_results)]
            if not idxs:
                return [AssertionFailure(
                    turn_index=-1, assertion=assertion_type,
                    expected="valid turn indices",
                    actual=turns_list,
                )]
            dialogue = []
            for i in idxs:
                tr = turn_results[i]
                dialogue.append(f"[Turn {i}] USER: {tr.user_input}\n"
                                 f"[Turn {i}] ASSISTANT: "
                                 f"{(tr.response_text or '')[:600]}")
            content = "\n\n".join(dialogue)
            check = spec.get("check_prompt",
                             "Evaluate Japanese shiritori rule adherence "
                             "across these turns: each proposed word "
                             "must start with the last mora of the "
                             "previous word, ん-terminal loses, no "
                             "repeats. Score 5 = strict compliance, "
                             "3 = partial, 1 = rule ignored.")
            verdict = _llm_judge(check, content,
                                 judge_model=spec.get("judge_model",
                                                       "openai/gpt-oss-120b"))
            score = int(verdict.get("score", 0))
            if score < min_score:
                return [AssertionFailure(
                    turn_index=-1, assertion=assertion_type,
                    expected=f">= {min_score}", actual=score,
                    detail=f"reason={verdict.get('reason','')[:200]}",
                )]
            return []
        user_turn_idx = int(spec.get("user_turn", 0))
        resp_turn_idx = int(spec.get("response_turn",
                                       len(turn_results) - 1))
        if not (0 <= user_turn_idx < len(turn_results)
                and 0 <= resp_turn_idx < len(turn_results)):
            return [AssertionFailure(
                turn_index=-1, assertion=assertion_type,
                expected="valid turn indices",
                actual=f"user={user_turn_idx} resp={resp_turn_idx}",
            )]
        user_word = turn_results[user_turn_idx].user_input.strip()
        resp = (turn_results[resp_turn_idx].response_text or "").strip()
        check = (
            f"In the shiritori (Japanese word-chain) game, the user's "
            f"word is «{user_word}». Does the assistant's response "
            f"propose a word that begins with the LAST MORA of «{user_word}» "
            f"AND respect basic shiritori rules (e.g. ん in last mora "
            f"means loss; the response should be a single noun word, "
            f"not a long explanation)? Score 5 = strict rule compliance, "
            f"3 = partial / close, 1 = no rule attempt."
        )
        verdict = _llm_judge(check, resp,
                             judge_model=spec.get("judge_model",
                                                   "openai/gpt-oss-120b"))
        score = int(verdict.get("score", 0))
        if score < min_score:
            return [AssertionFailure(
                turn_index=resp_turn_idx, assertion=assertion_type,
                expected=f">= {min_score}", actual=score,
                detail=f"user_word={user_word!r} reason={verdict.get('reason','')[:200]}",
            )]
        return []

    return [AssertionFailure(
        turn_index=-1, assertion="v2_unknown_type",
        expected="known v2 type", actual=assertion_type,
        detail="unrecognized v2 assertion type",
    )]


def _v2_check_assertions(scenario_data: Dict[str, Any],
                         turn_results: List[TurnResult]) -> List[AssertionFailure]:
    """Evaluate all v2_assertions in a scenario. No-op if absent."""
    out: List[AssertionFailure] = []
    items = scenario_data.get("v2_assertions") or []
    for item in items:
        out.extend(_v2_check_one(item, turn_results))
    return out


def _run_scenario_once(path: Path, data: Dict[str, Any],
                       session: Optional[PseudoUISession] = None) -> ScenarioResult:
    """Single execution of a scenario (one path through turns + assertions).
    Used directly for non-stochastic scenarios; called N times by the
    stochastic_gate wrapper."""
    name = data.get("name") or path.stem
    language = data.get("language") or ""
    category = data.get("category") or ""
    lang_seed = data.get("active_language_seed") or language
    turns_spec = data.get("turns") or []

    result = ScenarioResult(
        scenario_name=name, scenario_file=str(path),
        language=language, category=category, passed=True,
    )
    sess = session if session is not None else PseudoUISession()
    if session is None and lang_seed:
        sess.state.active_language = lang_seed

    for idx, turn_spec in enumerate(turns_spec):
        user = turn_spec.get("user") or ""
        asserts = turn_spec.get("assert") or {}
        tr = sess.process_turn(user, target_lang=lang_seed if idx == 0 else None)
        # Stash user_input on TurnResult for v2 judge access
        try:
            tr.user_input = user
        except Exception:
            pass
        result.turn_results.append(tr)
        result.total_time_ms += tr.processing_time_ms
        result.failures.extend(_check_assertion(name, asserts, tr, idx))

    result.failures.extend(_v2_check_assertions(data, result.turn_results))
    result.passed = len(result.failures) == 0
    return result


def run_scenario(path: Path,
                 session: Optional[PseudoUISession] = None) -> ScenarioResult:
    """Run one scenario from a YAML file. Honors v2 stochastic_gate
    if specified — re-runs the scenario N times and treats the
    composite as PASS only if K/N runs individually pass."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    sg = data.get("stochastic_gate")

    if not sg:
        return _run_scenario_once(path, data, session=session)

    runs = int(sg.get("runs", 3))
    min_pass = int(sg.get("min_pass", runs))
    sub_results = []
    for i in range(runs):
        sub_results.append(_run_scenario_once(path, data, session=None))
    pass_count = sum(1 for r in sub_results if r.passed)

    name = data.get("name") or path.stem
    composite = ScenarioResult(
        scenario_name=name, scenario_file=str(path),
        language=data.get("language") or "",
        category=data.get("category") or "",
        passed=(pass_count >= min_pass),
    )
    composite.total_time_ms = sum(r.total_time_ms for r in sub_results)
    # Carry latest run's turn_results for inspection
    composite.turn_results = sub_results[-1].turn_results
    if not composite.passed:
        per_run = [
            f"run {i+1}: {'PASS' if r.passed else 'FAIL'}"
            f" ({len(r.failures)} fail)" for i, r in enumerate(sub_results)
        ]
        composite.failures.append(AssertionFailure(
            turn_index=-1, assertion="stochastic_gate",
            expected=f"{min_pass}/{runs} runs PASS",
            actual=f"{pass_count}/{runs}",
            detail=" | ".join(per_run),
        ))
    return composite


def run_many(paths: List[Path]) -> List[ScenarioResult]:
    """Run multiple scenarios in sequence with independent sessions."""
    out: List[ScenarioResult] = []
    for p in sorted(paths):
        r = run_scenario(p)
        out.append(r)
        logger.info(r.summary())
    return out


# ── CLI ─────────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(description="Scenario runner CLI")
    parser.add_argument("path", help="YAML file or directory of scenarios")
    parser.add_argument("--json", action="store_true",
                        help="Emit structured JSON result")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    target = Path(args.path)
    if target.is_dir():
        files = sorted(target.glob("*.yaml")) + sorted(target.glob("*.yml"))
    else:
        files = [target]

    results = run_many(files)

    # Summary
    pass_count = sum(1 for r in results if r.passed)
    total = len(results)
    print()
    print(f"===== Scenario results: {pass_count}/{total} passed =====")

    # Language / category breakdown
    by_lang: Dict[str, List[int]] = {}  # lang -> [pass, total]
    by_cat: Dict[str, List[int]] = {}
    for r in results:
        by_lang.setdefault(r.language, [0, 0])
        by_lang[r.language][1] += 1
        by_lang[r.language][0] += int(r.passed)
        by_cat.setdefault(r.category, [0, 0])
        by_cat[r.category][1] += 1
        by_cat[r.category][0] += int(r.passed)
    print("By language:")
    for lang, (p, t) in sorted(by_lang.items()):
        print(f"  {lang or '(unset)':6s}: {p}/{t}")
    print("By category:")
    for cat, (p, t) in sorted(by_cat.items()):
        print(f"  {cat or '(unset)':30s}: {p}/{t}")

    if not args.json:
        # Per-failure detail
        for r in results:
            if r.passed:
                continue
            print()
            print(f"--- FAIL: {r.scenario_name} ({r.language}/{r.category}) ---")
            for f in r.failures:
                print(f"  turn {f.turn_index}: {f.assertion}")
                print(f"    expected: {f.expected}")
                print(f"    actual:   {f.actual}")
                if f.detail:
                    print(f"    detail:   {f.detail}")

    if args.json:
        out = []
        for r in results:
            out.append({
                "scenario_name": r.scenario_name,
                "language": r.language,
                "category": r.category,
                "passed": r.passed,
                "failures": [asdict(f) for f in r.failures],
                "total_time_ms": r.total_time_ms,
            })
        print(json.dumps(out, ensure_ascii=False, indent=2))

    sys.exit(0 if pass_count == total else 1)


if __name__ == "__main__":
    _cli()
