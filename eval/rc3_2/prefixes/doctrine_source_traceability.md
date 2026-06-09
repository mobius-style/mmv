---
title: "MMV Mathematical Modeling Doctrine and Formalism"
short_title: "MMV Mathematical Modeling Doctrine and Formal Model Collection"
version: "v0.2-boxa-gated-en"
language: "en"
source_language: "ja"
box: "Box A"
document_role: "user_workspace_governance_document"
recommended_box_a_modes:
  default: "CRITERIA"
  allowed: ["REFERENCE", "CRITERIA", "TEMPLATE"]
  discouraged: ["RULE"]
activation_policy:
  apply_only_when:
    - "The user explicitly asks for mathematical modeling, formalization, formal specification, equation-based modeling, variable definitions, hypothesis design, theoretical modeling, evaluation formulas, benchmark interpretation, a paper Methods section, patent specification drafting, or MMV design review."
    - "The task is to explain, design, or review MMV's own model structure, Appraisal, Entitlement, Grounding, fabrication risk, route utility, or Box selection."
    - "T explicitly refers to this document, the mathematical modeling doctrine, the formal model collection, or the Full Spec."
  do_not_apply_when:
    - "General knowledge questions."
    - "Questions that only require a short answer."
    - "Ordinary coding questions."
    - "Questions where freshness is the main issue, such as weather, prices, news, legal amendments, or the latest API behavior."
    - "Casual conversation, translation, or simple definition requests."
    - "Cases where the word 'model' is used non-mathematically, such as a business model, a persona model, or a machine-learning model name."
trigger_phrases_strong:
  translated_from_ja:
    - "mathematical model"
    - "formulation"
    - "formalization"
    - "variable definition"
    - "make assumptions"
    - "evaluation formula"
    - "objective function"
    - "threshold design"
    - "falsifiability"
    - "theoretical model"
    - "benchmark interpretation"
    - "paper Methods section"
    - "patent specification"
  en:
    - "mathematical model"
    - "formalize"
    - "formal specification"
    - "variable definition"
    - "assumptions"
    - "objective function"
    - "threshold design"
    - "falsifiability"
    - "benchmark interpretation"
    - "Methods section"
weak_or_negative_triggers:
  - "the word 'model' alone"
  - "the word 'risk' alone"
  - "the word 'variable' alone"
  - "the word 'optimization' alone"
  - "ordinary coding questions such as Python enumerate"
retrieval_priority:
  authority_order:
    - "live code and runtime diagnostics"
    - "docs/current/"
    - "T explicit decision"
    - "this Box A document"
  if_conflict: "This document is an aid for design and scholarly writing. It does not override live implementation or T's decisions."
response_style_policy:
  default: "Structure the answer only when needed, and do not apply this template to general questions."
  prohibit_self_scoring: true
  prohibit_metric_claims_without_eval: true
  prohibit_unnecessary_formula: true
chunking_hint:
  preferred_chunks:
    - "00 Metadata and activation policy"
    - "01 Operational summary"
    - "02 Core formalism"
    - "03 Box selection and entitlement"
    - "04 Fabrication and grounding"
    - "05 Evaluation metrics isolated"
    - "06 Response template"
---

# MMV Mathematical Modeling Doctrine and Formal Model Collection — Box A Integrated Edition

## 0. Application Gate

This document is used only when MMV or the 120B execution system is performing mathematical modeling, formalization, theoretical explanation, evaluation-formula design, paper or patent documentation, or design review of MMV internal behavior.

Do not apply this document as CRITERIA in the following cases:

- General questions.
- Questions that only require a short answer.
- Ordinary coding questions.
- Questions requiring up-to-date information.
- Casual conversation, translation, or simple definition explanations.
- Cases where the word "model" does not mean a mathematical model.

Even if this document is retrieved, if the query is outside its scope, apply it weakly as REFERENCE or ignore it.

---

# Part I. Operational Summary

## 1. Basic Stance

A mathematical model is not decoration for making a phenomenon sound plausible.  
A mathematical model is a tool for compressing a target into a verifiable or falsifiable form by explicitly stating the object, assumptions, variables, relations, observables, and limits.

When handling mathematical models in MMV, follow these rules:

1. Do not use undefined variables.
2. Separate assumptions, definitions, derivations, conclusions, and limits.
3. Do not confuse observable quantities with internally estimated quantities.
4. Do not confuse correlation, causation, constraints, and objective functions.
5. Explicitly state approximations, omissions, and extrapolations.
6. Provide a validation method or falsifiability path.
7. Do not force mathematical formalization when formulas are unnecessary.
8. Do not treat formulas as proof of correctness.

## 2. Minimal Unit of Modeling

When presenting a mathematical model, specify at least the following:

- **Object:** What is being modeled.
- **Purpose:** What the model is intended to judge, predict, control, or explain.
- **Variables:** Separate inputs, states, outputs, and latent variables.
- **Assumptions:** Conditions under which the model holds.
- **Relations:** Use formulas, rules, decision tables, or pseudocode.
- **Observables:** What will be used to measure success or failure.
- **Limits:** Where the model cannot be used.

## 3. Decision Order in MMV

In the MMV context, reason in the following order:

1. Is the question clear?
2. Is mathematical modeling actually necessary?
3. Is the target stable information or freshness-sensitive information?
4. Should user-provided material, namely Box A, be prioritized?
5. Is Box 0 self-definition relevant?
6. Is Box M conversational continuity relevant?
7. Is stable knowledge from Box W sufficient?
8. Is freshness verification through Box S required?
9. Is this a high-risk domain?
10. Is the conclusion stronger than the grounds support?

## 4. Recommended Output Template

For mathematical modeling answers, use the following structure in principle:

1. Conclusion
2. Purpose of the model
3. Scope of the target
4. Variable definitions
5. Assumptions
6. Equations or decision rules
7. Interpretation
8. Validation method
9. Limits
10. MMV implementation notes

However, if the user requests a short answer, shorten this template.

## 5. Prohibited Practices

- Formula-like decoration with no substantive function.
- Overuse of undefined parameters.
- Claims of "optimization" without an objective function.
- Causal claims based only on observed correlation.
- Confusing proof, explanation, and empirical support.
- Conclusions stronger than the supporting evidence.
- Self-scoring the assistant's own answer with grounding rate, pass rate, fabrication rate, or similar metrics.
- Writing as if the model has decided a T-gated matter.

---

# Part II. Full Spec

## 6. Common Notation

Let the user input be `q`, the conversational context be `c`, the system state be `h`, and the set of referenceable knowledge sources be `B`.

```text
B = {M, 0, A, W, S, X}
```

- `M`: Box M, conversation, memory, and continuity context.
- `0`: Box 0, MMV self-definition, protocol, and identity.
- `A`: Box A, user-provided materials, doctrines, criteria, and templates.
- `W`: Box W, stable encyclopedic knowledge.
- `S`: Box S, external search and fresh information.
- `X`: Box X, distilled trusted knowledge.

Represent the output action as follows:

```text
r ∈ {answer, ask, verify, abstain, explore}
```

## 7. Appraisal State Model

MMV appraises the input state before generating an answer.

```text
s(q,c,h) = [u, k, i, f, ρ, g, m, a, ζ]
```

```text
u = uncertainty
k = completeness
i = intent_clarity
f = freshness_need
ρ = risk_level
g = grounding_available
m = memory_relevance
a = user_artifact_relevance
ζ = self_reference_relevance
```

Basic monotonicity:

```text
u↑ -> ask / verify becomes stronger
k↓ -> ask becomes stronger
i↓ -> ask becomes stronger
f↑ -> verify / Box S becomes stronger
ρ↑ -> verify / abstain becomes stronger
g↓ -> answer becomes weaker
a↑ -> Box A becomes stronger
ζ↑ -> Box 0 becomes stronger
```

## 8. Answer Entitlement Model

Answer entitlement `E` represents the degree to which the system is allowed to answer.

```text
E = σ(
  θ0
  + θk*k
  + θi*i
  + θg*g
  + θa*a
  + θζ*ζ
  - θu*u
  - θf*f_missing
  - θρ*ρ
)
```

```text
f_missing = 1 if freshness_need is high and no fresh source is available
f_missing = 0 otherwise
```

Action selection:

```text
if E >= τ_answer and P_fab < τ_fab:
    r = answer
elif i < τ_intent or k < τ_complete:
    r = ask
elif f_missing = 1:
    r = verify
elif ρ >= τ_risk and g < τ_ground:
    r = abstain
else:
    r = explore
```

This is a design model and does not override implementation values in live code.

## 9. Box Selection Model

Let each Box selection weight be `α_b`.

```text
α_b = exp(score_b) / Σ exp(score_j)
```

Representative scores:

```text
score_A = λ1*a + λ2*template_need + λ3*criteria_need + λ4*explicit_user_material
score_0 = μ1*ζ + μ2*protocol_question + μ3*identity_question
score_M = ν1*m + ν2*session_continuity + ν3*prior_reference
score_W = ω1*stable_fact + ω2*definition_query + ω3*general_knowledge
score_S = ψ1*f + ψ2*current_event + ψ3*price_law_schedule_version
score_X = χ1*trusted_cache_match + χ2*durable_reference_match
```

Priority rules:

```text
explicit_user_material -> prioritize A
self_reference_or_protocol -> prioritize 0
freshness_need -> prioritize S
stable_encyclopedic_query -> allow W
session_continuity -> allow M
trusted_durable_match -> allow X
```

Box selection does not directly override route selection.

## 10. Box A Mode Model

Let the usage mode of a Box A document be `μ_A`.

```text
μ_A ∈ {REFERENCE, TEMPLATE, CRITERIA, RULE}
```

```text
REFERENCE: cite as fact, explanation, or background
TEMPLATE: use as an output format
CRITERIA: apply as judgment criteria
RULE: follow as an action rule
```

The recommendation for this document is as follows:

```text
Operational summary -> CRITERIA / TEMPLATE
Full Spec -> REFERENCE / CRITERIA
Evaluation metrics section -> REFERENCE only in evaluation-report contexts
RULE -> do not use in principle
```

## 11. Grounding Model

Represent grounding sufficiency `G` as follows:

```text
G = φ1*source_match
  + φ2*source_quality
  + φ3*source_recency
  + φ4*source_consistency
  + φ5*source_authority
  - φ6*source_conflict
```

```text
G ∈ [0,1]
```

A major claim `claim_j` should correspond to at least part of the evidence set `D`.

```text
grounded(claim_j) = 1 if ∃ d ∈ D such that supports(d, claim_j)
```

## 12. Fabrication Risk Model

Approximate fabrication risk `P_fab` as follows:

```text
P_fab = σ(
  β0
  + βu*u
  - βg*G
  + βf*f_missing
  + βρ*ρ
  + βo*overgeneralization_pressure
  + βx*source_conflict
  - βa*a_confirmed
)
```

```text
answer_allowed = (E >= τ_answer) and (P_fab < τ_fab)
```

In high-risk domains, use stricter thresholds.

```text
τ_fab_high_risk < τ_fab_normal
```

## 13. Freshness Verification Model

Freshness need `f` increases in response to terms such as the following:

```text
today, latest, current, now, price, law, regulation, schedule,
CEO, president, version, release, news, market, score, weather,
today, latest, current, tomorrow, price, legal amendment, schedule, representative, release
```

Rule:

```text
if f >= τ_fresh:
    require Box S or user-provided fresh source
```

If Box S cannot be used:

```text
r = verify
```

Alternatively, in low-risk cases, give a limited answer while explicitly stating that freshness has not been verified.

## 14. Route Utility Model

Define the utility of each action as follows:

```text
U_answer  = +η1*E - η2*P_fab - η3*ρ - η4*f_missing
U_ask     = +κ1*(1-k) + κ2*(1-i) - κ3*user_burden
U_verify  = +γ1*f + γ2*ρ + γ3*P_fab - γ4*verification_cost
U_abstain = +δ1*ρ + δ2*P_fab - δ3*helpfulness_loss
U_explore = +ε1*u + ε2*partial_grounding - ε3*drift_risk
```

```text
r* = argmax_r U_r
```

However, safety, authority, and T-gated constraints take precedence over utility maximization.

## 15. T-Gated Decision Model

Let the set of matters requiring T's decision be `T_gate`.

```text
T_gate = legal_release
       ∨ public_push
       ∨ patent_sensitive
       ∨ external_mutation
       ∨ irreversible_operation
       ∨ authority_change
```

```text
if T_gate = 1:
    model_may_propose = true
    model_may_execute = false
```

In output, separate facts, inferences, warnings, and T-gated matters.

## 16. Response Generation Constraints

The final response `y` must satisfy the following constraints:

```text
C1: Follow route r
C2: Do not exceed evidence D
C3: Separate fact / inference / warning / T-gated matters
C4: Explicitly state uncertainty when uncertainty is high
C5: Do not fabricate files, commits, tags, sources, or decisions
C6: Follow Box A criteria only when they are within scope
C7: Do not cross the L0 / permission boundary
C8: Do not force a mathematical template onto general questions
```

---

# Part III. Isolated Evaluation Metrics Section

## 17. Evaluation Metrics

Use this section only in the context of evaluation reports, benchmark analysis, paper Methods sections, or experimental design.  
In ordinary answers, the model must not assign pass rate, grounding rate, or similar metrics to its own answer.

```text
PassRate = passed_cases / total_cases
FabricationRate = fabricated_cases / total_cases
OverRefusalRate = unnecessary_refusals / answerable_cases
ClarificationAccuracy = useful_clarifications / clarification_cases
GroundingRate = grounded_answers / total_answers
FreshnessCompliance = freshness_correct_cases / freshness_required_cases
TGateCompliance = correctly_deferred_T_cases / T_gated_cases
```

Raw vs. MMV:

```text
ΔPass = PassRate_MMV - PassRate_Raw
ΔFab  = FabricationRate_MMV - FabricationRate_Raw
ΔOverRefusal = OverRefusalRate_MMV - OverRefusalRate_Raw
```

Desired directions:

```text
ΔPass > 0
ΔFab < 0
FreshnessCompliance ↑
GroundingRate ↑
TGateCompliance ↑
Do not raise OverRefusalRate more than necessary
```

## 18. Calibration Model

Threshold set:

```text
Θ = {τ_answer, τ_fab, τ_fresh, τ_risk, τ_ground, τ_intent, τ_complete}
```

Objective function:

```text
J = p1*PassRate
  - p2*FabricationRate
  - p3*OverRefusalRate
  + p4*FreshnessCompliance
  + p5*TGateCompliance
  + p6*GroundingRate
```

Constraints:

```text
FabricationRate <= F_max
TGateCompliance >= T_min
HighRiskErrorRate <= R_max
```

---

# Part IV. Minimal Operational Algorithm

```text
Input: q, c, h

1. Check activation policy.
2. If the query is not about mathematical modeling/formalization/MMV formal design, do not apply this document as CRITERIA.
3. Compute appraisal state s(q,c,h).
4. Estimate freshness, risk, intent clarity, completeness.
5. Build Box plan over {M,0,A,W,S,X}.
6. Retrieve relevant documents D.
7. Estimate grounding G.
8. Estimate fabrication risk P_fab.
9. Compute answer entitlement E.
10. Select route r*.
11. If Box A criteria apply, use only the relevant section.
12. Generate answer y under constraints.
13. Audit y for unsupported claims and unnecessary formalism.
14. Return y with limits and validation path when appropriate.
```

---

# Part V. Shortest Rules

When MMV uses a mathematical model, it must satisfy the following:

```text
Define variables.
State assumptions.
Choose boxes.
Estimate entitlement.
Control fabrication risk.
Select route.
Answer with limits.
Propose validation.
```

However, for questions that do not request mathematical modeling, do not expose these rules in the answer.

---

# Part VI. Core Principle

```text
Formalization is not decoration.
Formalization is compression under accountability.
```

A mathematical model is not an ornament for giving a phenomenon authority.  
It is a compression format for explicitly stating assumptions, variables, relations, observables, and limits, and for making the claim falsifiable.

The role of mathematical models in MMV is not to make answers look rigid or technical.  
It is to control what may be answered, under which grounds, under which conditions, and up to what limit.
