---
doc_status: current
authority: current_reference
scope: mmv_system_overview
last_verified_jst: 2026-05-21
---

# MMV System Overview -- RC3.3 / L0 v8.4

This is the current system overview for the MMV workspace after the
L0 v8.4 / RC3.3 synchronization pass.

## Current Release Lines

| Line | Current pointer | Runtime shape | Status |
|---|---|---|---|
| Small | MMV-S-RC3.3 | 9B `mobius_engine` structural governance plus Small Routing Stabilizer | Smoke-100 candidate engineering RC with controlled Core-500 candidate stress evidence |
| Medium | MMV-M-RC3.3 | Local Gemma 26B under the Large route-transformer / post-validator stack | Bootstrap line with controlled Core-500 candidate stress evidence |
| Large | MMV-L-RC3.3 | 120B route-transformer / post-validator temporal-governance stack | Smoke-100 candidate engineering RC |

## Authority Stack

| Layer | Current file or mechanism |
|---|---|
| L0 current authority | `prompts/l0_integrated_v8_4.md` |
| L0 machine-readable overlay | `prompts/mobius_l0_v8_4_protocol.json` |
| L0 inherited substrate | `prompts/l0_integrated_v8_2.md` and `prompts/mobius_l0_v8_2_protocol.json` |
| L0 compact artifact | `data/evaluation/L0_Essentials_v1_3_core.json` |
| Documentation authority map | `docs/current/DOCS_AUTHORITY_MAP.md` |
| Audit reintegration note | `docs/L0_V8_4_AUDIT_REINTEGRATION_NOTE.md` |
| Box 0 current self-reference index | `data/box_0/index_manifest.json` |
| Box A current mathematical doctrine | `corpus/MMV_Mathematical_Modeling_Doctrine_and_Formalism_EN.md` |

## What Changed At RC3.3

RC3.3 does not mean one identical architecture across Small, Medium, and
Large. It means each line has a documented current governance shape:

- Small keeps the 9B RoutingEngine skeleton and adds a profile-gated
  Small Routing Stabilizer for no-tool route stabilization.
- Large keeps the RC3.2 doctrine path and adds / freezes the v3.1
  temporal-governance route transformer and post-validator.
- Medium is a bootstrap sibling of the Large path using local
  `gemma4:26b`; it has its own controlled Core-500 candidate result, but
  must not inherit Large quality claims.

## Route Vocabulary

The current L0 v8.4 route vocabulary is:

```text
answer
ask
verify
date_bound_answer
re_anchor
abstain
```

`date_bound_answer` is the route for bounded temporal answers when the
system cannot verify live state but can answer honestly within an
explicit date or cutoff boundary.

`re_anchor` is the route for correcting stale, false, or unsupported
premises before answering the usable part of the request.

`explore` is no longer a Core route. It may describe answer style or
interaction shape, but not the route taxonomy.

## Audit / Trace Surface

L0 v8.4 restores audit and trace governance as a current surface.

The local runtime still contains the Phase D audit implementation:

- `src/audit/audit_schema.py`
- `src/audit/audit_emitter.py`
- `src/audit/audit_sampler.py`
- `src/audit/audit_store.py`
- `src/kernel/routing_engine.py` audit hooks

Runtime records are written to `logs/audit_turns.jsonl` when the local
runtime is exercised and audit is available. The runtime reads
`MOBIUS_AUDIT_MODE` with modes `off`, `shadow`, `full`, and
`incident_only`.

Public trace output is bounded: it may show route, evidence posture, sources,
temporal boundary, and claim-boundary notes, but must not expose hidden
chain-of-thought, private scratchpads, private corpora, secret logs, or
patent-sensitive implementation details.

## Box Placement

Box 0 is the self-reference / self-description reference store. It is
not a per-turn prompt injection layer. It is consulted when the runtime
needs canonical self-description or system-design grounding.

Current Box 0 contains:

- `l0_integrated_v8_4.md`
- `mobius_l0_v8_4_protocol.json`
- `l0_integrated_v8_2.md` as inherited constitutional substrate
- legacy complete-system Box 0 documents

Box A is the governed Mobius-foundational reference layer (user/workspace
documents now live in the box_1-3 user space). The current
mathematical-modeling doctrine lives there as a CRITERIA / REFERENCE
artifact for design review, patent drafting, formalization, evaluation
formula design, and MMV internal model explanation.

## L0 Essentials Boundary

L0 Essentials v1.3 is the current compact L0 artifact. It is not
currently injected into Small, Medium, or Large runtime paths.

The prior Condition I evaluation tested L0 Essentials v1.2 as a qwen
9B / structural-governance injection experiment and found that stacking
Essentials on top of structural governance degraded restraint on
ambiguous queries. Therefore Essentials remains available as a compact
artifact, but is not a live layer unless a future evaluation explicitly
re-opens that design.

## Current Mathematical Model Surfaces

The RC3.3 mathematical surfaces are:

- Answer Entitlement and route selection model.
- Box selection and evidence admissibility model.
- Fabrication-risk and grounding sufficiency model.
- Temporal volatility / freshness model.
- Stale-premise re-anchor model.
- Date-bound answer model.
- Audit / trace boundary model.
- Small / Medium / Large release-line separation model.
- Claim-boundary and evaluation-evidence model.

The latest full doctrine is:

`docs/current/MMV_MATHEMATICAL_MODELING_DOCTRINE_RC3_3.md`

## Claim Boundary

Acceptable public phrasing:

> MMV RC3.3 is a candidate engineering line with Smoke-100 evidence for
> Small and Large, plus controlled Core-500 candidate stress evidence for
> Small, Medium, and Large.

Do not claim:

> RC3.3 validates MMV generally.

or:

> Medium RC3.3 inherits Large RC3.3 performance.

or:

> The Core-500 candidate run is independent benchmark validation.
