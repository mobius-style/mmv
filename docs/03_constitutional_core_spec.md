# 03 Constitutional Core Spec

## Purpose
This document defines the immutable control commitments of the Möbius MMV
runtime under the current L0 v8.4 authority.

Current authority:

- `prompts/l0_integrated_v8_4.md`
- `prompts/mobius_l0_v8_4_protocol.json`
- `docs/L0_V8_4_RC3_3_SYNC_NOTE.md`

## Core Principle
The runtime must determine whether answering is justified before answering.

## Fixed routes
- `answer`
- `ask`
- `verify`
- `date_bound_answer`
- `re_anchor`
- `abstain`

## Appraisal dimensions
- `completeness`
- `uncertainty`
- `freshness_sensitive`
- `safety_relevant`
- `intent_clarity`

## Route preconditions
### Rule A — Abstain
If the request violates the safety envelope or is otherwise inadmissible, route to `abstain`.

### Rule B — Ask
If the question itself is under-specified, ambiguous, or missing constraints, route to `ask`.

### Rule C — Re-anchor
If the request rests on a false, stale, or contaminated premise, route to
`re_anchor` before any answer commitment.

### Rule D — Verify / Date-bound Answer
If the question is sufficiently specified but answer entitlement depends on evidence outside the turn, route to `verify`.
If the system can answer only under an explicit temporal scope, route to
`date_bound_answer`.

### Rule E — Answer
If the request is low-stakes, sufficiently specified, structurally clear, and answerable without external recovery, route to `answer`.

## Ask / Verify conflict rule
- If target, timeframe, or evaluation frame is under-specified, prefer `ask`.
- If the question is specified but evidence is external, prefer `verify`.
- If both conditions apply, `ask` goes first.
- If a stale or false premise is already identifiable, prefer `re_anchor`
  before either `answer` or `date_bound_answer`.
- After clarification, a later turn may route to `verify`.
- `verify_failed` may fall back to `ask` if the dominant failure source is unresolved specification.

## Answer shaping layer
Route selection and answer shaping are separate.
When the selected route is `answer`, the runtime must choose between:
- `low_movement_answer`
- `admissible_reframing_answer`

Low movement is lawful. Reframing is bounded and non-compulsory.

## Language policy
- The control language of the kernel is English.
- User-facing output must be rendered strictly in the user’s active language.
- Hidden reasoning language is not specified.
- All route labels, reason codes, verification controls, retrieval synthesis controls, trace schema fields, and internal state keys are defined in English.
- Output language is tracked as `active_language` in `SessionState`.
- By default, `active_language` is updated turn-by-turn from the user’s latest input language.
- If the user explicitly sets a language preference, that preference overrides automatic switching until revised.
- Language detection is performed by the kernel using a model-independent mechanism.
- The kernel first applies script-based heuristics and falls back to a lightweight detector only when needed.
- If detection is inconclusive, `active_language` remains unchanged.
- If detection is inconclusive on the first turn, `active_language` defaults to English.

## Search policy
Search is route-driven, not default-on.
- `answer`: no search by default
- `ask`: no search
- `verify`: may use local retrieval, tool evidence, and/or web evidence recovery
- `date_bound_answer`: no search is required if the temporal bound is explicit
- `re_anchor`: search is optional; the premise correction must not exceed the
  available evidence
- `abstain`: search cannot override inadmissibility
