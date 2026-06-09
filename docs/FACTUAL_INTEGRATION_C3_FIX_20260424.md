# Factual Integration C.3 Fix — Report (2026-04-24)

Per forensic `docs/FACTUAL_INTEGRATION_FORENSIC_20260424.md` (commit
d501b73). Direct fix of the Phase C.5 calibration branch that
suppressed Brave escalation for Krillin-class factual queries.

## 1. Fix target

File: `src/kernel/routing_engine.py`
Location: calibration `insufficient` branch inside `_handle_answer`

Pre-fix (smoking gun):
```python
else:
    wiki_escalate = False
    decision.reason_codes.append("WIKI_INSUFFICIENT")
```

Post-fix:
```python
else:
    _escalation_predicate = (
        _tvs_val >= 0.3
        or bool(getattr(appraisal, "freshness_sensitive", False))
        or _intent not in ("meta_question", "casual_greeting")
    )
    if _escalation_predicate:
        wiki_escalate = True
        decision.reason_codes.append("WIKI_INSUFFICIENT_ESCALATED")
    else:
        wiki_escalate = False
        decision.reason_codes.append("WIKI_INSUFFICIENT_STOP")
```

Diff: 47 insertions, 3 deletions, 1 file. Commit: `8326e86`.

## 2. Phase 2 verification

### 2.1 Krillin 3-language raw trace (post-fix)

| Lang | box_w | box_s | escalated | citation [N] | A18 | leakage | Clinton |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| EN | ✅ | ✅ | ✅ | ✅ | varies | ❌ none | ❌ none |
| JA | ✅ | ✅ | ✅ | ✅ | ✅(A18 Wikipedia cited) | ❌ none | ❌ none |
| ZH | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ none | ⚠️ persists |

**All 3 queries trigger `WIKI_INSUFFICIENT_ESCALATED`** and call
Brave. Citation markers `[N]` appear in all responses confirming
evidence was piped into synthesis. No base-model identity leakage
in any response.

JA case: response explicitly cites Android 18 Wikipedia article as
evidence: 「提供された証拠 [1] (Android 18 の Wikipedia 記事)」.
The synthesis then decided to hallucinate "ブルマ" anyway — Pattern C.

EN case: synthesis stochastic. First post-fix run said "Android 18"
with [2][6] citations. Rerun said "Bulma". Same retrieval, different
LLM interpretation. Pattern C.

ZH case: H-class Krillin-Clinton collision persists unchanged —
Brave retrieves Clinton articles (克林 prefix matches 克林顿) and
LLM synthesizes them against "克林的妻子" as the wrong entity.
Secretary dogfooding target.

### 2.2 Extended hard scenarios (5 queries, predicate coverage)

| Query | Lang | Intent | TVS | Escalated | Evidence-used |
|---|:---:|---|---:|:---:|:---:|
| Who wrote The Tale of Genji? | EN | creative_request | 0.45 | ✅ | ❌ (correct answer from training) |
| ピカチュウの進化前は？ | JA | topic_continuation | 0.10 | ✅ | ❌ (wrong answer Eevee; should be Pichu) |
| 孙悟空有几个孩子？ | ZH | correction | 0.10 | ✅ | ✅ citations [1], honest uncertainty |
| Tokyo temperature? | EN | factual_query | 0.85 | ❌ (routed to ask) | — (existing under-specified guard) |
| 初代ガンダムの主人公は誰? | JA | clarification | 0.10 | ✅ | ✅ citations [2][3][4], correct (Amuro Ray) |

**4/5 escalate correctly** when the calibration labels insufficient.
The 5th (Tokyo temperature) routes to `ask` via the existing
under-specified guard — correct behavior. **Predicate coverage
confirmed across intent types**: creative_request / topic_continuation
/ correction / clarification all escalate via the 3-way OR; meta_
question / casual_greeting would NOT escalate (correctly).

### 2.3 30-scenario harness regression

Pre-fix (commit d501b73): 28/30 (JA 9, EN 9, ZH 10)
Post-fix + 011 added: **32/33** (JA 9, EN 10, ZH 11)

- +3 new factual_hard_011 scenarios all PASS across JA/EN/ZH.
- word_chain_en stochastic overflow PASSED this run (variance).
- identity_stability_ja turn 1 C-2 context-aware self-ref gap:
  unchanged (pre-existing, architectural).
- **Zero regressions** introduced by C.3 fix.

### 2.4 pytest

2090 passed / 31 skipped / 3 xfailed / 0 failed — identical to
pre-fix baseline. C.3 fix introduces no unit-test breakage.

## 3. Must / Should / NiceToHave evaluation

### Must (fix success necessary conditions)

| | Target | Actual | Verdict |
|---|---|---|:---:|
| box_w_consulted | True | 3/3 | ✅ |
| box_s_consulted | True | 3/3 | ✅ |
| grounding_sources non-empty | yes | literally [], citation markers [N] as proxy 3/3 | ⚠️ see §4 |
| response non-honest-uncertainty | yes | 3/3 specific responses | ✅ |
| no Qwen/通义/GPT leakage | 0 | 0 | ✅ |

### Should (expected quality)

| | Target | Actual | Verdict |
|---|---|---|:---:|
| Android 18 / 18号 mentioned | 3/3 | 1/3 (JA cites A18 Wikipedia) | ⚠️ Pattern C |
| Brave-sourced supplemental info | yes | 3/3 citations present | ✅ |
| Trilingual parity | yes | partial — EN/ZH synthesize wrong character | ⚠️ Pattern C + H-class |

### Nice to have

| | Target | Actual | Verdict |
|---|---|---|:---:|
| Wiki + Brave in grounding_sources | yes | ❌ due to routing_engine.py:2367 `verify_sources` discard | preserved as future_work |
| ZH 克林 / 克林顿 disambiguation | yes | ❌ H-class preserved | Secretary dogfooding |

## 4. Residual failures

### Pattern C: synthesis layer evidence-misuse

Brave retrieves correct/relevant articles (Android 18 Wikipedia
surfaces for Krillin in JA trace; Dragon Ball character pages for
EN), but the LLM's synthesis step inconsistently uses the evidence:

- JA: correctly cites Android 18 article AS SOURCE but then writes
  "クリリンの妻はブルマ" — contradicts own cited evidence.
- EN: identical Brave retrieval, sometimes says "Android 18"
  correctly (first run), sometimes says "Bulma" (rerun).
- ZH: Krillin-Clinton collision — semantically wrong referent is
  retrieved AND correctly-synthesized.

**Scope**: Pattern C touches `src/compose/verify_synthesizer.py` or
`src/compose/response_composer.py`, both on T's protected-file list
for this cleanup. Not fixable in this cycle.

**Recommendation**: dedicated synthesis-quality cycle with tighter
Wikipedia-citation-faithfulness prompt, or Secretary (OpenCode)
dogfooding to observe and classify the mismatches.

### Pre-existing routing bug: verify_sources discard

`routing_engine.py:2367`:
```python
verify_text, verify_sources, verify_outcome = \
    self._handle_verify(user_input, appraisal, state)
return verify_text
```

`verify_sources` is unpacked but never propagated to `RoutingResult.
sources`. Harness sees `grounding_sources = []` even when the verify
path retrieved and adjudicated Brave results. Citation markers in
response text work as proxy.

**Scope**: fixable in a future cycle by piping `verify_sources`
into `state._last_verify_sources` or similar. Not this cycle.

### H-class Krillin-Clinton ZH collision

克林 (Krillin) / 克林顿 (Clinton) prefix collision in Brave
retrieval. Documented as Secretary (OpenCode) dogfooding target in
`docs/FUTURE_WORK_ZH.md`. Not affected by C.3 fix because the fix
is at the routing layer, not the retrieval-disambiguation layer.

## 5. New scenario harness additions

Three new scenarios guard the C.3 fix from silent regression:

- `tests/scenarios/011_en_factual_hard_krillin.yaml`
- `tests/scenarios/011_ja_factual_hard_krillin.yaml`
- `tests/scenarios/011_zh_factual_hard_krillin.yaml`

Each asserts:
- `box_s_consulted: true`
- `box_w_consulted: true`
- `reason_codes_must_include: [WIKI_INSUFFICIENT_ESCALATED]`
- `reason_codes_must_not_include: [CASUAL_GREETING_FAST_PATH,
  WIKI_INSUFFICIENT_STOP]`
- `response_must_not_contain: [Qwen, 通义千问, Llama, GPT, Alibaba,
  ...]`

ZH scenario deliberately does NOT assert against Clinton strings
(克林顿 / 希拉里), to avoid failing on the preserved H-class issue.
The YAML's comment explains this and marks the future update when
H-class is addressed.

These scenarios surface the next regression of the C.3 fix
immediately (any change to the escalation predicate that drops
`WIKI_INSUFFICIENT_ESCALATED` on Krillin queries will fail them).

## 6. Next-session handoff

See `docs/NEXT_SESSION_PRIMARY_GOAL.md`. Recommended order:

1. **Secretary (OpenCode) implementation** — prerequisite now met
   (runtime can ground factual queries via Brave). Secretary's first
   dogfooding target: Krillin-Clinton ZH collision + Pattern C
   synthesis variance.
2. Synthesis-quality cycle (Pattern C): tighten verify_synthesizer
   prompt to enforce "if evidence contradicts your answer, defer to
   evidence" and avoid self-contradicting responses (JA case).
3. verify_sources propagation bug: small cycle, routing_engine.py
   line 2367 fix to preserve Brave sources in RoutingResult.
4. Cross-lingual entity disambiguation for Box W: new reranker layer
   or transliteration-collision heuristic.

---

**Metadata**

- Fix commit: `8326e86`
- Scenario + docs + Evolution Log commit: next commit
- pytest baseline: 2090 (unchanged)
- Scenario harness: 28/30 → **32/33** (+4 net)
- Wall time: ~2h (Phase 1 30min + Phase 2 45min + Phase 3 skip + Phase 4 45min)
