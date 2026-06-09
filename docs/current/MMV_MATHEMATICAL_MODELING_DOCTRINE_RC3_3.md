---
doc_status: current
authority: current_reference
scope: mmv_mathematical_modeling_doctrine
last_verified_jst: 2026-05-21
box_target: Box A
recommended_box_a_modes: [CRITERIA, REFERENCE, TEMPLATE]
---

# MMV Mathematical Modeling Doctrine and Formal Model Collection -- RC3.3

This document supersedes the older Box A `v0.2-boxa-gated-en`
mathematical-modeling doctrine as the current RC3.3 / L0 v8.4 modeling
surface.

It is used when the user asks for mathematical modeling, formalization,
theoretical explanation, evaluation-formula design, paper or patent
drafting, or design review of MMV internal behavior. It should not be
applied to ordinary short-answer questions, casual conversation,
translation, or freshness-first questions.

## 1. Modeling Discipline

A mathematical model is a compression tool for making a target
inspectable. It must identify the object, purpose, assumptions,
variables, relations, observables, limits, and validation path.

Do not use formulas as decoration. Do not score MMV's own output unless
an evaluation protocol is explicitly in scope. Do not turn a design
model into an empirical claim without evidence.

## 2. Current System State Vector

Let a user input be `q`, conversational context be `c`, runtime state be
`h`, and available evidence surfaces be `B`.

```text
B = {M, 0, A, W, S, C, X}
```

Where:

```text
M = session / memory / continuity context
0 = Box 0 self-reference and system authority
A = Box A Mobius-foundational reference material (user/workspace documents -> box_1-3 user space)
W = stable encyclopedic knowledge
S = search quarantine / transient external search holding surface
C = live verification path
X = curated durable external knowledge
```

For no-tool OPERATE-FR evaluations, the effective evidence set is much
narrower because retrieval is intentionally disabled. In that condition,
the route-governance wrappers must not be described as retrieval-based.

## 3. Route Set

The current L0 v8.4 route set is:

```text
R = {answer, ask, verify, date_bound_answer, re_anchor, abstain}
```

`explore` is not a Core route. It may be an answer shape or user-facing
mode, but it must not appear as a route in the RC3.3 route model.

## 4. Appraisal State

Represent the pre-answer appraisal state as:

```text
s(q,c,h) = [u, k, i, f, rho, g, m, a, zeta, p, d]
```

Where:

```text
u    = uncertainty
k    = completeness of the request
i    = intent clarity
f    = freshness / temporal volatility need
rho  = risk level
g    = grounding availability
m    = memory relevance
a    = user-artifact relevance
zeta = self-reference relevance
p    = premise validity
d    = date-bound answer sufficiency
```

Monotonic tendencies:

```text
u up       -> ask / verify pressure increases
k down     -> ask pressure increases
i down     -> ask pressure increases
f up       -> verify or date_bound_answer pressure increases
rho up     -> verify / abstain pressure increases
g down     -> answer entitlement decreases
a up       -> Box A priority increases
zeta up    -> Box 0 priority increases
p down     -> re_anchor pressure increases
d up       -> date_bound_answer becomes more viable
```

## 5. Answer Entitlement

Answer entitlement `E` estimates whether the system may answer directly.

```text
E = sigma(
    theta_0
  + theta_k*k
  + theta_i*i
  + theta_g*g
  + theta_a*a
  + theta_z*zeta
  + theta_p*p
  + theta_d*d
  - theta_u*u
  - theta_f*f_missing
  - theta_r*rho
)
```

Where:

```text
f_missing = 1 when freshness need is high and no live verification is available
f_missing = 0 otherwise
```

This formula is conceptual. It does not override the live code or the
measured behavior of any release line.

## 6. Route Selection Ladder

A compact route ladder:

```text
if safety_relevant and grounding is insufficient:
    r = abstain
elif intent or request constraints are insufficient:
    r = ask
elif premise validity is low:
    r = re_anchor
elif freshness need is high and live verification is available:
    r = verify
elif freshness need is high and live verification is unavailable
     and a bounded answer is honest:
    r = date_bound_answer
elif answer entitlement is sufficient:
    r = answer
else:
    r = ask or verify depending on whether missing information is user-side or world-side
```

## 7. Date-Bound Answer Model

`date_bound_answer` is appropriate when:

```text
f is high
live verification is unavailable or intentionally disabled
the model can state a bounded answer without pretending present certainty
the boundary is explicit
```

The answer must disclose the boundary:

```text
as of <date/cutoff/source horizon>, X; this may have changed
```

It must not make unqualified present-tense claims about volatile facts.

## 8. Re-Anchor Model

`re_anchor` is appropriate when:

```text
p < tau_premise
```

Typical cases:

- A prompt embeds a false current premise.
- A prompt treats a past or hypothetical event as current fact.
- A prompt asks the model to build on a stale entity state.

The re-anchor response has three parts:

```text
1. identify the premise problem
2. state the corrected or bounded anchor
3. answer only the part that remains legitimate
```

## 9. Box Selection Model

Let each evidence surface receive a score:

```text
score_b = relevance_b + authority_b + freshness_fit_b - risk_penalty_b
```

Then:

```text
alpha_b = exp(score_b) / sum_j exp(score_j)
```

Representative priority:

```text
zeta high -> Box 0
a high    -> Box A
f high    -> Box C / live verification
stable factual query -> Box W or X
conversation continuation -> Box M
```

Box 0 and Box A are not interchangeable:

- Box 0 is self-reference / system authority.
- Box A is Mobius-foundational reference governance (user/workspace artifacts -> box_1-3 user space).

## 10. Release-Line Separation Model

RC3.3 must be modeled as a family of release-line mechanisms, not a
single implementation.

```text
Small  = 9B RoutingEngine + v2 post-cal + Small Routing Stabilizer
Large  = RC3.2 doctrine path + route_transformer_v3_1 + post_validator
Medium = Large stack shape + local gemma4:26b bootstrap emitter
```

Consequences:

- Small claims do not automatically transfer to Large.
- Large claims do not automatically transfer to Medium.
- Small RC3.3 and Medium RC3.3 now have their own controlled Core-500
  candidate stress results, but neither inherits Large performance.
- Independent Core-500 remains pending unless explicitly run and recorded;
  the 2026-05-21 run is a Smoke-100-derived controlled expansion.

## 11. Fabrication Risk

Let fabrication risk be:

```text
F = phi_0 + phi_u*u + phi_f*f_missing + phi_r*rho
    - phi_g*g - phi_p*p - phi_d*d
```

The system must reduce answer strength when `F` rises. The allowed
response may shift from `answer` to `date_bound_answer`, `verify`,
`ask`, `re_anchor`, or `abstain`.

## 12. Evaluation Claim Model

An empirical claim is valid only when:

```text
claim_scope <= evidence_scope
```

Examples:

```text
Smoke-100 Small evidence -> Small Smoke-100 candidate claim
Smoke-100 Large evidence -> Large Smoke-100 candidate claim
Small Core-500 candidate evidence -> Small controlled stress evidence only
Medium Core-500 candidate evidence -> Medium controlled stress evidence only
Controlled Core-500 candidate run -> no independent Core-500 validation claim
```

## 13. Output Template For Modeling Tasks

Use this structure when the user asks for formalization:

```text
1. Object
2. Purpose
3. Variables
4. Assumptions
5. Relations / equations / decision ladder
6. Observables
7. Validation path
8. Limits
9. Current implementation notes
```

Shorten it when the user asks for a concise answer.

## 14. Non-Claims

Do not claim:

- Essentials is currently injected into Small, Medium, or Large.
- Medium RC3.3 has Large RC3.3 performance.
- Box 0 is a per-turn prompt injection layer.
- Box A mathematical doctrine overrides live code.
- `explore` is a current Core route.

## 15. Current Evidence Anchors

- `docs/current/MMV_SYSTEM_OVERVIEW_RC3_3.md`
- `docs/current/DOCS_AUTHORITY_MAP.md`
- `prompts/l0_integrated_v8_4.md`
- `prompts/mobius_l0_v8_4_protocol.json`
- `operate-fr-bench/docs/MMV_Small_RC3_3_FREEZE_NOTE.md`
- `operate-fr-bench/docs/MMV_Large_RC3_3_FREEZE_NOTE.md`
- `operate-fr-bench/docs/MMV_Medium_RC3_3_FREEZE_NOTE.md`
- `operate-fr-bench/reports/operate_fr_smoke100_unified_s_m_l_vs_raw.md`
- `operate-fr-bench/reports/operate_fr_smoke100_paired_analysis.md`
