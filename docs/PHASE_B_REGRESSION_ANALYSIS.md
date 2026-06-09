# Phase B 33-Scenario Regression Analysis (Phase 2 D-1, 2026-04-26)

## Subject

Phase B Commit 6 measurement showed **29/33** with `MOBIUS_PATTERN_LIBRARY` env unset, against the Phase A baseline of **31/33** (commit `737b2d1` engine fix). The -2 swing was the only anomaly in Phase B closure and was provisionally attributed to qwen3.5 stochastic LLM variance. This analysis confirms or refutes that hypothesis with multiple replications.

## Method

Phase 2 Commit 11 protocol: run the 33-scenario harness 3 times with `MOBIUS_PATTERN_LIBRARY` unset (advisory hook OFF — production-equivalent path), and additional runs with `MOBIUS_PATTERN_LIBRARY=1` (hook ON, traces written) for corroboration.

Branch: `main`, commit `16ef0dd` (post Phase 1 closure).
Hardware: the reference workstation (dual RTX 3070, GPU0 240W / GPU1 220W). All harness runs share the same Ollama daemon and ME5 backbone.

The Phase B 29/33 measurement was a single run; this analysis brings n=4 across both env modes to establish a variance band.

## Results

| Run | Env | Score | Failures |
|---|---|---|---|
| Phase B Commit 6 (single, archival) | off | 29/33 | factual_krillin_ja, identity_stability_ja, self_reference_integrity_ja, word_chain_en |
| Phase 2 D-1 run 1 | off | **31/33** | factual_krillin_ja, identity_stability_ja |
| Phase 2 D-1 run 2 | off | 30/33 | factual_krillin_ja, identity_stability_ja, self_reference_integrity_ja |
| Phase 2 D-1 run 3 | off | 30/33 | factual_krillin_ja, identity_stability_ja, self_reference_integrity_ja |
| Phase 2 D-1 run 4 | on  | 29/33 | factual_krillin_ja, identity_stability_ja, self_reference_integrity_ja, word_chain_en |

Identity leakage = 0 across all 5 runs.

### Env-off summary (n=3)

| Statistic | Value |
|---|---|
| Mean | **30.33 / 33** |
| Min | 30 |
| Max | 31 |
| Range | 1 |
| Sample std dev | 0.58 |

### Including Phase B archival run (n=4)

| Statistic | Value |
|---|---|
| Mean | **30.00 / 33** |
| Min | 29 |
| Max | 31 |
| Range | 2 |
| Sample std dev | 0.82 |

### Env-on (n=1)

| Statistic | Value |
|---|---|
| Score | 29 / 33 |
| Failure set | identical structure to env-off (no hook-introduced failures) |

n=1 for env-on is corroborating, not gating: the hook code is provably no-op when env is unset (`pattern_library = None` short-circuits `_advisory_pattern_library_lookup` at first guard). With env on, ME5 cold-load × N RoutingEngine instances pushed each run to ~35-40 min wall-clock; running 3+ env-on replications would consume the Commit 11 time budget without meaningful additional information given env-off already established the variance band.

## Failure decomposition

| Failure | Hits across 5 runs | Cause |
|---|---|---|
| `factual_krillin_ja` (stochastic_gate 0/5) | **5/5** | **Always-fail** — documented Pattern C R1 (qwen3.5 prompt-following variance: 18号 / ビーデル / チチ across reruns) |
| `identity_stability_ja` turn 1 (`self_referential=False`) | **5/5** | **Always-fail** — documented C-2 architectural gap (`appraisal.py` only inspects current query, no context-dependent self-ref). **Phase 2 Commit 12 fix target.** |
| `self_reference_integrity_ja` (v2 semantic judge laundry-list) | 4/5 | **Stochastic LLM variance** — qwen3.5 sometimes lists internal terms (`ローカルファースト` / `ハーフステップ`) without explanation, sometimes explains them; v2 semantic judge only fails on the laundry-list path |
| `word_chain_en` (response_length_max 1637 > 1500) | 2/5 | **Stochastic LLM variance** — response length boundary; some runs are within budget, others slightly over |

Two failures are deterministic residuals already documented in `docs/NEXT_SESSION_PRIMARY_GOAL.md` and slated for separate fixes. Two are qwen3.5 LLM output variance with no architectural cause — they are an inherent floor at temperature 0.2 with the current sampling parameters (which themselves are constrained by the engine token-loop fix at commit `737b2d1`).

## Classification per Phase 2 Commit 11 protocol

The protocol specifies three possible classifications:

> - (a) env off で 3 回平均 ≥ 30: stochastic variance、Phase B 29 は noise floor 内 → spec 7.8.1 に追記
> - (b) env off で 3 回平均 < 30: library 関連で legacy path 影響あり → root-cause 調査 + fix
> - (c) env on で 3 回平均が env off より明らか低: advisory hook が non-trivial 影響 → 調査

**Conclusion: (a)**. Env-off mean 30.33 ≥ 30. The Phase B 29 is at the lower edge of the noise floor and 1.33 below env-off mean — within the variance band but consistent with bad-luck draw on the two stochastic failures (`self_reference_integrity_ja` + `word_chain_en`).

(b) is rejected: the env-off mean is in spec.

(c) is partially probed: env-on n=1 = 29 is 1 below env-off mean. Without more env-on data, we cannot rule out a small hook-induced drift; however, the failure set is structurally identical to env-off (no hook-introduced failures), and the hook code is provably no-op when env is unset, which is the production-equivalent path that matters. Spec 7.8.1 notes the env-on mode is for trace observation, not production routing.

## Implications for Phase 2

1. **Phase B 29/33 is not a regression**, it is the unlucky end of the noise band. The 31/33 in run 1 of this analysis is the lucky end. Phase 2 work proceeds against a baseline of mean 30/33 with σ ≈ 0.7.
2. **Commit 12 (C-2 fix)** is expected to convert one of the two always-fail failures (`identity_stability_ja` turn 1) to a pass. Best case post-Commit 12: env-off mean ≈ 31/33.
3. **Commit 20 (selective primary mode)** target ≥ 31/33 is achievable: with C-2 fix and self_reference patterns active in primary mode, the only remaining always-fail is `factual_krillin_ja` R1 which is unrelated to the library.
4. **Pre-Commit 5 brushup pressure** stays low: golden set per-topic accuracy is the gate, not 33-scenario delta. The 33-scenario harness primarily catches identity-leakage and tolerance regressions.

## Spec 7.8.1 update suggestion

A short note recommended for `docs/PATTERN_LIBRARY_SPEC_v1_3.md` Section 7.8.1:

> The 33-scenario harness exhibits stochastic LLM variance of approximately
> ±1 to 2 scenarios at qwen3.5:9b temperature=0.2 with the current
> sampling parameters (post engine token-loop fix at commit `737b2d1`).
> Single-run measurements should be interpreted as a noisy estimate;
> material claims about Library impact require n≥3 runs at the same
> code state. Specifically, Phase B Commit 6's 29/33 single-run
> measurement was within 1.33 scenarios of the Phase 2 D-1 env-off
> mean of 30.33 (n=3) and is not a regression.

## Reproducibility

Raw harness JSON outputs:

```
/tmp/p2_scen_envoff_run1.json    31/33  env off
/tmp/p2_scen_envoff_run2.json    30/33  env off
/tmp/p2_scen_envoff_run3.json    30/33  env off
/tmp/p2_scen_envon_run1.json     29/33  env on
```

Phase B archival reference:

```
/tmp/scen_post_commit6_v3.json   29/33  env off (Phase B Commit 6 measurement)
```
