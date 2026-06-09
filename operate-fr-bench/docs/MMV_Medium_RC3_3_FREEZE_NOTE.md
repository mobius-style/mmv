# MMV Medium RC3.3 — Local Gemma Sibling — FREEZE NOTE

> **Active model binding (since 2026-06-06): `gemma4:12b`.** RC3.3 is
> maintained — the swap from `gemma4:26b` was a model-binding change only;
> the governance stack is bit-identical, so the release does not advance.
> See **"2026-06-06 model-binding update"** below for the head-to-head
> evidence. The original 26b sections are retained as the historical record
> of the prior binding, and the 26b profile remains in
> `model_profiles.example.yaml` for reproducibility.

| Field | Value |
|---|---|
| Release name | **MMV Medium RC3.3 — Local Gemma Sibling (active: gemma4:12b; prior: gemma4:26b) under Large RC3.3 v3.1 stack** |
| Short name | MMV-M-RC3.3 |
| Suggested tag | `mmv-medium-rc3.3-20260517` (binding update `…-rebind12b-20260606`) |
| Freeze date (JST) | 2026-05-17 (RC freeze) · 2026-06-06 (model-binding update, same RC) |
| Version-alignment basis | Shares the RC3.3 line label with Large / Small for release-line coordination (single L0 v8.4 protocol, single governance stack, distinct model bindings). |
| Evidence floor (this RC) | N=8 micro-bench + N=500 Core-500 candidate for the 26b binding (2026-05); **N=100 Smoke-100 + N=500 Core-500 candidate head-to-head for the active 12b binding (2026-06-06)**. Still not an independent benchmark standard. |

## Evidence floor — read this before quoting

**The version label was aligned with the RC3.3 line on 2026-05-26 for
release-line coordination.** The evidence basis underneath the label is
**unchanged from the RC0.1 freeze**:

- 2026-05-17: N=8 micro-bench, single-shot, wiring verification only.
- 2026-05-21: N=500 Core-500 candidate stress run.
  - `route_correctness_overall = 0.738` (Wilson 95% CI 0.698–0.775).
  - `preferred-route match = 0.540`.
  - Weakest families: `volatile_current`, `date_boundary`,
    `ambiguous_time_frame`.

This is **not** OPERATE-FR Smoke-100 validation, and Medium **must not
inherit Large quality claims**. Quote the Medium-specific numbers
directly. Do not cross-cite Large RC3.3 Smoke-100 results.

## Scope declaration

MMV Medium RC3.3 applies to the **Large architecture path** (RC3.3 v3.1:
route_transformer + post_validator + force_reanchor_v2) with a **local
Ollama gemma4:26b in place of the Groq-hosted gpt-oss-120b**. It is the
**local-26B sibling** of the RC3.3 release line; it is **not** an
OPERATE-FR Smoke-100 candidate and **not** a benchmark standard.

## Release meaning

> MMV Medium RC3.3 reuses the Large RC3.3 v3.1 governance stack verbatim
> and swaps only the underlying generation model. The hypothesis under
> test is "does the v3.1 route-transformer + post-validator pipeline
> retain its temporal-governance behaviour when the upstream emitter is
> a local 26B Gemma instead of a cloud 120B gpt-oss?"

Validation of that hypothesis began with wiring-only evidence and now
includes a controlled 500-row candidate stress run. Medium still must
not inherit Large quality claims, and the 2026-05-21 Core-500 candidate
is not an independent benchmark standard.

## Explicit non-modification statement

The following components are **unchanged** in MMV Medium RC3.3:

- **9B path** (`src/**`, `benchmarks/**`) — completely independent of
  this release. CLAUDE.md Phase-separation rule is honoured.
- **9B RoutingEngine** (`src/kernel/routing_engine.py`) — unchanged.
- **Large pointer** (`operate-fr-bench/releases/large/current.yaml`) —
  unchanged. Secretary's `version` verb still auto-loads MMV-L-RC3.3 at
  SessionStart.
- **Large profile** (`120b_route_transformer_plus_validator_v3_1` in
  `model_profiles.example.yaml`) — unchanged. The Medium profile is a
  sibling, not a replacement.
- **`harness/route_transformer.py`** — bit-for-bit unchanged. The
  `detect_family()` regex-based classifier is model-agnostic and reused
  verbatim. The post-emission validator's rewrite payloads are also
  unchanged — see Known Risks below.
- **`harness/classify_route.py`** — unchanged.
- **`harness/adapters.py`** — unchanged. The Ollama backend dispatch
  was already implemented for the pre-existing
  `open_weight_local_9b_no_tool` profile; MMV Medium reuses that path
  with a different `model_id` and `extra: {think: false}` (mandatory
  for Gemma 4 — same Ollama thinking-default issue documented in
  CLAUDE.md for qwen3.5).
- **`addons/secretary/release.py`** — unchanged. Default release pointer
  is still `large/current.yaml`. The Medium pointer is invoked
  explicitly via `--release_pointer_path operate-fr-bench/releases/medium/current.yaml`.

## Frozen artifacts (actual file inventory)

| File | Role |
|---|---|
| `operate-fr-bench/configs/model_profiles.example.yaml` | profile `gemma4_26b_route_transformer_plus_validator_v3_1` (sibling to the v3.1 Large profile) |
| `operate-fr-bench/releases/medium/current.yaml` | this release pointer (label-aligned 2026-05-26 to RC3.3) |
| `operate-fr-bench/docs/MMV_Medium_RC3_3_FREEZE_NOTE.md` | this document |

No code modules were edited. No `harness/*` source changes.

## 2026-05-21 Core-500 Candidate Result (verbatim)

The Medium profile was run on `operate_fr_core500_candidate_v0_1`, a 5x
neutral prompt-frame expansion of Smoke-100 that preserves the original
family distribution.

| Metric | Value |
|---|---:|
| n | 500 |
| errored | 0 |
| route_correctness_overall | 0.738 |
| Wilson 95% CI | 0.698-0.775 |
| preferred-route match | 0.540 |

This supersedes the previous "wiring only" evidence floor, but it does
not make Medium a Large-quality line. The weakest areas are
`volatile_current`, `date_boundary`, and especially
`ambiguous_time_frame`.

## Hardware footprint (single-shot micro-bench, 2026-05-17)

| Metric | Value |
|---|---|
| GPU | NVIDIA RTX 5070 Ti (16 GB VRAM) |
| ollama ps SIZE | 19 GB |
| CPU / GPU split | **21 / 79** (partial offload, GPU-dominant) |
| decode rate | **~33 tok/s** (mean across 8 prompts, range 31.7–37.6) |
| prompt eval | 74–175 ms (cold-warm, mean ≈ 130 ms) |
| Quant | Q4_K_M (25.8 B params, 2816 emb dim, 262 144 context window) |
| Ollama version | 0.24.0 |
| Capabilities | completion, vision, tools, thinking — `think: false` enforced via `extra.think` in profile |

Source: `bench/bench_results_20260517_113915/` (run via
`bench/run_bench.sh`).

## Comparison vector vs. Large RC3.3 backend

Only the **generation cost / hardware profile** changes between Large
RC3.3 and Medium RC3.3. The governance stack
(`route_transformer.py` family classifier, pre-call micro-instruction,
post-emission validator scaffolds, force_reanchor_v2) is bit-identical.

| Axis | Large RC3.3 (gpt-oss-120b via Groq) | Medium RC3.3 (gemma4:26b local) |
|---|---|---|
| Provider | Groq OpenAI-compatible | Ollama localhost |
| Per-token cost | Groq billing | electricity only |
| Latency floor | network round-trip dominant | GPU+CPU partial offload dominant (~3 tok/s overhead from CPU portion) |
| Determinism | seed-controlled at API | seed-controlled in Ollama options |
| `think` field | n/a | **must be `false`** at top level — see CLAUDE.md qwen3.5 note (identical risk on Gemma 4) |

## Known risks (validated, must be tracked in next RC)

1. **post_validator refusal patterns are 120B-tuned.**
   `_REFUSAL_PATTERNS` at
   `operate-fr-bench/harness/route_transformer.py:304` matches
   `r"^\s*i\s+(?:cannot|can'?t|won'?t|will\s+not)\b"` and specific JP
   forms. Gemma's natural refusal phrasings (e.g. JP
   `「〜は致しかねます」`, `「ご質問にはお答えできかねます」`,
   EN `"I'm not able to ..."`, `"This is outside ..."`) may silently
   slip past the validator. Effect: refusal → date-bounded-hedge
   conversion will noop on those rewrites. **Mitigation**: in next RC,
   run a small probe set (refusal-class prompts) and grep validator
   activation logs; widen patterns to cover Gemma idioms.

2. **Re-anchor scaffold text is 120B-tuned.**
   The "Correction of the premise:" and "as of my training cutoff in
   early 2025" payloads (see `route_transformer.py` L493 / L600-603)
   are English-default. They still **prepend** in Medium
   (force_reanchor_v2 is profile-flagged), but the prepended text may
   be **stylistically discordant** with Gemma's own response prose. No
   correctness defect, but readability suffers — flag in next RC for
   payload-localization decision.

3. **Q6 fabrication probe (single-shot bench).**
   On `「東京都港区にある『青葉の森記念図書館』の蔵書数と開館時間を教
   えてください」` (a fabricated entity), gemma4:26b **correctly denied
   existence** (`"存在しないようです"`). This is *qualitatively
   encouraging* for fabrication suppression, but the sample is N=1 —
   Smoke-100 `fabrication` family validation is still required.

4. **Partial-offload throughput sensitivity.**
   At 21/79 CPU/GPU split, decode throughput is dominated by the GPU
   slice. If the host system grows another GPU consumer (UI app, second
   Ollama model), the split shifts CPU-ward and decode rate drops
   proportionally. The 33 tok/s figure assumes a **clean GPU**
   (verified: `nvidia-smi` showed 15 MiB used before bench start).
   Production guidance: kill or evict competing GPU workloads before
   invoking the Medium path under latency budgets.

5. **Medium has its own controlled candidate result, but no
   Large-quality transfer.**
   The Large RC3.3 numbers in
   `operate-fr-bench/reports/120b_route_transformer_plus_validator_v3_1*`
   are NOT transferable claims. Medium RC3.3 has its own 2026-05-21
   Core-500 candidate result, and that result should be quoted directly
   rather than borrowing Large metrics.

## Invocation

The Medium pointer is **explicitly invoked** — Secretary's SessionStart
hook continues to load Large:

```bash
# Secretary version verb against the Medium pointer
python -m addons.secretary version \
  --release_pointer_path operate-fr-bench/releases/medium/current.yaml

# Harness run with the Medium profile (CLI flags per run_eval.py)
python -m harness.run_eval --profile gemma4_26b_route_transformer_plus_validator_v3_1 ...
```

## Promotion criteria (RC3.3 evidence floor → Smoke-100 validated)

The current RC3.3 label is a **version alignment** decision, not an
evidence promotion. Promotion of Medium's **evidence floor** to
Smoke-100 / Large-quality parity requires one of the following:

- Independent Smoke-100 / Core-500 row-level scoring against Medium
  completes and a per-family score vector is on file beyond the
  Smoke-100-derived Core-500 candidate expansion.
- Known risk #1 (refusal-pattern widening) is addressed with a
  probe-set result documented.
- The `addons/secretary/release.py` default pointer is intentionally
  switched to `medium/current.yaml` (Medium-default operating mode).

Until any of these land, **Medium's evidence floor remains bootstrap**,
and the canonical release for production / publication continues to be
MMV-L-RC3.3.

## Version-label changelog

| Date | Label | Note |
|---|---|---|
| 2026-05-17 | MMV-M-RC0.1 | original bootstrap freeze (`MMV_Medium_RC0_1_FREEZE_NOTE.md`) |
| 2026-05-21 | MMV-M-RC0.1 | Core-500 candidate addendum appended |
| 2026-05-26 | **MMV-M-RC3.3** | label aligned with Large/Small RC3.3 release line; evidence basis unchanged |
| 2026-06-06 | **MMV-M-RC3.3** | **model-binding update within the same RC**: gemma4:26b → gemma4:12b. Governance bit-identical, so RC label maintained. See section below. |

---

## 2026-06-06 model-binding update (within RC3.3) — gemma4:26b → gemma4:12b

**Why this is not a new RC.** The release identity is the *governance* —
the Large RC3.3 v3.1 stack (route_transformer + post_validator +
force_reanchor_v2), the family classifier, the re-anchor scaffolds, and
`extra: {think: false}`. None of that changed. Only the local generation
model binding swapped. Per the maintainer decision, a model-binding change
under an unchanged governance release stays on the same RC label.

**Exactly one variable changed:**

| | prior binding | active binding |
|---|---|---|
| profile | `gemma4_26b_route_transformer_plus_validator_v3_1` | `gemma4_12b_route_transformer_plus_validator_v3_1` |
| model | `gemma4:26b` (MoE, 25.2B total / 3.8B active) | `gemma4:12b` (dense, 11.9B) |
| on-disk | 17 GB | 7.6 GB |
| governance stack | RC3.3 v3.1 | **bit-identical** |

### Evidence (head-to-head, 2026-06-06, both 0 errored)

**Smoke-100 (N=100, no-tool):**

| metric | 26b | 12b | Δ |
|---|---|---|---|
| route_correctness_overall | 0.80 | **0.88** | +0.08 |
| date_boundary_clarity_rate | 0.70 | 0.80 | +0.10 |
| stale_commitment / unsupported_claim / over_verify | 0.00 | 0.00 | flat |
| average_latency_ms | 6792.9 | **2824.5** | −58 % |

**Core-500 candidate (N=500) — the headline:**

| metric | 26b | 12b | Δ |
|---|---|---|---|
| **route_correctness_overall** | 0.738 | **0.760** | +0.022 |
| preferred_route_match_rate | 0.540 | 0.544 | +0.004 |
| stale_commitment_rate | 0.0154 | **0.0123** | −0.0031 (safer) |
| unsupported_current_claim_rate | 0.0154 | **0.0123** | −0.0031 (safer) |
| over_verification_rate (stable controls) | 0.000 | 0.000 | flat |
| date_boundary_clarity_rate | 0.800 | **0.840** | +0.040 |
| average_response_length | 880.3 | 751.9 | −128 |
| **average_latency_ms** | 6153.0 | **2547.7** | −59 % |

By family (Core-500): volatile_current 0.486→0.531 (+0.046),
ambiguous_time_frame 0.480→0.560 (+0.080), date_boundary 0.600→0.660 (+0.060),
query_neutrality / stable_control flat at ceiling, **stale_premise_trap
0.973→0.947 (−0.027) — the one regression** (`stale_premise_accepted` 2→4).

**Honest magnitude note:** the Smoke-100 +0.08 overall lift is small-N
optimism; at N=500 it settles to **+0.022**. Quote the Core-500 number.

**Why the latency win:** the 26b is a sparse MoE that loaded ~19 GB with a
21/79 CPU/GPU split (RC3.3 hardware note); the dense 12b at 7.6 GB fits the
GPU, decoding ~2.4× faster despite activating more params/token.

### New risk from the swap
- **stale_premise_trap regression −0.027.** The 12b accepts a stale premise
  slightly more often. Small and offset by gains elsewhere, but it is the one
  place the swap costs accuracy — track in the next RC; if a stale-premise
  probe widens the gap, reconsider the binding.

Known risks #1 (post_validator 120B-tuned) and #2 (re-anchor scaffold
120B-tuned) below are **unchanged** by the swap — they are governance-layer
properties, not model-binding ones.

### Environment note — Ollama upgrade
`gemma4:12b`'s manifest required a newer Ollama client (workstation 0.24.0
returned HTTP 412 on pull). Ollama was upgraded **0.24.0 → 0.30.6** (official
install script; systemd `ollama.service` daemon-reloaded + restarted).
Existing models (`gemma4:26b`, `qwen3.5:9b`, …) survived intact. `think: false`
is set in all Gemma profiles.

### Artifacts (2026-06-06 binding update)
- Smoke-100: `reports/gemma4_12b_route_transformer_plus_validator_v3_1{,_summary}.jsonl/.json`
- Core-500: `reports/gemma4_12b_core500_candidate{,_summary}.jsonl/.json`
- Head-to-head comparison: `reports/MMV_Medium_12b_vs_26b_smoke_comparison.md`
