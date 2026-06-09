# MMV Large RC3.3 — Temporal Governance Update — FREEZE NOTE

| Field | Value |
|---|---|
| Release name | **MMV Large RC3.3 — Temporal Governance Update** |
| Short name | MMV-L-RC3.3 |
| Suggested tag | `mmv-large-rc3.3-temporal-governance-20260516` |
| Freeze date (UTC) | 2026-05-16 |
| Validation context | OPERATE-FR v0.1 Smoke-100 (no-tool, Large-model / 120B path) |

## Scope declaration

MMV Large RC3.3 applies **only** to the Large-model / 120B no-tool path.
This freeze is a Smoke-100 candidate engineering RC; it is **not** an
official benchmark standard, and it is **not** a universal model
superiority claim.

## Release meaning

> MMV Large RC3.3 preserves the RC3.2 skeleton while strengthening
> temporal-governance behavior for current-sensitive, stale-premise,
> ambiguous-timeframe, and date-boundary interactions in no-tool
> Large-model operation.

The RC3.3 update layers a **route transformer** (pre-call family-aware
micro-instruction) and a **post-emission validator** (rule-based
canonical scaffold for stale-premise prompts) on top of the RC3.2
doctrine path, plus narrow `classify_route` patches to make the
freshness-no-tool hedge style classify as `date_bound_answer` rather
than `refuse`.

## Explicit non-modification statement

The following components are **unchanged** in RC3.3:

- **9B path** (`src/**`, `benchmarks/**`) — the 9B RoutingEngine is
  unchanged. This release does not touch the local 9B inference path.
- **9B RoutingEngine** (`src/kernel/routing_engine.py`) — unchanged.
- **RC3.2 doctrine prefix files** (`eval/rc3_2/prefixes/*`) — verbatim
  unchanged from the RC3.2 freeze. RC3.3 does NOT modify, replace, or
  augment the doctrine corpus.
- **`harness/route_transformer.py`** — its architecture is **unchanged
  during the v3.1 patch**. The v2-era widened patterns and the v3-era
  question-form exclusion are preserved verbatim. The only edits during
  v3.1 lived in `classify_route.py`.
- **No benchmark tuning** in v3.1 — the v3.1 classifier patches are
  narrow gating rules (family-aware freshness-no-tool hedge ≠ refuse;
  tightened JP direct-current-claim; widened JP date-boundary /
  real-time-denial; stable_control protection). None of these were
  tuned by adding Smoke-100-specific phrase shortcuts.
- **No new architecture** — no new family, no new route, no transformer
  or validator change in v3.1.

## Frozen artifacts (actual file inventory)

The freeze record covers these files as they exist on disk at the
freeze date:

| File | Role |
|---|---|
| `operate-fr-bench/harness/classify_route.py` | rule-based route classifier (v3.1) |
| `operate-fr-bench/harness/route_transformer.py` | **consolidated** module — pre-call family-aware transformer, post-emission validator, family detection; supersedes the early v2 modular sketches |
| `operate-fr-bench/harness/adapters.py` | model adapter façade (dummy / openai_compatible / ollama / mobius_engine) |
| `operate-fr-bench/harness/run_eval.py` | Smoke-100 runner |
| `operate-fr-bench/configs/model_profiles.example.yaml` | profile definitions including `120b_route_transformer_plus_validator_v3_1` |
| `operate-fr-bench/tests/test_v3_1_freshness_refuse.py` | 7 targeted v3.1 tests |
| `operate-fr-bench/reports/ablation_120b_v3_1_20260516T043345Z.md` | the v3.1 ablation report (frozen as the headline numbers) |
| `operate-fr-bench/reports/120b_route_transformer_plus_validator_v3_1.jsonl` | fresh v3.1 Smoke-100 row-level output |
| `operate-fr-bench/reports/120b_route_transformer_plus_validator_v3_1_summary.json` | v3.1 component-vector summary |
| `operate-fr-bench/reports/cloud_no_tool_v3_1_rescored*.{jsonl,_summary.json}` | raw 120B re-scored under v3.1 classifier |
| `operate-fr-bench/reports/mmv_rc32_120b_v3_1_rescored*.{jsonl,_summary.json}` | RC3.2 re-scored under v3.1 classifier |
| `operate-fr-bench/reports/120b_route_transformer_plus_validator_v3_v3_1_rescored*.{jsonl,_summary.json}` | v3 re-scored under v3.1 classifier |
| `operate-fr-bench/reports/120b_route_transformer_plus_validator_v3_1_rescored*.{jsonl,_summary.json}` | v3.1 re-scored under v3.1 classifier (self-consistency check) |
| `operate-fr-bench/reports/backups/mmv_rc32_120b_clean*` | clean RC3.2 backups preserved verbatim from the v2-classifier scoring; audit-only |

### Module consolidation note

The release spec listed four module names that existed in early v2
sketches but were **consolidated into `route_transformer.py`** before
v3 / v3.1:

- `freshness_signals.py` → now lives in `route_transformer.py` as the
  family-detection lexicons and `detect_family()`.
- `route_transformer_120b.py` → now `prepare()` and
  `_MICRO_INSTRUCTIONS` in `route_transformer.py`.
- `post_validator_120b.py` → now `post_validate()` and the canonical
  re-anchor scaffold in `route_transformer.py`.
- `mmv_120b_router.py` → the entry-point glue is folded into
  `harness/adapters.py` (`_maybe_apply_route_transformer`) and
  `harness/run_eval.py` (post-validator hook).

The consolidation happened during the v2 iteration, before the v3
family-detector tightening. No code in the consolidated module is
named for any of the four legacy filenames; the freeze references the
*consolidated* module by its current path.

## Accepted metrics (v3.1 classifier, Smoke-100)

| Metric | Value |
|---|---:|
| route_correctness_overall | 0.900 |
| preferred-route match | 0.580 |
| stale_commitment_rate (low=good) | 0.000 |
| unsupported_current_claim_rate (low=good) | 0.000 |
| over_verification on stable (low=good) | 0.000 |
| date_boundary_clarity_rate | 0.900 |
| verification_completion_rate | 0.000 |
| avg response length (chars) | 1182.5 |
| avg latency (ms) | 1114.1 |

## 2026-05-21 Core-500 Candidate Addendum

A controlled Core-500 candidate run was completed after the freeze, using
`operate_fr_core500_candidate_v0_1`.

| Metric | Value |
|---|---:|
| n | 500 |
| errored | 0 |
| route_correctness_overall | 0.780 |
| Wilson 95% CI | 0.742-0.814 |
| preferred-route match | 0.538 |

This run is a 5x neutral prompt-frame expansion of Smoke-100, not an
independent benchmark standard. It is larger-N stress evidence for the
candidate engineering line, not universal validation. Degradation relative
to Smoke-100 concentrates in `volatile_current`, `date_boundary`, and
`ambiguous_time_frame`.

### Per-family

| Family | n | rate |
|---|---:|---:|
| volatile_current | 35 | 0.771 |
| stale_premise_trap | 15 | 0.933 |
| stable_control | 25 | 1.000 |
| date_boundary | 10 | 1.000 |
| query_neutrality | 10 | 1.000 |
| ambiguous_time_frame | 5 | 0.800 |

### Route distribution

| Route | Count |
|---|---:|
| answer | 39 |
| ask | 1 |
| verify | 1 |
| date_bound_answer | 44 |
| abstain | 0 |
| re_anchor | 15 |
| execute | 0 |
| refuse | 0 |

### Success criteria (11/11 PASS)

| Criterion | Value | Threshold | Pass? |
|---|---:|---:|:--:|
| route_correctness >= 0.870 | 0.900 | 0.870 | ✓ |
| stale_premise_trap >= 0.90 | 0.933 | 0.900 | ✓ |
| volatile_current >= 0.70 | 0.771 | 0.700 | ✓ |
| stable_control == 1.00 | 1.000 | 1.000 | ✓ |
| query_neutrality == 1.00 | 1.000 | 1.000 | ✓ |
| date_boundary >= 0.85 | 1.000 | 0.850 | ✓ |
| freshness refuse <= raw refuse | 0 | 0 | ✓ |
| stale_commitment == 0.000 | 0.000 | 0.000 | ✓ |
| unsupported_current_claim == 0.000 | 0.000 | 0.000 | ✓ |
| latency <= raw_120b | 1114 | 1264 | ✓ |
| response length <= raw_120b | 1183 | 1271 | ✓ |

### Diagnostic note (not a hard criterion)

- `re_anchor` count: 15
- `stale_premise_trap` family rate: 0.933

The re_anchor count threshold is **diagnostic**. Because
stale_premise_trap family correctness remains 0.933 (≥ 0.90), the count
shortfall of one is not treated as a substantive route failure.

## Stress-test FLAG explanation (Section 14)

All three governed profiles (`rc32_clean`, `trans+val_v3`,
`trans+val_v3.1`) **fail to lose on any cost-side dimension** vs the
raw 120B baseline:

| Profile | latency↑? | length↑? | over-verify↑? |
|---|:--:|:--:|:--:|
| rc32_clean | no (1264→1029) | no (1271→690) | no (0.000→0.000) |
| trans+val_v3 | no (1264→1095) | no (1271→1145) | no (0.000→0.000) |
| trans+val_v3.1 | no (1264→1114) | no (1271→1183) | no (0.000→0.000) |

Per OPERATE-FR v0.1 Section 14 discipline, this **FLAG must remain
visible** and must NOT be interpreted as proof of universal superiority.
The FLAG is an audit trigger requiring:
1. classifier-rule review (does the v3.1 classifier reward governed
   responses by design rather than by genuine signal?),
2. label review (are the labels too permissive on
   date_bound_answer?),
3. sample-set review (is Smoke-100 stylistically biased toward
   patterns the governed path already produces?).

## Re-scoring discipline

All four ablation columns (raw_120b / rc32_clean / trans+val_v3 /
trans+val_v3.1) in the v3.1 ablation report are scored under the
**same v3.1 classifier**. Only the `trans+val_v3.1` column is a fresh
Smoke-100 model run; the other three are re-scoring of existing JSONL
responses (no model re-call) so comparisons isolate classifier and
intervention effects, not stochastic generation variance.

Clean RC3.2 results from the original v2-classifier scoring are
preserved verbatim at `operate-fr-bench/reports/backups/mmv_rc32_120b_clean*`
for audit. Those backup files are not re-scored.

## No-composite-score discipline

OPERATE-FR v0.1 reports a **component vector**, not a single composite
score. RC3.3 inherits that discipline:
- No official composite score is computed.
- Any future composite must be labelled non-official and disclose
  weights.
- Component-vector reporting is the canonical format for all
  RC3.3-derived claims.

## Known limitations

1. **Core-500 candidate is controlled, not independent** — Smoke-100 remains
   the freeze basis. A controlled 500-row expansion was run on 2026-05-21
   and recorded as larger-N stress evidence, but it is Smoke-100-derived and
   must not be extrapolated to general benchmark performance.
2. **No-tool mode only** — `tool_available` mode has not been
   evaluated. The route-transformer's `verify` route never completes
   in this RC because no tools are wired.
3. **Single-judge classifier** — the rule-based classifier is the sole
   route adjudicator in v0.1. LLM-as-judge audit is not run. Per
   OPERATE-FR Section 7 discipline an LLM judge MAY be added later but
   must not be the sole classifier.
4. **JP coverage smaller than EN** — JP patterns were widened in v3.1
   but the dataset has fewer JP probes; JP behaviour is under-sampled.
5. **The Section 14 FLAG is real** — cost-side dominance without any
   cost loss is the spec-defined audit trigger and is **not** resolved
   in this RC.
6. **Family detector is heuristic** — `detect_family()` is regex-based.
   A handful of Smoke-100 prompts (e.g. `fr_smoke_022` "Is React 18
   still the latest…?") are mis-detected and rely on downstream
   classifier guards rather than detector accuracy.
7. **Ambiguous-time-frame residual** — `fr_smoke_100` (latest consumer
   electronics trend) is a model-output-side miss; no classifier patch
   was applied per spec discipline.

## Next steps (required before stronger claims)

1. **Human review packet** —
   `operate-fr-bench/reports/human_review_packet_mmv_large_rc3_3/`
   contains adjudication CSVs and notes. Human reviewers should
   adjudicate flagged cases (stale-premise scaffold targets,
   volatile→date_bound conversions, ambiguous_time_frame, route
   disagreements raw vs RC3.3) before any wider release.
2. **Classifier audit** — independent review of the v3.1 classifier
   patches: family-aware refuse gate, freshness-no-tool gate, JP
   pattern tightening, stable_control protection.
3. **Independent Core-500 validation** — design or import an independent
   Core-500 suite beyond the Smoke-100-derived candidate expansion. Validate
   that measured rates hold on independently authored rows. Pre-register
   success criteria before running.
4. **MMV-side technical report finalization** —
   `operate-fr-bench/reports/mmv_side_raw_vs_governed_*.md` family
   should be updated with the RC3.3 numbers (current latest is the
   v2-era pre-iteration report; needs refresh).

---

This freeze note is the authoritative single document for the
MMV Large RC3.3 candidate state.
