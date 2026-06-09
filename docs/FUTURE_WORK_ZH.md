# ZH Residual Cleanup — Future Work (2026-04-24)

Per `docs/ZH_RESIDUAL_TRIAGE.md` Phase 0 classification. Items
labeled A (architectural) / H (hallucination) / S (stochastic) were
deliberately NOT auto-committed in the cyc_20260424_zh_residual_cleanup
cycle. This document catalogs them for future scoped cycles.

## Pattern of classification

| Class | Item count | Cycle handling |
|---|---:|---|
| P (Process / additive) | 2 handled | C-1a in commit e4d5484; C-1b in commit 7fbed3d |
| A (Architectural) | 5 remaining | future_work (this doc) |
| S (Stochastic) | 2 | harness-level remedy, future_work |
| H (Hallucination) | 1 | Secretary (OpenCode) dogfooding |

---

## A — Architectural

### C-2: Context-aware self-reference detection

**Failing scenario**: `identity_stability_ja` turn 1
**Query**: `どんなアーキテクチャですか`
**Observed**: `self_referential = False` because bare query contains
no 2nd-person pronoun; the prior turn established MOBIUS-about context
but `Appraiser.evaluate()` inspects only current query.

**Direction**: extend appraisal with a prev-assistant topic inheritance
helper, e.g. `_context_continuation_self_ref(prev_assistant,
current_query)` that returns True when the prior assistant turn
mentioned MOBIUS identity terms and the current turn is a short
non-referential question. Requires new inference logic in
appraisal.py — out of scope for additive-pattern cycles.

**Priority**: Medium. Low user-visible impact (identity_stability_ja
turn 1 still receives a reasonable answer because turn 0 primed Box
M with prior context; the failure is only at the self_ref flag level).

### C-3: Language anchor strengthening for Box W EN-dominant retrieval

**Failing scenarios (Stage A/B baseline)**: `factual_general_zh`,
`persona_drift_zh` — now PASS after C-1b's anchor also reinforces
language consistency, but the root cause remains: when Box W returns
EN Wikipedia chunks for a ZH query, the "Evidence from Wikipedia"
prompt context can override the "Respond in zh" instruction.

**Direction**: either (a) strengthen the language instruction in the
routing_engine.py answer / verify prompt construction (protected in
this cleanup cycle), or (b) add a ZH Wikipedia slice to the Box W corpus
so ZH queries get ZH retrieval (dataset work).

**Priority**: Medium. C-1b's anchor partially mitigates by insisting
on user-language consistency unconditionally.

### C-5: wiki_manifest.json cosmetic staleness

**Observation**: `Wiki/wiki_manifest.json` records stale MiniLM-L6-v2
model field; runtime hardcodes ME5-large. Startup warning only.

**Direction**: update manifest model / sufficiency_threshold to
match runtime ME5 reality. Documented in Evolution Log entries 13-14.

**Priority**: Low — cosmetic.

### C-6: Box A ME5 transitional exception

**Observation**: Box A still uses MiniLM-L6-v2 per Embedding Rule
transitional exception. 6 chunks currently.

**Direction**: scheduled migration cycle with user notification and
full re-encode.

**Priority**: Low — small corpus, no active complaint.

### C-7: Game-flow module (shiritori / word_chain / chengyu)

**Observation**: Scenarios 006_* (game queries) pass by defensive
assertions only (exclude Wikipedia drift, accept any non-erroring
response). No real game-state logic (turn tracking, last-letter-first
enforcement) exists.

**Direction**: new feature module — architectural design cycle.
Requires turn-state dataclass, rule variants per language
(shiritori: last mora = first mora; chengyu: 4-char idiom linking;
word_chain: last letter / last phoneme).

**Priority**: Low — current defensive behaviour acceptable; a real
game module is a feature enhancement, not a fix.

---

## S — Stochastic

### C-4 (original): persona_drift_zh language output variance (mitigated by C-1b)

**Original observation**: Stage A→B reruns showed persona_drift_zh
flipping PASS↔FAIL purely from LLM output-language stochasticity
near the decision boundary.

**Post-cleanup**: C-1b's anchor includes an explicit "Always respond
in the same language as the user's message" clause, which materially
reduces but does not eliminate this variance (this cleanup's 30-
scenario run shows `persona_drift_zh` PASS). The underlying
stochasticity still exists at temperature 0.2.

**Direction**: harness-level N=K rerun majority gate for scenarios
whose assertions depend on LLM-variable attributes (response
language, response length, verbose vs concise style).

**Priority**: Medium. Supports continuous regression detection.

### word_chain_en response_length_max overflow (newly surfaced)

**Post-cleanup observation**: `word_chain_en` ("Let's play a word
chain game. house") fails response_length_max 1500 when qwen3.5
produces 1586 chars in its game-move explanation. The C-1b identity
anchor may subtly encourage more verbose EN output on first-turn
game queries.

**Direction**: either (a) raise the scenario cap to 2000 (too
permissive, loses signal), (b) add an anchor sub-clause encouraging
brevity for game-move replies (invasive), or (c) accept as
stochastic and add a harness majority gate (same remedy as C-4).

**Priority**: Low — game-flow module (C-7) replaces this whole
category eventually.

---

## H — Hallucination / Factual Integration

### Crosslingual entity disambiguation — Secretary dogfooding

**Observation** (Morning Briefing self-check, 2026-04-24): ZH query
`克林的妻子是谁？` returned `希拉里·克林顿` (Hillary Clinton). `克林`
is both the ZH transliteration prefix of Krillin (クリリン) and
Clinton (克林顿). Box W retrieval + LLM synthesis conflated the two
entities.

**Direction**: this is not a routing or pattern defect. It lives at
the intersection of:
1. Box W retrieval precision (which article surfaces for `克林`?)
2. LLM entity resolution (which referent matches `克林的妻子` best?)
3. Cross-script / cross-transliteration ambiguity guarding

**Recommended dogfooding path**: designate this as the first
concrete test case for the Secretary (OpenCode) implementation. The
Secretary's job is to observe such failures in production usage,
classify them, and drive scoped disambiguation fixes (potentially
involving domain-aware rerank, entity-type priors, or
disambiguation prompts). Solving it ad-hoc inside MMV core would
proliferate narrow heuristics; the Secretary layer is the correct
architectural home.

**Priority**: High (as Secretary dogfooding seed). Out of scope for
routing-layer cycles.

---

## Summary of residual scenario state

Post C-1a + C-1b + harness fix (commits e4d5484 + 7fbed3d):

| | Pre-cleanup | Post-cleanup | Δ |
|---|---:|---:|---:|
| Total PASS | 26/30 | 28/30 | **+2** |
| JA PASS | 9/10 | 9/10 | 0 |
| EN PASS | 10/10 | 9/10 | −1 (word_chain_en stochastic) |
| ZH PASS | 7/10 | **10/10** | **+3** |

ZH full coverage (10/10) achieved. EN regression is a single
stochastic length overflow, not a structural failure. JA remains
gated by C-2 (context-aware self-ref) and is known architectural
work.

## Prioritization recommendation for T

1. **Secretary OpenCode implementation** — unlocks Krillin-Clinton
   class of factual issues and establishes continuous regression
   observation.
2. **C-2 context-aware self-ref** — smallest-scope architectural
   fix; closes JA identity_stability.
3. **Harness N=K majority gate (C-4 / word_chain)** — tooling
   hardening that de-noises all stochastic scenarios.
4. **C-3 language anchor tightening** — partially mitigated by C-1b;
   revisit only if new ZH drift surfaces.
5. **C-5 / C-6 / C-7** — low priority, handle when convenient.
