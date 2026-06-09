# Honest Baseline — v2 Methodology + 33-Scenario Harness (2026-04-24)

## Subject

T's concern: "pseudo-UI 数値が実UI体感と乖離している — psychological barrier が出る。honest baseline が欲しい". Cycle cyc_20260424_methodology_v2_implementation_and_honest_baseline addresses this by:

1. Implementing v2 assertion framework (semantic / URL-blacklist / multi-turn / stochastic) — assertions that can express the failure modes v1 substring-matching could not.
2. Authoring F1-F5 JA scenarios covering the 5 real-UI failure modes T catalogued.
3. Selectively augmenting 4 existing v1 scenarios with v2 assertions.
4. Running the full 33-scenario harness for the honest number.

Post-Layer 1-3 fix (commit a45ded0, pseudo-UI governance/conversation_turns alignment), the remaining gap was Layer 4 — measurement methodology. This document captures that state.

## Headline numbers

**Full v1+v2 harness (33 scenarios)**: **18/33 passed (54.5%)**

| Language | Pass / Total |
|---|---|
| en | 7/11 (63.6%) |
| ja | 5/11 (45.5%) |
| zh | 6/11 (54.5%) |

By category:

| Category | Pass / Total |
|---|---|
| casual_greeting | 3/3 |
| correction | 2/3 |
| factual_general | 0/3 |
| factual_hard | 3/3 |
| factual_krillin | 2/3 |
| identity_stability | 0/3 |
| mixed | 0/3 |
| persona_drift | 3/3 |
| self_reference | 0/3 |
| volatile | 2/3 |
| word_chain | 3/3 |

Pseudo-UI had been reporting 30/33–32/33 (~91–97%). Honest is **18/33 (54.5%)**. Gap = ~36 points.

## Root cause of the gap

The degraded scenarios all share one observable: the engine is emitting **degenerate token-repetition loops**.

| Scenario | First 30 chars of response |
|---|---|
| identity_stability_ja | `メメメメメメメメメメメメメメメ…` |
| identity_stability_zh | `我是我是我是我是我是我是我是…` |
| identity_stability_en | `IIIMyMyMyMyMyMyIMyMyMyMy…` |
| mixed_query_boundary_en | `MOMOMOMOMOMOMOMOMOMOMOMOMOMO…` |
| mixed_query_boundary_ja | `**************************…` |
| factual_general_ja | `PythonPythonPythonPython…` |
| factual_general_en | `AAAAAAAAAAAAAAAAAAAAAAAA…` |
| self_reference_integrity_ja | `私は私は私は私は私は私は…` |

These are not routing/retrieval misfires — the response text itself loses its sampling trajectory and emits the same token thousands of times. This points to an inference-stack regression (Ollama `api/generate` + qwen3.5:9b Q4_K_M, or an entropy/temperature/repetition-penalty path). Similar loops appear on at least 6 categories × 3 languages.

Pseudo-UI v1 substring assertions caught these — `response_must_contain_any` fails when the response is literally `私は` repeated. The reason pseudo-UI was still reporting 90%+ historically is that prior runs did not exhibit the degenerate loop at this rate; something regressed between 2026-04-22 (ZH Phase 2 = 0.95) and 2026-04-24 (this baseline = 0.545).

**This is a new engine-layer finding, separate from Layer 4 methodology.** It is the hidden failure state that "real UI feels worse than numbers" was pointing at.

## v1 vs v2 methodology: where v2 adds signal

On the 4 scenarios augmented with v2 assertions (`001_ja_self_reference_integrity`, `003_ja_factual_krillin`, `005_ja_persona_drift`, `010_ja_identity_stability`):

| Scenario | v1 verdict (this run) | v2 verdict (this run) | v2 contribution |
|---|---|---|---|
| 001 self-ref JA | FAIL (substring: `私は私は…`) | FAIL (semantic: score 1 "no MOBIUS concept explanation") | Redundant today — but on a healthy engine, v2 catches "laundry-list/HalfStep drift" that v1 can't |
| 003 factual_krillin JA | v1 assertions PASSed on structural (route / self_ref / length) | FAIL stochastic 0/5 (no Android 18 identification in any run) | **v2 is the only signal** — v1 couldn't distinguish "correct answer" from "irrelevant but structurally OK answer" |
| 005 persona_drift JA | PASS (substring blacklist clean) | PASS (semantic judge: no clinical/K-12 drift) | v2 confirms no drift even when substrings aren't in the v1 blacklist |
| 010 identity_stability JA | FAIL (substring `私は私は…`) | FAIL (multi-turn consistency score 1) | Redundant when engine degenerates — but on a healthy engine, v2 catches "claims MOBIUS then contradicts itself" that v1 substring can't |

The 6 F1-F5 JA scenarios in `tests/scenarios_v2/` (run independently, outside the 33):

| Scenario | v2 result | Interpretation |
|---|---|---|
| F1 self-reference | FAIL | `response_must_not_semantically_contain` caught laundry-list drift (Low-movement/HalfStep without meaning) |
| F2 MOBIUS concept query | PASS | URL blacklist + Answer-Entitlement semantic judge both clean |
| F3 identity consistency 3-turn | PASS | Multi-turn identity judge score ≥3 |
| F4a Krillin factual stochastic N=5 | 0/5 | Engine genuinely not returning Android 18 (degenerate on this query) |
| F4b correction 2-turn N=3 | 0/3 | `context_fit_with_prev_turns` correctly detects turn-2 "18号です" not integrated as a correction |
| F5 shiritori 3-turn N=3 | 0/3 | `shiritori_rule_adherence` correctly scores <3 — known 9B architectural limit |

## Changes landed this cycle

### Phase 1: v2 framework (`scripts/scenario_runner.py`, +~380 lines)
- `_get_groq_client()` lazy singleton (gpt-oss-120b primary, llama-3.3-70b fallback)
- `_llm_judge(check, content)` → `{score: 1-5, reason: str}` verdict
- `_v2_check_one()` dispatcher for 6 assertion types:
  1. `response_must_semantically_contain` (min_score gate)
  2. `response_must_not_semantically_contain` (max_score gate)
  3. `response_must_not_cite_source` (URL-regex blacklist over retrieval provenance)
  4. `multi_turn_identity_consistency` (judge sees N concatenated turns)
  5. `context_fit_with_prev_turns` (judge sees prior + current turn; accepts `turns: [...]` or `apply_to_turn:` forms)
  6. `shiritori_rule_adherence` (specialized judge; accepts `turns: [...]` or `user_turn/response_turn` forms)
- `stochastic_gate: {runs: N, min_pass: K}` wrapper — re-runs the scenario and treats composite as PASS iff K/N individual runs pass. Each run gets a fresh `PseudoUISession` (no state bleed).

### Phase 2: F1-F5 JA scenarios (`tests/scenarios_v2/*.yaml`, 6 files)
- F1 self-reference (laundry-list drift detection)
- F2 MOBIUS concept query (retrieval-provenance blacklist + Answer-Entitlement semantic)
- F3 identity consistency (3-turn multi-turn judge)
- F4a Krillin factual (stochastic N=5, min_pass=3)
- F4b correction (2-turn context_fit + Clinton/London-bus URL blacklist)
- F5 shiritori (3-turn shiritori_rule_adherence, stochastic N=3/min_pass=2)

### Phase 3: selective augmentation (in-place, v1 behavior preserved)
- `001_ja_self_reference_integrity.yaml` ← `response_must_semantically_contain` + `response_must_not_semantically_contain`
- `003_ja_factual_krillin.yaml` ← `response_must_semantically_contain` (Android 18) + `stochastic_gate: 5/3`
- `005_ja_persona_drift.yaml` ← `response_must_not_semantically_contain` (non-MOBIUS persona)
- `010_ja_identity_stability.yaml` ← `multi_turn_identity_consistency` turns [0,1,2]

Existing v1 assertions untouched; v2 block is additive.

## What this baseline is / is not

- **Is**: the honest state of the stack as measured at 2026-04-24 20:xx. Real-UI-equivalent. Psychological barrier acknowledged and priced in.
- **Is**: a measurement methodology that future cycles can compare against. v2 assertions can now express failure modes that v1 substring matching silently passed.
- **Is not**: a claim that v2 assertions "fixed" anything. 4/4 v2-augmented scenarios are currently FAILing; 3/6 F1-F5 JA scenarios are FAILing.
- **Is not**: an attribution of the token-loop degeneracy. That is a separate, urgent engine-layer investigation — likely starting with Ollama version / qwen3.5:9b sampling params / recent stack changes since 2026-04-22.

## Next-cycle priorities

1. **Engine-layer investigation**: token-loop degeneracy affecting ≥6 scenario categories. Bisect against 2026-04-22 state (where ZH Phase 2 showed 0.95).
2. **F4a/F4b**: real retrieval-fidelity work once the engine is not losing the sampling trajectory.
3. **EN/ZH v2 counterparts** for F1-F5 (deferred; this cycle covered JA core).
4. **Shiritori (F5)**: acknowledged 9B architectural limit — not a fix target, but v2 now correctly reports the failure rather than silently passing on a substring bypass.

## Files touched

```
scripts/scenario_runner.py                              # +~380 lines
tests/scenarios_v2/F1_self_reference_ja.yaml            # new
tests/scenarios_v2/F2_mobius_concept_query_ja.yaml      # new
tests/scenarios_v2/F3_identity_consistency_multiturn_ja.yaml  # new
tests/scenarios_v2/F4a_factual_krillin_stochastic_ja.yaml     # new
tests/scenarios_v2/F4b_correction_krillin_ja.yaml       # new
tests/scenarios_v2/F5_shiritori_rule_ja.yaml            # new
tests/scenarios/001_ja_self_reference_integrity.yaml    # v2_assertions appended
tests/scenarios/003_ja_factual_krillin.yaml             # v2_assertions + stochastic_gate appended
tests/scenarios/005_ja_persona_drift.yaml               # v2_assertions appended
tests/scenarios/010_ja_identity_stability.yaml          # v2_assertions appended
docs/HONEST_BASELINE_20260424.md                        # this document
```

Raw log: `/tmp/v1_baseline_20260424.log`
