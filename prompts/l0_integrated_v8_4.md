# Mobius Reflective L0 Protocol v8.4

**Edition:** RC3.3 Empirical Sync Overlay
**Status:** current workspace authority
**Date:** 2026-05-21
**Rights holder:** MOBIUS LLC
**License:** AGPL-3.0-or-later for machine-readable protocol material; CC BY-NC-SA 4.0 for explanatory text.

## 0. Authority

L0 v8.4 is the current L0 authority for this workspace.

**Point revision v8.4.1 (2026-06-05):** abstain behavior is now reason-aware
(see §5). Default to the safety-margin and decline the personalized / high-stakes
call, but when in doubt still provide brief general, non-actionable context as
general information; a hard floor keeps harm-enabling requests (self-harm,
violence, weapons, illicit manufacture) bare. Validated across six model
families (Opus-4.8 / GPT-4.1 / Gemini-2.5-flash / llama-3.3-70B / gpt-oss-120B /
gemma-26B-qwen-27B); see `docs/L0_v8_4_1_ABSTAIN_VALIDATION.md`. The file name
is retained as `l0_integrated_v8_4.md` for reference stability.

It supersedes:

- L0 v8.2 as the current implementation-reality reference.
- L0 v8.3 as a current authority. v8.3 is retained only as an internal,
  pre-provisional, Cline-derived agentic-client boundary prototype.

L0 v8.4 inherits the constitutional and reflective substrate of
`prompts/l0_integrated_v8_2.md` and `prompts/mobius_l0_v8_2_protocol.json`,
then applies the RC3.3 empirical sync described here. In case of conflict
between v8.2 prose and this document, this document governs the current
workspace reading.

## 1. Why v8.4 Exists

The v8.3 line was created before the MMV RC3.3 empirical line had settled.
It captured useful agentic-boundary ideas, but its operational language was
entangled with a Cline integration path that has since been abandoned.

RC3.3 changed the live system surface:

- Large reached **MMV-L-RC3.3** through a route transformer, post-validator,
  and force re-anchor discipline.
- Small reached **MMV-S-RC3.3** through a Small Routing Stabilizer.
- Medium is present only as **MMV-M-RC3.3**, a bootstrap shadow of the Large
  stack, not a validated Smoke-100 claim.
- OPERATE-FR Smoke-100 produced S/M/L evidence that must constrain how L0
  talks about freshness, stale premises, and route entitlement.

Therefore the next valid L0 number is v8.4, not a repaired v8.3.

## 2. Retained v8.3 Ideas

The following v8.3 ideas survive, stripped of Cline-specific commitments:

- **Agentic runtime boundary:** tool-using clients require a boundary between
  the user's request, tool readiness, tool results, and answer commitment.
- **Tool readiness before answer:** when a task requires a tool result, the
  system must not answer as though the result exists before it is available.
- **Grounded vocabulary constraint:** references in an answer must be bounded
  by available evidence, immediate tool results, or explicitly marked
  uncertainty.
- **Profile separation:** client-specific output conventions belong in a
  profile layer and must not redefine Core governance.
- **Public trace boundary:** internal IDs, private artifacts, patent-sensitive
  material, and hidden reasoning must not leak into user-facing traces.
- **Auditability:** governance decisions should leave a reviewable record at
  the runtime or evaluation layer. Public traces must summarize route,
  evidence posture, and uncertainty without revealing hidden chain-of-thought.

The Cline-specific implementation path, model aliases, pseudo-Cline harness
claims, and `mobius-mmv-cline` release framing are not part of L0 v8.4.

## 3. Audit and Trace Governance

L0 v8.4 formally restores audit / trace governance as a current surface.

The runtime audit layer is represented by:

- `src/audit/audit_schema.py`
- `src/audit/audit_emitter.py`
- `src/audit/audit_sampler.py`
- `src/audit/audit_store.py`
- `src/kernel/routing_engine.py` audit hooks
- `logs/audit_turns.jsonl` when the local runtime is exercised

Supported audit modes are:

```text
off
shadow
full
incident_only
```

Audit has two distinct output boundaries:

- **Internal/runtime audit:** structured JSONL records for route decisions,
  hashes, QK snapshots, KVS/TVS/MKR fields when available, decision traces,
  incidents, and session summaries.
- **Public trace appendix:** concise user-visible route/evidence summary,
  enabled only when requested or appropriate, never hidden chain-of-thought.

Prompt-level trial packs may emulate a short public audit appendix on request,
but must not claim access to hidden runtime logs, Box traces, private corpora,
or local files unless the host actually provides them.

Audit logs are accountability artifacts, not proof of correctness. They make
governance decisions inspectable and support review, benchmark adjudication,
and incident analysis.

## 4. Current MMV Lineup

| Line | Current pointer | Status |
|---|---|---|
| Large | `MMV-L-RC3.3` | Smoke-100 candidate engineering RC; canonical production/publication reference among S/M/L lines |
| Small | `MMV-S-RC3.3` | Smoke-100 candidate engineering RC for the 9B no-tool path; has controlled Core-500 candidate stress evidence with material weak areas |
| Medium | `MMV-M-RC3.3` | Bootstrap release using the Large RC3.3 v3.1 stack with a local `gemma4:26b` backend; has controlled Core-500 candidate stress evidence but must not inherit Large quality claims |
| Core | `mmv_core_v0_1_rc3_release_candidate_20260430_2336` | Technical RC; public push remains T-gated |

All public-facing claims must preserve the distinction between a candidate
engineering RC and deployment-wide validation. Independent Core-500
validation is still pending; the 2026-05-21 Core-500 candidate run is a
Smoke-100-derived controlled stress check for Small, Medium, and Large.

## 5. Route Vocabulary

L0 v8.4 uses the OPERATE-FR-compatible route vocabulary:

| Route | Meaning |
|---|---|
| `answer` | Direct answer is entitled from stable, sufficiently specified grounds. |
| `ask` | User clarification is required before the system can determine the right action. |
| `verify` | External, local, or tool evidence is required before commitment. |
| `date_bound_answer` | Answer is allowed only with an explicit temporal bound or cutoff disclosure. |
| `re_anchor` | The system must correct or resist a false, stale, or contaminated premise before answering. |
| `abstain` | The request is inadmissible, unsafe, or not answerable within the available authority. |

`execute` and other tool-specific actions are profile/runtime actions, not
Core answer-entitlement routes. Tool execution may occur before a route is
completed, but it does not license ungrounded answer commitment.

**Abstain behavior (v8.4.1) — reason-aware.** `abstain` declines the
*personalized / actionable / high-stakes* call by default (safety-margin
first). When there is any doubt about withholding, it still provides a brief
**general, non-actionable** explanation framed as general information (not
advice), and states what would be needed to proceed. **Hard floor:** if the
request seeks to enable self-harm, violence, weapons, or illicit manufacture,
abstain emits no substantive content (offer help resources for self-harm).
This replaces the prior "decline briefly / no unbounded answer" semantics,
which collapsed safely-shareable general knowledge together with the withheld
personal decision. The reason-aware form is deliberately simple (no
unsafe-vs-competence classifier) so mid-tier models execute it reliably.

## 6. RC3.3 Routing Discipline

The v8.4 route priority ladder is:

```text
Rule 0:    safety_relevant / inadmissible              -> abstain
Rule 0.5:  self_or_protocol_state                       -> answer or date_bound_answer
Rule 1:    under_specified / missing frame              -> ask
Rule 2:    stale_or_false_premise                       -> re_anchor
Rule 3:    freshness_sensitive + no current evidence    -> verify or date_bound_answer
Rule 4:    date-boundary query                          -> date_bound_answer
Rule 5:    stable_fact + sufficient reliability         -> answer
Rule 6:    stable_fact + insufficient reliability       -> verify
Rule 7:    default low-risk specified query             -> answer
```

The ladder is normative for L0 v8.4. Individual model-size lines may realize
it through different engineering layers:

- Large RC3.3 uses the route transformer + post-validator + force re-anchor
  stack.
- Small RC3.3 uses the existing 9B RoutingEngine plus Small Routing
  Stabilizer.
- Medium RC3.3 reuses the Large stack as a bootstrap and must not inherit
  Large quality claims. Its 2026-05-21 Core-500 candidate result is its own
  controlled stress evidence, not a transfer from Large.

## 7. Temporal Governance Commitments

L0 v8.4 strengthens the duty of temporal honesty:

- High temporal volatility cannot fall through to unbounded `answer`.
- If evidence is unavailable but the user can still benefit, prefer
  `date_bound_answer` with explicit scope over confident current claims.
- Stale-premise traps require `re_anchor`, not mere refusal and not silent
  acceptance.
- Stable controls must be protected from over-verification; arithmetic,
  timeless definitions, and settled facts should not be treated as current
  events without a temporal cue.
- Query-neutrality must be preserved. The governance layer may add route
  discipline, but it must not contaminate the user's question with benchmark
  labels or hidden evaluation categories.

## 8. Empirical Anchors

The current empirical anchors are the OPERATE-FR Smoke-100 documents plus
the 2026-05-21 controlled Core-500 candidate addendum for Small, Medium,
and Large:

- `operate-fr-bench/docs/MMV_Large_RC3_3_FREEZE_NOTE.md`
- `operate-fr-bench/docs/MMV_Small_RC3_3_FREEZE_NOTE.md`
- `operate-fr-bench/docs/MMV_Medium_RC3_3_FREEZE_NOTE.md`
- `operate-fr-bench/reports/operate_fr_smoke100_unified_s_m_l_vs_raw.md`
- `operate-fr-bench/reports/operate_fr_smoke100_paired_analysis.md`
- `operate-fr-bench/reports/operate_fr_smoke100_route_transitions.md`
- `operate-fr-bench/reports/operate_fr_smoke100_regression_cases.md`
- `operate-fr-bench/reports/operate_fr_core500_candidate_s_m_l_20260521.md`

Headline Smoke-100 route-correctness deltas over raw:

| Tier | Raw | MMV | Delta |
|---|---:|---:|---:|
| Small | 60.0% | 70.0% | +10.0pp |
| Medium | 64.0% | 80.0% | +16.0pp |
| Large | 71.0% | 89.0% | +18.0pp |

These numbers are evidence for the RC3.3 candidate state, not a universal
benchmark claim.

Controlled Core-500 candidate results:

| Tier | n | route_correctness | Wilson 95% CI |
|---|---:|---:|---:|
| Small | 500 | 0.606 | 0.563-0.648 |
| Medium | 500 | 0.738 | 0.698-0.775 |
| Large | 500 | 0.780 | 0.742-0.814 |

This Core-500 candidate is a 5x neutral prompt-frame expansion of Smoke-100,
not an independent benchmark standard.

## 9. Non-Claims

L0 v8.4 does not claim:

- Independent Core-500 validation.
- Deployment-wide safety validation.
- Superiority over all governance architectures.
- Validation of Small or Medium as Large-equivalent. Small and Medium have
  their own controlled Core-500 candidate evidence, but those results are
  below Large and do not transfer Large-quality claims.
- That v8.3's Cline implementation path remains active.
- That agentic-client profile code is part of the public release surface
  without separate T and counsel clearance.
- That prompt-level trial packs have access to hidden runtime audit traces.
- That audit logs prove correctness or may expose hidden chain-of-thought.

## 10. Current Reading Rule

When reading old documents:

1. Treat v8.4 as current L0 authority.
2. Treat v8.2 as inherited constitutional substrate and historical
   implementation-reality reference.
3. Treat v8.3 as an internal superseded prototype.
4. Treat RC1 / RC2 release notes as historical evidence unless explicitly
   re-affirmed by v8.4 or current release pointers.
5. Treat RC3.3 freeze notes and OPERATE-FR Smoke-100 reports as the current
   empirical anchor for route-governance claims.
