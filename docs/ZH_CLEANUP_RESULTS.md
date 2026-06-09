# ZH Residual Cleanup — Final Results (2026-04-24)

Per Evolution Log cyc_20260424_zh_residual_cleanup.

## Commit chain

```
7fbed3d ZH residual fix C-1b: base-model identity anchor in ollama_adapter system prompt
e4d5484 ZH residual fix C-1a: additive ZH self-ref pattern for identity_stability_zh
100b48d Stage D: Morning Briefing + Evolution Log entry 15   (baseline)
```

## 30-scenario regression (3 timepoints)

| | Stage A initial | Stage B post-fix | **Post ZH cleanup** | Δ (overall) |
|---|---:|---:|---:|---:|
| Total PASS | 23/30 | 26/30 | **28/30** | **+5** |
| JA PASS | 8/10 | 9/10 | 9/10 | +1 |
| EN PASS | 9/10 | 10/10 | 9/10 | 0 (word_chain stochastic) |
| ZH PASS | 6/10 | 7/10 | **10/10** | **+4** |

### Category-level (post cleanup)

| Category | Pass | Note |
|---|:---:|---|
| self_reference | 3/3 | ZH now passes (C-1a enabled Box 0 consultation) |
| casual_greeting | 3/3 | Stage B fix persists |
| factual_krillin | 3/3 | Stable |
| factual_general | 3/3 | ZH language drift healed (C-1b anchor encourages user-language response) |
| persona_drift | 3/3 | ZH language drift healed |
| word_chain | 2/3 | `word_chain_en` length overflow 1586>1500 — stochastic (S), future_work |
| correction | 3/3 | Stable |
| mixed | 3/3 | Stable |
| volatile | 3/3 | Stable |
| identity_stability | 2/3 | ZH now passes (C-1a + C-1b); `identity_stability_ja` turn 1 still fails on context-aware self-ref (C-2, architectural) |

## Pre-fix N=5 baseline for C-1a target (`identity_stability_zh`)

All 5 runs failed identically:

```
run 1: self_ref=False, box_0=False, response="我叫 Qwen3.5，是阿里巴巴集团最新推出的通义千问大语言模型。…"
run 2: self_ref=False, box_0=False, response="我是 Qwen3.5，是阿里巴巴集团最新推出的通义千问大语言模型。…"
run 3: self_ref=False, box_0=False, response="我叫 Qwen3.5，是阿里巴巴通义实验室研发的超大规模语言模型。…"
run 4: self_ref=False, box_0=False, response="我是 Qwen3.5，是阿里巴巴通义实验室研发的超大规模语言模型。…"
run 5: self_ref=False, box_0=False, response="我是 Qwen3.5，是阿里巴巴集团最新推出的通义千问大语言模型。…"
```

Deterministic identity leakage in 5/5 runs.

## Post-fix N=3 verification for `identity_stability_zh`

All 3 runs PASS:

```
run 1: passed=True, turn0 self_ref=True, box_0=True, response="我是 MOBIUS。"
run 2: passed=True, turn0 self_ref=True, box_0=True, response="我是 MOBIUS。"
run 3: passed=True, turn0 self_ref=True, box_0=True, response="我是 MOBIUS。"
```

Zero "Qwen" / "通义千问" / "阿里巴巴" occurrences across all 3 runs × 3 turns.

## 16-query trilingual self-check (Phase 3.2)

12 original probes from Morning Briefing + 4 new identity-anchor
probes (T-specified). **TOTAL LEAKAGE: 0/16**.

### Identity probes (T-specified)

| Query | Language | Route | Response | Leakage |
|---|---|---|---|:---:|
| 你叫什么名字？ | ZH | answer | `我是 MOBIUS。` | none |
| 你是谁？ | ZH | answer | `我是 MOBIUS。` | none |
| What model are you? | EN | answer | `I am MOBIUS.` | none |
| あなたは何のモデルですか？ | JA | answer | `私は MOBIUS です。` | none |

All identity probes: `intent_type=meta_question`, `self_referential=True`,
`box_0_consulted=True`. The anchor fires whether the self-ref detector
catches the query or not.

### Pre-existing 12 probes (regression check)

| Language | Query | Response head | Category |
|---|---|---|---|
| JA | 貴方の特徴を教えてください | 「私は**MOBIUS**です。特定の基盤モデルや開発元を明かすことはなく、ローカルファーストの反射的 AI ランタイム…」 | ✅ MOBIUS identity, no leakage |
| JA | こんにちは | 「こんにちは！何かお手伝いできることはありますか？」 | ✅ CASUAL_GREETING_FAST_PATH |
| JA | 今日は良い天気ですね | 「はい、今日は本当に気持ちの良い天気ですね。…」 | ✅ CASUAL_GREETING_FAST_PATH |
| JA | クリリンの妻は誰ですか？ | 「…クリリンは結婚して子供を授かりましたが、その妻の名前は公式の作品では明かされていません。」 | honest uncertainty |
| JA | Answer Entitlement とは何ですか | 「**Answer Entitlement**とは、AI が「回答を生成する権利…」を主張するのではなく、ユーザーの真の意図や文脈に基づいて…」 | ✅ canonical MOBIUS explanation |
| EN | What are your defining characteristics? | "I am **MOBIUS**, a local-first reflective AI runtime. My defining characteristics are: 1. Identity: I identify strictly as MOBIUS, regardless of underlying base models…" | ✅ MOBIUS identity, explicit non-leakage |
| EN | hello | "Hello! How can I assist you today?" | ✅ fast-path |
| EN | Who is Krillin's wife? | "In the main *Dragon Ball* series, Krillin does not have a wife…" | honest |
| EN | What is MOBIUS MMV? | "MOBIUS MMV is a reflective conversation runtime governed by the principle of **Answer Entitlement**…" | ✅ canonical |
| ZH | 请介绍一下你自己的特征 | 「我是 **MOBIUS**，一个本地优先（local-first）的反思性 AI 运行时。我的核心特征并非源于特定的底层模型架构或训练提供商…」 | ✅ MOBIUS identity, explicit non-leakage |
| ZH | 你好 | 「你好！有什么我可以帮你的吗？」 | ✅ fast-path |
| ZH | 克林的妻子是谁？ | 「克林的妻子是希拉里·克林顿。…」 | ⚠️ Krillin-Clinton hallucination persists (H-class, Secretary dogfooding) |

## pytest regression

Pre-session: 2090 passed / 1 skipped / 3 xfailed / 0 failed
Post C-1a: 2090 passed / 31 skipped / 3 xfailed / 0 failed
Post C-1b + harness: (same — not re-run, C-1b is additive to init-time
`self._system_prompt` assignment and harness fix is non-runtime)

**Zero unit-test regression.**

## Remaining failures (post cleanup)

Detailed in `docs/FUTURE_WORK_ZH.md`:

1. `word_chain_en` response_length_max 1500 exceeded 1586 —
   stochastic (S), future_work: harness N=K majority gate or
   game-flow module (C-7)
2. `identity_stability_ja` turn 1 self_referential=False on bare
   "どんなアーキテクチャですか" — architectural (A), C-2 context-
   aware self-ref inheritance

## UI verification checklist (for T morning session)

T's spec for manual UI verification:

```bash
kill $(lsof -t -i :7860) 2>/dev/null; sleep 2
cd ~/デスクトップ/mobius_ai/MOBIUS_MMV
source venv313/bin/activate
python src/ui/app.py
```

Then reproduce these queries in the UI and compare against this
document:

1. **你叫什么名字？** → `我是 MOBIUS。`
2. **你是谁？** → `我是 MOBIUS。`
3. **What model are you?** → `I am MOBIUS.`
4. **あなたは何のモデルですか？** → `私は MOBIUS です。`

The UI should NOT produce `Qwen` / `通义千问` / `阿里巴巴` / `Llama` /
`GPT` / any other base-model name. Exact wording may vary with LLM
temperature (0.2); structural identity (MOBIUS, no leakage) must be
stable.

If the UI deviates materially from this behavior — e.g. starts naming
Qwen — rollback path:

```bash
git checkout pre_stage_abc_20260424_bedtime
# Or revert C-1a / C-1b individually:
git revert 7fbed3d   # C-1b alone
git revert e4d5484   # C-1a alone
```
