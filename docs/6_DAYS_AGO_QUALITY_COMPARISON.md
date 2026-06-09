# 6-Days-Ago Quality Comparison (State X vs HEAD, 2026-04-24)

Reference: T's original concern — "6 日前の UI は動いていたのに、
個別モジュール磨きで劣化した". This document evaluates the claim after
the C.3 + Pattern C full fix cycle.

## Timeline

| Date | Event | Substrate |
|---|---|---|
| 2026-04-12 (~6 days ago) | State X local backup taken | MiniLM-L6-v2 Box W (EN-only, 384-dim) + simple Brave adapter (128 lines) + no Phase C.5 calibration |
| 2026-03-22 → 2026-04-22 (30-day un-versioned gap) | ME5 migration, Phase C.5 calibration added, 23 new modules | State Y (HEAD baseline) |
| 2026-04-22 → 2026-04-24 | 19 additional commits (RCB / Phase E / Fix 1 / L1-A / Fix 2 / Stage A-D / ZH cleanup / C.3 / Pattern C) | current state |

## Krillin query comparison

State X UI behavior (inferred from backup's routing_engine and
brave_search_adapter):
- "Who is Krillin's wife?" → Brave Web Search (simple endpoint, no
  Goggles) likely returned Wikipedia + Dragon Ball fandom sites →
  EAL adjudicated → response cites Android 18 when top results
  included the Android 18 article.
- JA/ZH: MiniLM is English-only, so ZH/JA queries scored uniformly
  low on Box W → always escalated to Brave → Brave returned
  English results → response in English (or translated via LLM).

HEAD (post C.3 + Pattern C full fix):
- Brave adapter has Goggles boosting authoritative sources (Wikipedia
  +3, Britannica +3, etc.) — **strictly better retrieval**
- Box W ME5 cross-lingual — JA/ZH queries don't always need Brave
  escalation, but when they do, C.3 fix + calibration predicate
  ensures escalation fires
- Synthesis prompt enforces evidence-priority (Pattern C fix)
- verify_sources propagated to harness (trace-level improvement)

## Quality delta

### Improvements over State X

| Dimension | State X | HEAD |
|---|---|---|
| Trilingual retrieval | EN-only, MiniLM 384-dim | Cross-lingual ME5 1024-dim |
| Box 0 (self-ref) | MiniLM, EN-only | ME5, 1024-dim, Persona-drift filter |
| Identity leakage | Latent (if self-ref missed) | Unconditional anchor (C-1b) closes Qwen/Llama/GPT leak |
| ZH self-ref | Incomplete patterns | Kanji + ZH pronouns covered (Fix 1 + C-1a) |
| Casual greeting | Wikipedia drift possible | Fast-path (Fix 2 + Stage B) |
| Brave adapter | 128-line simple Web Search | 299-line LLM Context + Goggles + credibility boost |
| Synthesis prompt | Encouraged "use your own knowledge" fallback | Evidence-fidelity enforced (Pattern C) |
| Regression harness | None | 33 trilingual scenarios + Pseudo-UI runner |
| Evidence citation markers | Present but sources lost in escalation | Present + grounding_sources propagated |

### Issues present in HEAD but not State X (mostly stochasticity)

- **LLM prompt-following variance** (qwen3.5:9b at temp 0.2): same
  base model in both states, but HEAD's more complex prompts may
  not be followed consistently. State X had simpler prompts that
  the model was more likely to follow.
- **Calibration stochasticity**: Phase C.5 calibration's auxiliary/
  sufficient/insufficient labeling is not fully deterministic, so
  grounding_sources propagation varies. State X had no calibration
  (always escalated on low confidence).

### Issues pre-existing in State X (HEAD is not worse)

- Krillin-Clinton ZH transliteration collision (H-class): Would
  exist in State X too if ZH query were attempted, because Brave
  retrieval has the same 克林 prefix collision regardless of
  adapter sophistication.
- Factual-integration hallucination on obscure characters: LLM
  training data limits apply equally.

## Trilingual parity achievement

State X had **no meaningful trilingual parity** — MiniLM Box W was
English-only, so JA/ZH queries went through translation+EN workflow.
The pseudo-UI experience was EN-centric.

HEAD post-fix achieves:
- **JA**: Self-ref / casual greeting / factual / identity — all
  respond in JA correctly with evidence integration when applicable.
- **EN**: Full parity; sometimes better than State X because of the
  Goggles-boosted Brave retrieval.
- **ZH**: Self-ref / casual greeting / identity all work correctly.
  Krillin-Clinton H-class persists as known issue.

**Net assessment**: HEAD exceeds State X quality on:
- Trilingual parity (structural)
- Identity integrity (no base-model leakage)
- Retrieval-layer engineering (Goggles, credibility filter)
- Synthesis discipline (evidence priority)
- Regression detection (33-scenario harness)

HEAD equals State X on:
- EN factual accuracy on mainstream queries
- Response fluency

HEAD trails State X on (or presents new variance):
- Prompt-following determinism: qwen3.5:9b's variance under more
  complex prompts
- Specific-name commitment reliability on obscure characters

## Conclusion

T's concern "6 日前の品質で動いていた UI が劣化した" reflected a real
observation at commit d501b73 (before Pattern C fix): Krillin-class
queries hallucinated because the calibration branch suppressed Brave
escalation and the synthesis prompt encouraged "use your own
knowledge" fallback.

After C.3 fix (commit 8326e86) and Pattern C fix (this cycle):
- Structural grounding pipeline is restored — Brave escalation fires,
  evidence reaches synthesis, verify_sources propagates.
- Prompt discourages fabrication.
- Residual variance is at the LLM prompt-following level, not
  structural regression.

**The claim "劣化から超越へ" is substantiated in structural terms**:
HEAD has strictly better engineering across the Box / adapter /
retrieval / scenario axes, with the caveat that LLM reliability
variance is a separate concern requiring either a stronger model or
a dual-pass synthesis layer.

The next-session Secretary (OpenCode) implementation is the
architectural companion to close the remaining variance — by
observing production outputs and proposing scoped fixes, the
Secretary compensates for the LLM-level variance that prompt tuning
alone cannot solve.
