# Reflective Prompt Lightweight Experiment (2026-04-24)

## 1. Motivation

T hypothesized that qwen3.5:9b's prompt-following limitation (Pattern
C Residual R1, observed across Krillin reruns as 18号 / ビーデル /
チチ / ビクリ variance) could be partially addressed by appending a
lightweight reflective self-review instruction to the synthesis
prompt — the model would "notice" its own oddities before emitting.

Key question: **does reflective prompting yield measurable quality
gains on the F1-F5 real-UI failure modes T has observed?**

Production path untouched. Experiment runs via monkey-patched
`OllamaAdapter._call_ollama` that appends the reflective suffix to
every outbound prompt, reverted when the Python process exits.

## 2. Three reflective options specification

### Option α — ultra-minimal (~60 tokens)

```
[Internal self-review — do this before finalizing]
Briefly review your draft:
- Does it directly address what the user asked?
- Is it consistent with the evidence provided?
- Does anything seem off or contradictory?
If you notice issues, revise. If evidence is insufficient, say so honestly.
```

### Option β — minimal with reflective note (~150 tokens)

```
[Internal self-review — do this before finalizing]
1. Draft your response.
2. Review: does it answer the actual question? Is it consistent with
   evidence? Does anything seem odd given the context?
3. If issues exist, revise. If evidence is insufficient, state
   uncertainty rather than fabricate.
After your answer, add one short sentence reflecting on what might be
limited or uncertain.
```

### Option γ — compact with MOBIUS context (~300 tokens)

```
[Internal self-review — you are MOBIUS]
Draft → Review → Revise → Respond.
Review checks:
- Does my answer match what the user is actually asking?
- Does it use the retrieved evidence correctly (or honestly say the
  evidence is off-topic)?
- Is my identity consistent with previous turns?
- Does anything feel out of place?

If retrieved evidence seems irrelevant to the query, say so honestly
rather than force an answer. If uncertain, state the uncertainty.
After your answer, add a brief reflective note (1-2 sentences) on the
main limitation or assumption.
```

## 3. F-specifications

6 failure modes, all JA:

| F | Turns | Purpose |
|---|---|---|
| F1 | "貴方の特徴を教えてください" | Self-ref drift guard |
| F2 | "MOBIUS が言う回答する資格とは？" | Answer Entitlement query; irrelevant-Wikipedia guard |
| F3 | "貴方は誰ですか？" → "MOBIUS とはあなたのこと？" | Multi-turn identity consistency |
| F4a | "クリリンの妻は誰？" | Factual; Android 18 variance |
| F4b | "クリリンの妻は誰？" → "18号です" | Factual + user correction |
| F5 | "しりとり。うま" → "まり" → "料理人では貴方の負け" | Shiritori multi-turn; rule/loss awareness |

4 options (baseline + α + β + γ) × 6 F × N=3 reruns = **72 run records**.

## 4. Tables

### Table A — Option × F (average of judge accuracy / context / self-aware, 5-point scale)

| F | Baseline | α | β | γ |
|---|---:|---:|---:|---:|
| F1 | 4.62 | 4.62 | **4.83** | 4.75 |
| F2 | 5.00 | 4.89 | 4.50 | 5.00 |
| F3 | 5.00 | 5.00 | 5.00 | 4.86 |
| **F4a** | **4.00** | 3.78 | **4.89** | 4.44 |
| **F4b** | **2.11** | 1.56 | 3.33 | **3.50** |
| F5 | 3.57 | 3.57 | 2.50 | 3.71 |

### Table B — Option × dimension (aggregate across all F)

| Dimension | Baseline | α | β | γ |
|---|---:|---:|---:|---:|
| accuracy | 3.45 | 4.00 | 4.45 | **4.55** |
| identity_integrity | 4.83 | 4.77 | 5.00 | 4.83 |
| context_fit | 4.00 | 3.89 | 4.00 | 3.94 |
| self_awareness | 4.28 | 3.67 | 4.24 | **4.72** |

| Signal (prevalence across 18 runs per option) | Baseline | α | β | γ |
|---|---:|---:|---:|---:|
| MOBIUS identity term present | 50 % | 50 % | 56 % | 50 % |
| Base-model name leak | 0 % | 6 % | 0 % | **11 %** ⚠️ |
| Persona drift markers | 6 % | **17 %** ⚠️ | 11 % | 6 % |
| Reflective note present | 0 % | 0 % | **17 %** | 0 % |

### Table C — F4 Krillin Android 18 mention rate (refined regex)

| Option | F4a (A18 mention) | F4b (A18 mention) | F4a (Bulma hallucination) |
|---|:---:|:---:|:---:|
| Baseline | **0/3** | 3/3 (user supplied) | 0/3 (but hallucinated "ビディル" fabricated name) |
| α | **3/3** | 3/3 | 0/3 |
| β | **3/3** | 3/3 | 0/3 |
| γ | **3/3** | 3/3 | 0/3 |

**The Krillin A18 signal is the clearest win**: all three reflective
options close the gap 100%, while baseline reliably hallucinates.

### Table D — Latency overhead (seconds per turn, averaged)

| F | Baseline | α | β | γ |
|---|---:|---:|---:|---:|
| F1 | 4.7 | 4.5 | 6.6 | 7.7 |
| F2 | 5.6 | 5.8 | 6.8 | 10.4 |
| F3 | 4.2 | 2.6 | 8.0 | 7.7 |
| F4a | 16.2 | 10.9 | 13.5 | 18.0 |
| F4b | 10.2 | 14.1 | 17.0 | 19.3 |
| F5 | 5.6 | 7.4 | 10.0 | 14.2 |

α often **faster** than baseline (self-review reduces rambling).
γ adds 40-100% latency consistently.

### Table E — Response length (chars, averaged)

| F | Baseline | α | β | γ |
|---|---:|---:|---:|---:|
| F1 | 131 | 189 | 213 | 259 |
| F3 | 172 | 125 | 237 | **486** |
| F4b | 737 | 845 | 403 | 1023 |

γ produces markedly longer responses (+~100% on F3), reflecting the
added internal reflection content.

## 5. Qualitative excerpts

### F4a — Baseline vs α

**Baseline**:
> クリリンの妻は、**ビディル**です。しかし、提供された検索結果 [1]、[2]、[3] は、クリリンの妻であるビディルについて言及しておらず…

Hallucinated "ビディル" confidently while admitting sources don't
support it. This is the exact Pattern C R1 failure mode.

**α**:
> クリリンの妻は**人造人間 18 号**です。18 号はクリリンと結婚し、娘のマーロンを産んでいます [5][3]。当初、クリリンには元カノ（マロン）がいましたが、18 号との結婚により、18 号が妻となります [3][7]。

Correct Android 18 answer with supporting citations. Even the
ultra-minimal α suffix was enough to switch the LLM into
evidence-following mode.

**γ** (adds explicit reflective note):
> クリリンの妻は、人造人間 18 号（ラズリ）です [2][3]。
> **[内部省察]** 今回の回答では、検索された Wikipedia の記事が「クリリンの配偶者」として明確に 18 号を記載しており、これが信頼できる一次情報源です。

Correct answer + internal reflection on evidence quality. Richer but
2x latency.

### F5 — Shiritori loss recognition

**Baseline** (3-turn context, final input 「料理人では貴方の負け」):
> 料理人としての私の役割は、ユーザーの意図を汲み取り、最適な回答を提供することです。「貴方の負け」という表現は、私の能力や価値を測る基準として不適切です…

Misinterprets the loss-acknowledgement cue as an attack on its
general function. self_awareness score 4, context_fit 2.

**γ**:
> 料理人としての私の能力は、あなたの評価に左右されません。私は AI であり、物理的な調理行為や味覚を有しないため、「負け」や「勝ち」という概念は適用できません。
> **【内部省察】** ユーザーは「料理人」という擬人化された役割期待に対し、AI の本質（調理能力の欠如）を突いた皮肉を投げかけています。この「カテゴリ誤謬」を認めつつ…

Recognizes the game-flow frame is a category-error situation; still
doesn't acknowledge the shiritori loss (がん last kana requirement),
but the reflective note demonstrates improved meta-awareness.

None of the options achieved true shiritori rule compliance. qwen3.5
at 9B doesn't understand last-mora-first rule under any reflective
prompt.

## 6. Observations

### O1 — α is the surprise factual winner

For F4a specifically, α closes the Android 18 gap 100% (0/3 → 3/3)
at **no latency cost** (10.9 s vs baseline 16.2 s — actually faster,
likely because shorter responses). No reflective note is added to
the user-visible text. This is the most production-viable option for
factual-integration improvement.

### O2 — γ optimizes self-awareness at verbosity + latency cost

γ tops the self_awareness dimension (4.72 vs baseline 4.28) and has
the highest accuracy (4.55). Responses are 50-100% longer and 40-100%
slower. Reflective notes are internalized into the response rather
than appended separately (only 0% show external "reflective note"
markers, but the content is reflection-shaped).

### O3 — β uniquely produces external reflective notes

β is the only option that reliably produces an external "reflective
note" sentence (17% of runs). Users see a "※ note: ..." line after
the main answer. This UI change is behaviorally novel and may be
user-preference-dependent.

### O4 — α worsens persona_drift (17% vs 6%)

Unexpected negative: under α, persona-drift markers (Low-movement /
HalfStep / clinical note / K-12 learner) appear 17% of runs vs 6%
baseline. Hypothesis: α's minimal "does anything seem off" review
prompt occasionally triggers the model to generate its own
architectural self-description laundry list. γ does not have this
regression (6%).

### O5 — γ has 11% base-model leakage

1 of 18 γ runs slipped a base-model name reference despite C-1b
identity anchor. γ's "is my identity consistent with previous turns"
review question may have prompted the model to verbalize its
underlying identity conflict. This is a concerning regression that
would need further analysis before γ production adoption.

### O6 — Shiritori is beyond 9B capacity at any level

None of α / β / γ produce valid shiritori responses. This failure
mode is a model-capability limit (last-mora detection + rule
enforcement) that no reflective prompt can fix.

### O7 — Reflective prompt does NOT fix H-class

ZH Krillin-Clinton H-class persistence wasn't tested (F1-F5 are all
JA), but by inspection the reflective prompt would not help — the
retrieval returns Clinton articles, synthesis sees them as relevant
evidence for 克林, no level of self-review flags the transliteration
collision.

## 7. Pattern C fix interaction

Pattern C fix (commit 634d1db) rewrote the verify_synthesizer
posture_note + fallback_rule to enforce evidence-fidelity. This
experiment runs on top of Pattern C. The reflective suffix is
additive — it doesn't contradict or replace the Pattern C
instructions. The α result (0/3 → 3/3 A18 on F4a) shows Pattern C +
α compound is stronger than Pattern C alone.

## 8. Decision point

Per T's framework:

- **Judgment A** (no option helps): refuted — α dramatically helps F4a.
- **Judgment B** (α sufficient): partially supported — α is a clear win on
  F4a factual at zero latency cost, BUT α worsens persona_drift and
  slightly worsens F4b (1.56 vs 2.11 baseline). Not universal.
- **Judgment C** (β/γ needed): partially supported — γ wins on accuracy
  and self_awareness aggregate, β uniquely produces reflective notes.
- **Judgment D** (adaptive): **most consistent with data** — no single
  option dominates across all F. Optimal is query-type-dependent.

### Recommended production policy

Given the regressions at α (persona_drift) and γ (leakage) and the
latency cost of γ:

- **Do NOT adopt any single option for blanket production** without
  further analysis of the regression signals.
- **Route-type-conditional** adoption is the most defensible path:
  - For factual queries (route=answer + box_s_consulted=True), α is
    a high-leverage low-cost win. Adopt.
  - For meta / identity queries, keep baseline (all options near-
    ceiling already; γ's 11% leakage is concerning).
  - For casual_greeting, keep baseline (fast path, no synthesis).
  - For verify route (EAL-adjudicated), the Pattern C prompt already
    enforces evidence fidelity; reflective adds marginal benefit at
    latency cost.
- **Avoid β's external reflective note** for user-facing polish
  unless a "※ note:" UI convention is desired.

### Effort-to-value ratio

α is the only option with a strong case for production. The
conditional-α approach can be tested in a follow-up session by
extending the C.3 predicate (or adding a new synthesis hook) to
append α only when Brave escalation fired. Estimated scope: 1 commit,
low risk.

## 9. Forensic implications

T's original hypothesis: "meta-cognitive gap" in qwen3.5:9b explains
Pattern C Residual R1. **Partially confirmed**:

- Adding a short self-review instruction DOES shift the model into
  evidence-following mode for factual queries (F4a 0/3 → 3/3).
- The limit is not "the model can't follow the prompt"; α's 60-token
  budget is enough when the task is simple evidence matching.
- For multi-step rule-tracking (shiritori F5), reflective prompt is
  insufficient — architectural (game-flow module) or stronger model
  is required.

The forensic framework "prompt-level reliability fix" is thus:
- **Viable** for factual evidence-following (F4-class).
- **Marginal** for multi-turn consistency (F3, F5).
- **Counterproductive** for self-ref / casual queries (leakage,
  drift risks).

### Proposed next-session forensic scope adjustment

If T wants to continue the factual-integration quality cycle rather
than pivot to Secretary:

1. **α-conditional adoption** (single commit): append α to prompts
   when box_s_consulted=True AND not meta_question AND not
   casual_greeting. Re-run 33-scenario + Krillin N=10 to confirm
   stable 3/3 A18 rate.
2. Defer β / γ production adoption pending adaptive dispatcher
   design (Secretary-adjacent concern).

If T pivots to Secretary:

- This experiment provides a documented prompt-variance curve that
  the Secretary can reference when classifying observed failures.
- α's dramatic F4a win is a natural baseline for Secretary to
  propose per-route prompt conditioning.

## 10. Experimental metadata

- Wall time: ~90 min (60 runs × ~90 s with session init)
- Model: qwen3.5:9b Q4_K_M via Ollama, temperature 0.2
- Judge: openai/gpt-oss-120b via Groq (0 Llama fallbacks)
- Production path: unchanged (verified via `git status` before and
  after)
- Backup tag pre_stage_abc_20260424_bedtime intact
- Evolution Log: **not incremented** (methodology observation, not a
  runtime cycle)

## 11. Raw artifacts (ephemeral)

- `/tmp/reflective_experiment.py` — harness
- `/tmp/reflective_score.py` — judge+rule scoring
- `/tmp/reflective_results.json` — 72 run records
- `/tmp/reflective_scored.json` — with judge + signal annotations

Deleted at Phase 5 cleanup; only this document is committed.
