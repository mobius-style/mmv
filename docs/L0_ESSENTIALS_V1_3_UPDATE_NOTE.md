# L0 Essentials v1.3 Update Note

**Status:** current compact Essentials artifact
**Date:** 2026-05-21
**File:** `data/evaluation/L0_Essentials_v1_3_core.json`
**Aligned L0:** v8.4

L0 Essentials v1.3-core updates the compact prompt-level governance artifact
after the L0 v8.4 / MMV RC3.3 sync.

## What Changed From v1.2

- Adds the v8.4 route vocabulary:
  `answer`, `ask`, `verify`, `date_bound_answer`, `re_anchor`, `abstain`.
- Moves `explore` out of Core route status and treats it as an answer-shaping
  mode.
- Adds explicit stale-premise / false-premise `re_anchor` duty.
- Adds `date_bound_answer` for temporally scoped answers.
- Adds client-agnostic agentic-boundary rules:
  tool readiness before answer, grounded vocabulary, and profile separation.
- Records that the Cline-specific v8.3 path is superseded.
- Separates authorship and rights/licensing:
  author `Taiko Toeda`; rights/license holder `MOBIUS LLC`.
- Adds the v8.4 audit / trace boundary for prompt-level Essentials use:
  concise public audit appendix may be provided on request, but hidden runtime
  logs, chain-of-thought, Box traces, benchmark row IDs, and fabricated audit
  records remain prohibited.
- Preserves the warning that Essentials prompt injection should not be stacked
  on top of full structural governance.

## Relationship To v1.2 Evaluations

The v1.2 evaluation files remain valid historical evidence for the tested
artifact:

- `data/evaluation/eval_v8_essentials_v1_2_500q_summary.md`
- `data/evaluation/eval_v8_essentials_v1_2_500q_cond_I_summary.md`

Those results do not automatically transfer to v1.3. A new prompt-injection
evaluation is required before quoting v1.3 as empirically measured.

## Use Boundary

Use v1.3 as:

- the current compact reference for L0 v8.4 Essentials;
- a prompt-level governance artifact for controlled evaluations where
  structural routing is absent;
- a human-readable compressed map of the v8.4 route rules.

Do not use v1.3 to justify adding an Essentials prompt on top of the full MMV
RoutingEngine stack without a new layering evaluation.
