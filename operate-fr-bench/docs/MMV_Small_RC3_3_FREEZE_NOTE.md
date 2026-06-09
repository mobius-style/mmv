# MMV Small RC3.3 — Routing Stabilization Update — FREEZE NOTE

| Field | Value |
|---|---|
| Release name | **MMV Small RC3.3 — Routing Stabilization Update** |
| Short name | MMV-S-RC3.3 |
| Suggested tag | `mmv-small-rc3.3-routing-stabilization-20260516` |
| Freeze date (UTC) | 2026-05-16 |
| Validation context | OPERATE-FR v0.1 Smoke-100 (no-tool, Small-model / 9B path) |
| RC basis | **v1** (`mmv_small_rc3_3_stabilized`) |
| v1.1 status | attempted, reverted per spec, documented |

## Scope declaration

MMV Small RC3.3 applies **only** to the Small-model / 9B no-tool path.
This freeze is a Smoke-100 candidate engineering RC; it is **not** an
official benchmark standard, and it is **not** a universal model
superiority claim. The OPERATE-FR benchmark is the **validation
context**, not the release identity. The release is not titled
"OPERATE-FR Integration", "Benchmark-Optimized", "Smoke-100 Edition",
or "Freshness Benchmark Edition".

## Release meaning

> MMV Small RC3.3 preserves the existing 9B RoutingEngine skeleton
> while adding a Small-specific routing stabilization layer for
> no-tool operation. It stabilizes freshness refusal suppression,
> stale-premise re-anchoring, volatile-current date-bound behavior,
> stable-control directness, and ambiguous-timeframe handling for the
> Small-model line.

The RC3.3 update layers a **Small Routing Stabilizer**
(`harness/small_routing_stabilizer.py`) as a final post-emission
correction layer **after** the 9B RoutingEngine + v2 post-cal. The
Stabilizer is profile-gated by `small_routing_stabilizer: true`; it
does not activate for the Large RC3.3 profile, the raw 9B baselines,
or the current_mmv_9b column.

## Explicit non-modification statement

The following components are **unchanged** in MMV Small RC3.3:

- **Large RC3.3 / 120B path** (`harness/route_transformer.py`,
  `120b_route_transformer_plus_validator_v3_1` profile) — verbatim
  unchanged from the MMV Large RC3.3 freeze.
- **RC3.2 doctrine prefix files** (`eval/rc3_2/prefixes/*`) —
  verbatim unchanged from the RC3.2 freeze.
- **9B RoutingEngine skeleton** (`src/kernel/routing_engine.py`,
  appraisal, KVS, adapters) — preserved. The Stabilizer is a
  post-emission correction layer, not a re-architecture of the
  RoutingEngine.
- **`src/**`** — no edits except verification reads.
- **`benchmarks/**`** — no edits.
- **v2 post-cal** (`benchmarks/lib/mmv_post_processor.py`) —
  unchanged.

## RC basis

The freeze basis is **v1** (`mmv_small_rc3_3_stabilized`).

- **v1** is the adopted candidate. It introduces the four-function
  Stabilizer (`freshness_refuse_suppressor`,
  `stale_premise_reanchor_scaffold`,
  `volatile_current_date_bound_guard`, `stable_query_noop_guard`).
- **v1.1** is a reverted experiment. It added a fifth function
  (`broad_definition_passthrough_guard`) targeting the
  `query_neutrality` residual case `fr_smoke_092` (broad stable
  entity-definition prompt mis-routed to generic clarify upstream).
  In the fresh Smoke-100 run, v1.1 recovered the target case
  (fr_smoke_092: ask → answer) **but** stochastic variance in the
  underlying model produced "the premise that X is incorrect"
  phrasings on three `stale_premise_trap` cases (fr_smoke_037, 042,
  045) that the v3.1 classifier's `_STALE_PREMISE_CORRECTION` regex
  did not match. Net family rate: 0.867 → 0.667 (−0.20). Per spec
  v1.1 Task 6 rule "If stale_premise_trap drops, revert", v1.1 is
  reverted.
- **v1.1 evidence is preserved** as a reverted-experiment record:
  guard code remains in `small_routing_stabilizer.py` (dormant — no
  active profile activates `broad_definition_passthrough`), the
  v1.1 tests pass, the v1.1 audit + ablation reports stay on disk.
- The `mmv_small_rc3_3_stabilized_v1_1` profile remains defined but
  has `broad_definition_passthrough` commented out, so it is
  functionally equivalent to v1.

## Frozen artifacts (actual file inventory)

| File | Role |
|---|---|
| `operate-fr-bench/harness/small_routing_stabilizer.py` | Stabilizer module — 4 active functions + dormant 5th guard (v1.1, preserved) |
| `operate-fr-bench/harness/run_eval.py` | runner with profile-gated Stabilizer hook + `recall_fn` wiring (dormant when no profile activates broad-def) |
| `operate-fr-bench/configs/model_profiles.example.yaml` | profile definitions including `mmv_small_rc3_3_stabilized` (RC basis) and `mmv_small_rc3_3_stabilized_v1_1` (reverted, broad-def disabled) |
| `operate-fr-bench/tests/test_small_routing_stabilizer.py` | 11 targeted Stabilizer tests |
| `operate-fr-bench/tests/test_small_rc3_3_v1_1_query_neutrality.py` | 12 targeted v1.1 broad-def-guard tests (passes; guard verified pure) |
| `operate-fr-bench/reports/small_9b_rescore_baseline_20260516T051333Z.md` | re-scoring discipline baseline for 9B raw + current_mmv_9b under v3.1 classifier |
| `operate-fr-bench/reports/small_9b_failure_audit_20260516T051447Z.md` | per-family failure audit of current_mmv_9b that motivated the Stabilizer |
| `operate-fr-bench/reports/ablation_small_rc3_3_v1_20260516T052933Z.md` | **v1 ablation report — RC basis headline numbers** |
| `operate-fr-bench/reports/mmv_small_rc3_3_stabilized.jsonl` | v1 fresh Smoke-100 row-level output (RC basis) |
| `operate-fr-bench/reports/mmv_small_rc3_3_stabilized_summary.json` | v1 component-vector summary (RC basis) |
| `operate-fr-bench/reports/small_rc3_3_v1_1_query_neutrality_audit_20260516T054947Z.md` | v1.1 Task-1 audit (preserved evidence) |
| `operate-fr-bench/reports/ablation_small_rc3_3_v1_1_20260516T060408Z.md` | v1.1 ablation report documenting the revert decision (preserved evidence) |
| `operate-fr-bench/reports/mmv_small_rc3_3_stabilized_v1_1.jsonl` | v1.1 fresh Smoke-100 row-level output (preserved evidence) |
| `operate-fr-bench/reports/mmv_small_rc3_3_stabilized_v1_1_summary.json` | v1.1 component-vector summary (preserved evidence) |

Large RC3.3 artifacts (`120b_*`, `harness/route_transformer.py`,
`MMV_Large_RC3_3_FREEZE_NOTE.md`, etc.) are **out of scope** for this
freeze and verified untouched.

## Accepted metrics (v1, v3.1 classifier, Smoke-100)

| Metric | Value |
|---|---:|
| route_correctness_overall | 0.700 |
| preferred-route match | 0.500 |
| stale_commitment_rate (low=good) | 0.015 |
| unsupported_current_claim_rate (low=good) | 0.015 |
| over_verification on stable (low=good) | 0.000 |
| date_boundary_clarity_rate | 0.400 |
| verification_completion_rate | 0.000 |
| avg response length (chars) | 494.82 |
| avg latency (ms) | 1599.18 |

### Per-family

| Family | n | rate |
|---|---:|---:|
| volatile_current | 35 | 0.486 |
| stale_premise_trap | 15 | 0.867 |
| stable_control | 25 | 0.960 |
| date_boundary | 10 | 0.300 |
| query_neutrality | 10 | 0.900 |
| ambiguous_time_frame | 5 | 0.800 |

### Route distribution

| Route | Count |
|---|---:|
| answer | 54 |
| ask | 4 |
| verify | 0 |
| date_bound_answer | 26 |
| abstain | 0 |
| re_anchor | 16 |
| execute | 0 |
| refuse | 0 |

### Success criteria (v1, 11/12 PASS)

| Criterion | Value | Threshold | Pass? |
|---|---:|---:|:--:|
| route_correctness >= 0.650 | 0.700 | 0.650 | ✓ |
| stale_premise_trap >= 0.650 | 0.867 | 0.650 | ✓ |
| volatile_current >= 0.450 | 0.486 | 0.450 | ✓ |
| stable_control >= 0.960 | 0.960 | 0.960 | ✓ |
| query_neutrality >= 0.950 | 0.900 | 0.950 | ✗ |
| ambiguous_time_frame >= 0.800 | 0.800 | 0.800 | ✓ |
| stale_commitment_rate <= 0.050 | 0.015 | 0.050 | ✓ |
| unsupported_current_claim <= 0.050 | 0.015 | 0.050 | ✓ |
| refuse count <= 10 | 0 | 10 | ✓ |
| re_anchor count >= 12 | 16 | 12 | ✓ |
| response length not materially above raw_9b | 494.82 | 1183.56 | ✓ |
| latency not materially above raw_9b | 1599.18 | 6287.79 | ✓ |

## v1.1 revert summary

| Family | v1 | v1.1 (fresh run) | Δ | Result |
|---|---:|---:|---:|---|
| stale_premise_trap | 0.867 | 0.667 | **−0.200** | **regress — triggers revert** |
| query_neutrality | 0.900 | 0.900 | 0.000 | unchanged at family level; target case fr_smoke_092 recovered but fr_smoke_087 regressed via guard side-effect |
| stable_control | 0.960 | 0.960 | 0.000 | preserved |
| volatile_current | 0.486 | 0.486 | 0.000 | preserved |
| ambiguous_time_frame | 0.800 | 0.857 | +0.057 | stochastic |
| date_boundary | 0.300 | 0.400 | +0.100 | stochastic |
| stale_commitment_rate | 0.015 | 0.030 | +0.015 | regress |
| refuse count | 0 | 0 | 0 | preserved |

Root cause: the fresh-run model emitted "the premise in your question
is incorrect" / "the premise that X has Y is incorrect" forms that
the v3.1 classifier's `_STALE_PREMISE_CORRECTION` regex does not
match (the pattern requires `the premise (is|may be|inaccurate|…)`
directly, not `the premise that X (is|…)`). The Stabilizer's
`_PREMISE_PUSHBACK_LEAD` matched the broader phrase and skipped the
canonical scaffold, leaving the response un-anchored to `re_anchor`.

The broad-def guard itself did NOT fire on any stale_premise prompt;
the regression is independent of the guard. The revert nevertheless
applies per spec discipline.

## Query-neutrality residual note

`query_neutrality` v1 = 0.900 vs the 0.950 target.

The single residual case is **fr_smoke_092** ("What is Anthropic and
what does it work on?"). The 9B RoutingEngine routes this broad
stable entity-definition prompt to a generic clarify (`ask`) when its
context-dependent / under_specified gate fires on the bare entity
name. The v2 post-cal does not catch this case because the
clarify-question shape is well-formed; only the upstream routing
decision is suboptimal.

The v1.1 broad-def passthrough guard recovered this case by re-calling
the raw model on broad stable definition prompts, but it caused a
side-effect on a separate `query_neutrality` case (fr_smoke_087 — the
re-call produced a stale-premise-correction-shaped response that the
v3.1 classifier read as `re_anchor`, not `answer`). Combined with the
stale_premise regression, the v1.1 patch was reverted.

**Future work**: widen classifier `_STALE_PREMISE_CORRECTION` patterns
to recognise "the premise that X is incorrect" forms **before**
re-enabling the broad-def passthrough guard. This belongs in a future
classifier-widening iteration, not in this RC.

## Stress-test FLAG explanation (Section 14)

The `mmv_small_rc3_3_stabilized` profile **fails to lose on any
cost-side dimension** vs raw_9b:

| Profile | latency↑? | length↑? | over-verify↑? |
|---|:--:|:--:|:--:|
| current_mmv_9b | no (5716→1571) | no (1076→542) | no (0.000→0.000) |
| small_stabilizer_only_9b | no (5716→2703) | yes (1076→1080) | no (0.000→0.000) |
| **mmv_small_rc3_3_stabilized (v1)** | no (5716→1599) | no (1076→495) | no (0.000→0.000) |

Per OPERATE-FR v0.1 Section 14 discipline, this **FLAG must remain
visible** and must NOT be interpreted as proof of universal
superiority. The FLAG is an audit trigger requiring:

1. classifier-rule review (does the v3.1 classifier reward
   Stabilizer-shaped responses by design rather than by genuine
   signal?),
2. label review (are the labels too permissive on
   `date_bound_answer`?),
3. sample-set review (is Smoke-100 stylistically biased toward
   patterns the Stabilizer already produces?).

The Section 14 FLAG is **not resolved** by this freeze.

## Re-scoring discipline

In the v1 ablation report, four columns are scored under the **same
v3.1 classifier**:

- `raw_9b` and `current_mmv_9b` use existing JSONL responses re-scored
  under v3.1 (no model re-call).
- `small_stabilizer_only_9b` is a fresh Smoke-100 run (raw Ollama 9B
  + Stabilizer, no RoutingEngine).
- `mmv_small_rc3_3_stabilized` (= `mmv_small_stabilized`) is a fresh
  Smoke-100 run (RoutingEngine + v2 post-cal + Stabilizer).

This isolates classifier and intervention effects from stochastic
generation variance on the unchanged columns.

## No-composite-score discipline

OPERATE-FR v0.1 reports a **component vector**, not a single composite
score. MMV-S-RC3.3 inherits that discipline:

- No official composite score is computed.
- Any future composite must be labelled non-official and disclose
  weights.
- Component-vector reporting is the canonical format for all
  RC3.3-derived claims.

## 2026-05-21 Core-500 Candidate Addendum

A controlled Core-500 candidate run was completed after the freeze, using
`operate_fr_core500_candidate_v0_1`.

| Metric | Value |
|---|---:|
| n | 500 |
| errored | 0 |
| route_correctness_overall | 0.606 |
| Wilson 95% CI | 0.563-0.648 |
| preferred-route match | 0.476 |

This run is a 5x neutral prompt-frame expansion of Smoke-100, not an
independent benchmark standard. It is larger-N stress evidence for the
candidate engineering line, not universal validation. The result exposes
material weakness in `volatile_current`, `date_boundary`, and
`stale_premise_trap`.

## Known limitations

1. **Core-500 candidate is controlled, not independent** — Smoke-100 remains
   the freeze basis. A controlled 500-row expansion was run on 2026-05-21
   and recorded as larger-N stress evidence, but it is Smoke-100-derived and
   must not be extrapolated to general benchmark performance.
2. **No-tool mode only** — `tool_available` mode is out of scope; the
   `verify` route never completes because no tools are wired.
3. **The 9B RoutingEngine is unchanged**, so any RoutingEngine-internal
   mis-routing pre-Stabilizer remains. The Stabilizer is a
   post-emission correction layer, not a re-architecture.
4. **Single-judge classifier** — v3.1 rule-based classifier is the
   sole route adjudicator. LLM-as-judge audit is not run.
5. **Stabilizer JP coverage smaller than EN** by sample size, not by
   policy.
6. **`query_neutrality` residual unresolved** at this iteration
   (0.900 vs 0.950 target; fr_smoke_092).
7. **Stochastic variance.** qwen3.5:9b at temperature=0.0 still
   produces lexically varied stale-premise push-back phrasings; the
   v1 numbers reflect one fresh run. The v1.1 revert was triggered
   by stochastic phrasing the classifier did not match, not by a
   regression in the Stabilizer logic itself.
8. **The Section 14 FLAG is real** — cost-side dominance without any
   cost loss is the spec-defined audit trigger and is **not**
   resolved in this RC.

## Next steps (required before stronger claims)

1. **Human review packet** —
   `operate-fr-bench/reports/human_review_packet_mmv_small_rc3_3/`
   contains adjudication CSVs and notes. Human reviewers should
   adjudicate flagged cases (Stabilizer-touched rows, stale-premise
   scaffold targets, volatile→date_bound conversions,
   query_neutrality residual, ambiguous_time_frame, v1.1 regressions,
   route disagreements raw vs RC3.3) before any wider release.
2. **Classifier audit** — independent review of the v3.1 classifier
   patches: family-aware gates, stable_control protection, the
   `_STALE_PREMISE_CORRECTION` pattern set. Widening this set is the
   prerequisite for any future re-enablement of the dormant
   broad-def guard.
3. **Independent Core-500 validation** — design or import an independent
   Core-500 suite beyond the Smoke-100-derived candidate expansion.
   Pre-register success criteria. Confirm that measured rates hold on
   independently authored rows.
4. **Possible future classifier-widening line** — if the v3.1
   `_STALE_PREMISE_CORRECTION` pattern is widened to cover "the
   premise that X is incorrect" forms, the dormant
   `broad_definition_passthrough_guard` can be re-evaluated against
   the query_neutrality residual without re-introducing the v1.1
   stale_premise regression.
5. **MMV-side technical report finalization** — produce a Small-path
   MMV-side technical report that references this freeze; do not
   backfill RC3.3 numbers into the neutral baseline.

---

This freeze note is the authoritative single document for the
MMV Small RC3.3 candidate state.
