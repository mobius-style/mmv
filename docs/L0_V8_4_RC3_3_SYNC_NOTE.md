# L0 v8.4 RC3.3 Sync Note

**Status:** current reference
**Date:** 2026-05-21
**L0 authority:** `prompts/l0_integrated_v8_4.md`

This note records why L0 advances from v8.2 / superseded v8.3 to v8.4.

## Decision

L0 v8.4 is the current L0 authority for this workspace.

v8.4 is not a continuation of the Cline-specific v8.3 path. It is an
RC3.3 empirical synchronization release:

- it inherits the v8.2 constitutional substrate;
- it retires v8.3 as a current authority;
- it folds in the route-governance lessons from MMV-L-RC3.3,
  MMV-S-RC3.3, and the OPERATE-FR Smoke-100 S/M/L reports.

## RC3.3 Elements Promoted Into L0

| Element | v8.4 treatment |
|---|---|
| Large RC3.3 route transformer v3.1 | Current Large realization of the temporal-governance ladder |
| Large post-validator | Current Large safeguard against route drift and stale-premise misses |
| Force re-anchor | Canonical stale-premise correction mechanism |
| Small Routing Stabilizer v1 | Current Small realization of RC3.3 routing stabilization |
| `date_bound_answer` | First-class route for bounded temporal answers |
| `re_anchor` | First-class route for stale or false premise correction |
| Stable-control protection | Required guard against over-verification |
| Query-neutrality discipline | Required guard against benchmark-label contamination |
| Audit / trace governance | Restored as a formal v8.4 surface; runtime audit and public trace boundaries are current |
| Small RC3.3 Core-500 candidate | Controlled larger-N stress evidence; exposes weak areas and does not upgrade to independent validation |
| Medium RC3.3 | Bootstrap line with its own controlled Core-500 candidate stress evidence; no transferred Large quality claim |
| Independent Core-500 pending | Mandatory caveat for all RC3.3-derived claims; the 2026-05-21 Core-500 candidate is Smoke-100-derived |

## Canonical Evidence

- `operate-fr-bench/docs/MMV_Large_RC3_3_FREEZE_NOTE.md`
- `operate-fr-bench/docs/MMV_Small_RC3_3_FREEZE_NOTE.md`
- `operate-fr-bench/docs/MMV_Medium_RC3_3_FREEZE_NOTE.md`
- `operate-fr-bench/reports/operate_fr_smoke100_unified_s_m_l_vs_raw.md`
- `operate-fr-bench/reports/operate_fr_smoke100_paired_analysis.md`
- `operate-fr-bench/reports/operate_fr_smoke100_route_transitions.md`
- `operate-fr-bench/reports/operate_fr_smoke100_regression_cases.md`
- `operate-fr-bench/reports/operate_fr_core500_candidate_s_m_l_20260521.md`
- `docs/L0_V8_4_AUDIT_REINTEGRATION_NOTE.md`

## Public Claim Boundary

Use language such as:

> L0 v8.4 synchronizes the Mobius L0 protocol with the MMV RC3.3
> candidate engineering line and the OPERATE-FR Smoke-100 evidence.

Do not use language such as:

> RC3.3 validates MMV generally.

or:

> Medium RC3.3 inherits Large RC3.3 performance.
