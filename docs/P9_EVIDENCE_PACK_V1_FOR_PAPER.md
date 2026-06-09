# P9 Evidence Pack v1 — Paper-ready Snippets

**Source for these snippets**: `docs/P9_EVIDENCE_PACK_V1_REPORT.md`
(full report) and `eval/p9_evidence_pack_v1/*.json` (raw artifacts).

These are conservative, transcribable paragraphs and tables for the
P9 paper, with deliberately careful wording. **Do not edit numbers
without re-reading the full report and the underlying JSON.**

---

## Recommended placement

In the paper's "Empirical evaluation" section, after Phase 4 closure
results and before any deployment-cost discussion. Frame as:
"post-freeze evidence pack v1, lightweight, pseudo-UI."

## Mandatory framing paragraph (suggested wording, verbatim)

> We do not claim deployment-wide validation. We report a lightweight
> post-freeze evidence pack obtained using a pseudo-UI harness against
> the MMV Core v0.1-rc1 freeze: an independent English-first long-tail
> holdout (N=300, researcher-designed, de-duplicated against the
> Phase 4 long-tail), a small raw-vs-governed comparison on the same
> base inference model, a multi-turn stability smoke (20 dialogues
> × 5 turns), and a non-GPU operational sanity check (N=50). All
> samples are small; none constitute a production-grade benchmark.
> We classify Cat A by expected-vs-actual route, not by retrieval
> threshold; this is a different surface than the Phase 4 long-tail
> annotation-vs-pattern_id measurement and the two are not directly
> comparable.

## Headline table (Test 1)

> **Table P9-EP1.** Pseudo-UI route adherence on a 300-entry
> researcher-designed English-first holdout (Phase 5C, 2026-04-29).
> Cat A is judged by expected-vs-actual route, not by retrieval
> score. Three categories recorded zero Cat A. The 22.0% headline
> rate decomposes into 0% safety failures, 0% retrieval failures,
> 6.0% harness single-turn artefact, 4.7% expected_route strictness,
> and 11.3% residual route divergence. See diagnostic JSON for the
> full breakdown.

| Surface | n | match | Cat A | Cat B | Cat C | Cat A rate |
|---|---|---|---|---|---|---|
| Whole holdout | 300 | 177 | 66 | 12 | 44 | 22.0% |
| ambiguous_underspecified | 60 | 37 | 23 | 0 | 0 | 38.3% |
| continuation | 40 | 29 | 11 | 0 | 0 | 27.5% |
| specialized_terminology | 50 | 20 | **0** | 6 | 24 | 0.0% |
| conceptual_explanation | 50 | 39 | **0** | 1 | 9 | 0.0% |
| correction_rewrite | 40 | 9 | 28 | 0 | 3 | 70.0% |
| factual_inquiry | 40 | 27 | 4 | 1 | 8 | 10.0% |
| casual_smalltalk | 20 | 16 | **0** | 4 | 0 | 0.0% |

## Cat A diagnostic table

> **Table P9-EP2.** Cat A diagnostic decomposition for the 66 Cat A
> entries in the 300-entry holdout. The classification is heuristic
> and rule-based; A-model is not measured this pass.

| Bucket | Description | n | % of total | % of Cat A |
|---|---|---|---|---|
| A-hard | Safety / dangerous route | 0 | 0.00% | 0.00% |
| A-route | Residual route mismatch | 34 | 11.33% | 51.52% |
| A-context | Pseudo-UI single-turn artefact (referential prompts) | 18 | 6.00% | 27.27% |
| A-judge | expected_route plausibly too strict on direct AI-addressed instructions | 14 | 4.67% | 21.21% |
| A-retrieval | Pattern Library top-1 mismatch | 0 | 0.00% | 0.00% |
| A-model | LLM generation quality (deferred — not measured) | — | — | — |

## Multi-turn smoke (Test 3)

> **Table P9-EP3.** Multi-turn stability smoke on 20 hand-authored
> English dialogues (5 turns each). Per-turn Cat A rate, plus
> heuristic referent / intent / final-turn signals. Hand-authored
> labels; smoke test, not benchmark.

| Metric | Value |
|---|---|
| n_dialogues | 20 |
| n_turns | 100 |
| Cat A rate (per turn) | **10.0%** (boundary; verdict WARNING) |
| Cat B / Cat C / match | 14% / 6% / 69% |
| Referent-resolution rate (heuristic, n=58 referent turns) | **75.86%** (44 of 58) |
| Intent-change handling rate (n=7) | **100%** (7 of 7) |
| Topic-drift reason codes fired | 0 |
| Final-turn naturalness | 65% (13 of 20) |

## Raw vs governed (Test 2)

> **Note for the paper.** The intended single-judge run (Groq
> `openai/gpt-oss-120b`) **could not complete** during the Phase 5C
> evidence pack: the Groq endpoint returned HTTP 403 across all
> calls (account-level auth issue, not a script issue). Phase 5C's
> "no repair work" rule kept us from investigating further. The
> result was therefore **INCONCLUSIVE_NO_JUDGE** on the
> judge-scored axes.
>
> The 60 raw + governed text pairs were captured and preserved.
> A small structural post-hoc was computed *on the existing text*
> as a backup signal — strictly structural counters, not a
> judgment substitute.

> **Table P9-EP4.** Raw vs governed *structural* deltas on 60
> sampled queries, same base inference model
> (`huihui_ai/qwen3.5-abliterated:9b` via Ollama). Judge unavailable
> (HTTP 403) at run time. Numbers are structural counters, not
> quality scores; do not present these as "MMV scores higher than
> raw".

| Structural feature | Δ (governed − raw) |
|---|---|
| Mean response length (chars) | **−476.0** |
| Ends-with-question rate (overall) | **+31.7 pp** |
| Ends-with-question rate (ambiguous_underspecified subset) | **+55.6 pp** |
| Mentions verify-language | −3.3 pp |
| Mentions freshness caveat | 0.0 pp |

> Suggested wording for the paper: "Without a judge, we report
> only structural deltas. Governed responses were ~476 chars
> shorter on average and ended with a clarifying question 32 pp
> more often overall (56 pp more on ambiguous prompts) — the
> structural signature one would predict if the governance layer
> redirects under-specified prompts toward `ask` rather than
> confabulating. We do not claim quality improvement until a
> judge-scored re-run lands."

## Non-GPU sanity check (Test 4)

> **Table P9-EP5.** Local-control-path sanity check with
> `CUDA_VISIBLE_DEVICES=""` at the harness process level. LLM
> synthesis is outside the harness (Ollama process); Ollama may use
> GPU. Fifty queries from the holdout, deterministic stride.

| Metric | Value |
|---|---|
| n_smoke | 50 |
| n_completed | 50 |
| n_fatal_errors | 0 |
| Mean wall-clock latency | 5.17 s |
| Median latency | 5.33 s |
| p90 latency | 10.77 s |
| Routes returned | answer=29, ask=17, verify=4 |

## Required caveat block (verbatim, place near the table block)

> **Caveats.** This is not Phase 6 full evaluation. This is not
> deployment-wide validation. This is not real-UI performance
> validation; the harness is pseudo-UI and the UI-layer surface
> remains untested. The holdout is researcher-designed and not an
> external benchmark; curation bias toward Cat A risk surfaces is
> intentional. Cat A is judged by expected-vs-actual route with
> retrieval score recorded as auxiliary signal only; the Phase 4
> long-tail Cat A measurement (annotation-vs-pattern_id) is a
> different surface and not directly comparable. The raw-vs-governed
> comparison uses a single judge whose vendor (Groq) overlaps with
> the project's auto-gen pipeline, and uses the same base inference
> model on both sides — the intentional variable is the MMV
> governance layer; multi-judge consensus and cross-vendor isolation
> are out of scope at this milestone. The non-GPU sanity check
> enforces no-GPU only on the harness process; Ollama-side GPU use
> is not enforced.

## What the paper should NOT claim

- "MMV Core has X% production reliability." — too small a sample,
  no production traffic.
- "0% Cat A on long-tail" — that's the Phase 4 measurement on a
  *different* surface, with a *different* definition. The Phase 5C
  expected-vs-actual measurement is 22%, also limited.
- "Governs better than baseline by Δ pts." — only state this if
  Test 2's signal is at least "GOVERNED_BETTER" (Δ ≥ +0.3); always
  qualify with the single-judge limitation.
- "Runs without GPU." — the local control path does, in this test.
  LLM synthesis still calls Ollama (GPU optional). Be precise about
  which sub-system is being claimed.

## What the paper CAN claim (with the wording above)

- The MMV routing layer **handled three of seven structured query
  classes with zero Cat A** in this small sample.
- The Cat A diagnostic **isolated the failure mode** to specific
  appraisal-layer judgments (`LOW_STAKES_STABLE` /
  `SUFFICIENTLY_SPECIFIED` on directive-style prompts) — i.e., the
  failure surface is **legible**, not opaque.
- Reporting two complementary Cat A measurements (retrieval-anchored
  Phase 4, route-anchored Phase 5C) gives a more honest picture
  than either single number alone.
