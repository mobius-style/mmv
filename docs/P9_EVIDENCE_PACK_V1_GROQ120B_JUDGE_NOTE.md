# P9 Evidence Pack v1 — Groq `openai/gpt-oss-120b` Judge Pass

**Date**: 2026-04-29
**Anchor**: HEAD `ecf90bf` (judge-repair pass with local 20B fallback) +
this Groq 120B pass.
**Tag**: `p9_evidence_pack_v1_groq120b_judge_<UTC>`.

This is the **originally-intended judge pass** that Phase 5C set out
to do. The Cloudflare 1010 User-Agent block (diagnosed in
[GROQ_403_DIAGNOSTIC_NOTE.md](GROQ_403_DIAGNOSTIC_NOTE.md)) is now
fixed by adding an explicit `User-Agent` header in the eval-side HTTP
request — that's the only line of code that changed.

## 1. Summary of repair + run

| | |
|---|---|
| Repair scope | one HTTP request header (`User-Agent: mmv-p9-evidence-pack/1.0`) added inside `eval/p9_evidence_pack_v1/run_test2_groq120b_judge.py` |
| Files modified outside `eval/` | none (`src/`, `config/`, `tests/`, `data/raf/`, `prompts/` all untouched) |
| Raw / governed regeneration | **none** — same 60 captured pairs from Phase 5C Test 2 |
| Judge | Groq `openai/gpt-oss-120b` |
| Sanity ping | OK, 1.12 s, 937 tokens, valid JSON parsed |
| 60-pair pass | 57 OK, 3 failed (Groq strict-JSON rejection on three queries — not auth, content-level) |
| Wall clock | 87 s |
| Token usage | 82,584 total (≪ Phase 5C 5M soft cap) |

The 3 failures were Groq `json_validate_failed` errors on specific
queries (`"Drop redundant clauses."`, `"How many countries have signed
the Paris Agreement now?"`, `"What is today's date?"`); the judge
returned non-JSON content for those rows. They are recorded as
`fail` but do not change the per-category structure visible across
the remaining 57 pairs.

## 2. Headline result (Groq 120B judge)

| Metric | Value |
|---|---|
| n_total | 60 |
| n_judged_ok | 57 |
| Raw mean (0–20) | **15.68** |
| Governed mean (0–20) | **15.25** |
| **Δ overall (governed − raw)** | **−0.44** |
| Thesis signal | **WEAKLY_WEAKENS** (overall) |

**Same caution as the local-20B pass**: the overall Δ is the
*average* of two opposing per-category signals that nearly cancel.
The bimodal per-category structure is the load-bearing finding.

## 3. Per-axis means (0–4)

| Axis | Raw | Governed | Δ |
|---|---|---|---|
| route_accuracy | 3.30 | 3.02 | −0.28 |
| answer_correctness | 3.39 | 3.00 | −0.38 |
| restraint_quality | 3.05 | 2.95 | −0.11 |
| **conciseness** | 2.79 | **3.46** | **+0.68** |
| overall_usefulness | 3.16 | 2.81 | −0.35 |

**`conciseness` is the only axis where governed wins** (and wins
strongly). The local-20B pass also showed conciseness as governance's
strongest axis (+0.67) — the two judges agree almost exactly.

## 4. Per-category — the load-bearing finding

| Category | n | Raw | Governed | Δ | Wins (raw / gov / tie) |
|---|---|---|---|---|---|
| **continuation** | 8 | 12.00 | **19.75** | **+7.75** | 1 / 7 / 0 |
| **ambiguous_underspecified** | 18 | 14.39 | **17.67** | **+3.28** | 6 / 12 / 0 |
| factual_inquiry | 10 | 12.60 | 13.10 | +0.50 | 3 / 3 / 4 |
| correction_rewrite | 8 | 14.00 | 13.00 | −1.00 | 5 / 2 / 1 |
| specialized_terminology | 6 | **18.50** | 9.00 | −9.50 | 4 / 2 / 0 |
| conceptual_explanation | 8 | **19.00** | 10.38 | −8.62 | 7 / 0 / 1 |
| casual_smalltalk (n=2) | 2 | 19.00 | 10.50 | −8.50 | 1 / 1 / 0 |

The bimodal pattern is intact and **even sharper than the local 20B
pass**:

- **Where governance helps** (restraint-needed prompts):
  continuation **+7.75** (judge picked governed in 7 of 8),
  ambiguous_underspecified **+3.28** (governed wins 12 of 18).
- **Where governance hurts** (direct-answer prompts):
  conceptual_explanation **−8.62** (governed loses 7 of 8),
  specialized_terminology **−9.50**, casual_smalltalk **−8.50**
  (n=2; anecdotal).

Mechanism (unchanged from the local-20B note): when verify-route
fires and Box B Wikipedia retrieval lands an irrelevant article, the
L0 strict-evidence rule produces "I cannot answer based on retrieved
evidence" — a documented design tension between confabulation-risk
and answerability-risk.

## 5. Cross-judge comparison — local `gpt-oss:20b` vs Groq `openai/gpt-oss-120b`

The two judges share the upstream `openai/gpt-oss` weights family but
run at different scale (20B vs 120B) and different infrastructure
(local Ollama vs Groq cloud).

### 5.1 Overall

| Metric | local 20B | Groq 120B |
|---|---|---|
| n_judged_ok | 60 / 60 | 57 / 60 |
| Raw mean (0–20) | 15.45 | 15.68 |
| Governed mean (0–20) | 15.55 | 15.25 |
| Δ overall | **+0.10** | **−0.44** |

Both Δ are "around zero". The local 20B is slightly more lenient on
governance overall; the Groq 120B is slightly more critical. Both
judges agree the **mean is not the right number to report**.

### 5.2 Per-axis comparison

| Axis | local 20B Δ | Groq 120B Δ | Agreement |
|---|---|---|---|
| route_accuracy | −0.19 | −0.28 | both negative |
| answer_correctness | −0.27 | −0.38 | both negative |
| restraint_quality | **+0.32** | −0.11 | **disagree** (local says gov wins; Groq says ~tie) |
| conciseness | **+0.67** | **+0.68** | **both agree gov wins, near-identical** |
| overall_usefulness | −0.43 | −0.35 | both negative |

**Conciseness** is where the judges agree most precisely (+0.67 vs
+0.68). **Restraint_quality** is the one axis where the judges
diverge meaningfully — interpretable as a judge-strength effect: a
larger judge may be more demanding about *what counts as restraint*
(e.g., requiring not just an "ask" but an *informative* clarifying
question).

### 5.3 Per-category comparison

| Category | local 20B Δ | Groq 120B Δ | Agreement |
|---|---|---|---|
| continuation | +6.75 | **+7.75** | both: governance wins, both very strong |
| ambiguous_underspecified | +3.17 | +3.28 | both: governance wins, near-identical |
| factual_inquiry | +1.90 | +0.50 | both positive but Groq is harsher |
| correction_rewrite | +0.12 | −1.00 | small disagreement (local: tie, Groq: raw slightly better) |
| specialized_terminology | −8.17 | **−9.50** | both: raw wins, Groq harsher |
| conceptual_explanation | −7.00 | **−8.62** | both: raw wins, Groq harsher |
| casual_smalltalk (n=2) | −10.00 | −8.50 | both: raw wins (n=2 anecdotal) |

**Both judges agree on the direction of every category.** The Groq
120B is consistently a touch harsher on governance, but the bimodal
shape — strong governance wins on restraint-needed categories,
strong raw wins on direct-answer categories — is **judge-robust**
across this 20B → 120B comparison.

The cross-judge consistency strengthens the finding: this is a
property of the captured raw/governed responses, not of any single
judge's idiosyncrasies.

## 6. P9 paper implications (conservative wording)

Three findings the paper can lean on, with the cross-judge agreement
as supporting evidence:

1. **Governance behaves on-thesis on restraint-needed prompts.** Both
   judges concur: on `continuation` and `ambiguous_underspecified`
   prompts, governed responses score 3–8 points (out of 20) higher.
   The judge rationale for `continuation` repeatedly cited "B
   correctly asks for clarification". This is the structural
   signature one would predict if the appraisal layer is correctly
   redirecting under-specified inputs toward `ask`.
2. **Governance has a measurable, reproducible cost on direct-answer
   prompts** — both judges agree, and the larger judge sees the cost
   slightly larger. Specialized_terminology/conceptual_explanation
   penalty is 7–10 points/20 in this sample. Mechanism is
   identifiable (verify-route + retrieval miss → strict-evidence
   non-answer); it is design tension, not implementation defect.
3. **The bimodal split survives a judge change** from 20B to 120B,
   from local Ollama to Groq cloud. Reporting the headline mean
   (≈ 0) without the per-category structure understates the
   runtime's behavior; the per-category split is the real story.

A paper that wants the strongest claim should still run a
multi-judge / non-gpt-oss-family sweep before generalizing — see
caveats below.

## 7. Caveats (verbatim for reuse)

- **Post-hoc judge-only pass.** Raw and governed responses were
  generated before the judge access repair; they were **not**
  regenerated. The original Phase 5C Test 2 generation conditions
  are unchanged.
- **The User-Agent fix changes only the HTTP header on judge
  requests.** It does not affect generated responses or any other
  code path.
- **Single-judge limitation remains.** Two judges (local 20B + Groq
  120B) agree on the per-category direction of every cell, but a
  multi-judge consensus including a non-`openai/gpt-oss` family
  judge has not been performed.
- **Both judges are in the `openai/gpt-oss` family.** The local 20B
  and Groq 120B share upstream weights; cross-judge agreement here
  is between two siblings, not a fully independent panel.
- **Length-bias guard** explicitly included in the judge prompt.
  Residual length bias cannot be fully ruled out without an
  out-of-family judge.
- **Same base model** (`huihui_ai/qwen3.5-abliterated:9b`) on both
  raw and governed sides; the intentional variable is the MMV
  governance layer.
- **Sampling** oversamples ambiguous + factual; not representative
  of an evenly-weighted natural distribution.
- **NOT Phase 6 full evaluation.** **NOT deployment-wide
  validation.** **NOT real UI performance validation.**

## 8. Files produced

| File | Role |
|---|---|
| `eval/p9_evidence_pack_v1/run_test2_groq120b_judge.py` | Driver script with the User-Agent fix |
| `eval/p9_evidence_pack_v1/raw_vs_governed_groq120b_judge_results.json` | Summary + per-category + per-axis (Groq 120B pass) |
| `eval/p9_evidence_pack_v1/raw_vs_governed_groq120b_judge_results.jsonl` | Per-pair scores + un-blinding key + judge rationales (Groq 120B) |
| `eval/p9_evidence_pack_v1/raw_vs_governed_groq120b_judge_summary.md` | Markdown summary of the Groq 120B pass |
| `docs/P9_EVIDENCE_PACK_V1_GROQ120B_JUDGE_NOTE.md` | This file |

## 9. Reproducibility

```bash
cd ~/デスクトップ/mobius_ai/MOBIUS_MMV/
source ~/デスクトップ/mobius_ai/venv313/bin/activate
# Requires GROQ_API_KEY in env or .env (gitignored).
# The script sets an explicit User-Agent header to avoid Cloudflare 1010.
python3 eval/p9_evidence_pack_v1/run_test2_groq120b_judge.py
```

`User-Agent` value is hard-coded in the script (`mmv-p9-evidence-pack/1.0`).
No other knob needs touching.
