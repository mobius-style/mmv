---
doc_status: current
authority: current_reference
scope: document_authority_map
last_verified_jst: 2026-06-09
---

# Documentation Authority Map -- Current

This file records which documents are current authority after the L0 v8.4
RC3.3 sync.

Current L0 behavior is the **v8.4.1** reason-aware abstain point-revision
(2026-06-05, abstain behavior only; live on public). v8.4.1 deliberately
**retains the v8.4 file names** (`prompts/l0_integrated_v8_4.md`, `TRY_MOBIUS.md`,
`L0_Essentials_v1_3_core.json`) for reference stability, so the v8.4-named
authority files in the table below already carry the v8.4.1 behavior. v8.4.1 is
an overlay on the v8.4 structural protocol, **not** a new protocol version —
there is no separate `l0_integrated_v8_4_1` file by design. Where `TRY_MOBIUS.md`
or other surfaces say "v8.4.1", read it as this point-revision, not a conflict
with the v8.4 authority pointer. See `docs/L0_v8_4_1_ABSTAIN_VALIDATION.md`.

## Current Authority

| Surface | Current authority |
|---|---|
| System overview | `docs/current/MMV_SYSTEM_OVERVIEW_RC3_3.md` |
| L0 protocol | `prompts/l0_integrated_v8_4.md` |
| L0 machine-readable overlay | `prompts/mobius_l0_v8_4_protocol.json` |
| L0 abstain point-revision (current behavior) | `docs/L0_v8_4_1_ABSTAIN_VALIDATION.md` — v8.4 → v8.4.1, abstain behavior only; v8.4 filenames retained |
| L0 Essentials compact artifact | `data/evaluation/L0_Essentials_v1_3_core.json` |
| L0 Essentials update note | `docs/L0_ESSENTIALS_V1_3_UPDATE_NOTE.md` |
| Mathematical modeling doctrine | `docs/current/MMV_MATHEMATICAL_MODELING_DOCTRINE_RC3_3.md` |
| Frontier chat trial pack | `docs/current/MMV_FRONTIER_CHAT_TRIAL_PACK_RC3_3_L0V8_4.md` |
| L0 v8.3 status | `docs/L0_V8_3_SUPERSEDED_NOTE.md` |
| RC3.3 sync rationale | `docs/L0_V8_4_RC3_3_SYNC_NOTE.md` |
| Audit / trace reintegration | `docs/L0_V8_4_AUDIT_REINTEGRATION_NOTE.md` |
| Patent / public release gate | `docs/current/PATENT_RELATED_FILE_INVENTORY.md` |
| Box namespace / naming | `docs/BOX_NAMESPACE.md` |
| Large release pointer | `operate-fr-bench/releases/large/current.yaml` |
| Small release pointer | `operate-fr-bench/releases/small/current.yaml` |
| Medium release pointer | `operate-fr-bench/releases/medium/current.yaml` |

## Historical Documents

These remain evidence but are not current authority when they conflict with
the table above:

| Document | Current reading |
|---|---|
| `prompts/l0_integrated_v8_2.md` | inherited constitutional substrate and historical implementation-reality reference |
| `prompts/mobius_l0_v8_2_protocol.json` | inherited machine-readable substrate; superseded as current protocol by v8.4 overlay |
| `data/evaluation/L0_Essentials_v1_2_core.json` | historical compact artifact used by prior evaluations; superseded as current compact artifact by v1.3 |
| v8.3 Cline / `mobius_json_8_3` documents in git history | internal superseded prototype; Cline-specific path abandoned |
| `docs/MMV_CORE_V0_1_RC1_RELEASE_NOTES.md` | rc1 historical release notes |
| `docs/PUBLIC_RELEASE_READINESS_CHECKLIST.md` | rc1-era readiness checklist |
| `docs/MMV_CORE_FREEZE_POLICY.md` | rc1-era freeze policy; use current release pointers for RC3.3 status |

## Reading Rule

1. For current L0 behavior, read the v8.4 protocol files — they carry the
   v8.4.1 abstain point-revision (behavior-only; see
   `docs/L0_v8_4_1_ABSTAIN_VALIDATION.md`).
2. For inherited constitutional background, read v8.2.
3. For RC3.3 empirical claims, read OPERATE-FR freeze notes and Smoke-100
   reports.
4. For publication/legal gates, read `docs/current/PATENT_RELATED_FILE_INVENTORY.md`.
5. For audit / trace behavior, read `docs/L0_V8_4_AUDIT_REINTEGRATION_NOTE.md`.
6. Do not treat Cline-specific v8.3 materials as current release guidance.

## Audit / Trace Reintegration

Updated on 2026-05-21.

L0 v8.4 formally restores audit and trace governance as a current surface.
The implementation is not merely historical: `src/audit/*`,
`src/kernel/routing_engine.py` audit hooks, and `logs/audit_turns.jsonl`
remain present. The current reading is:

- runtime audit may emit structured JSONL records when the local runtime is
  exercised;
- public trace appendices must remain concise and must not expose hidden
  chain-of-thought;
- prompt-level trial packs may emulate a short public audit appendix on
  request, but must not claim hidden runtime logs or Box traces are available;
- audit records support reviewability, not correctness proof.

## L0 Essentials Runtime Scope Check

Checked on 2026-05-21 with `scripts/check_mmv_essentials_scope.py`.

Current reading: L0 Essentials is a **compact artifact and prior
Small-line injection experiment**, not a current Medium/Large Box contract.

- The recorded Condition I evaluation applies
  `L0_Essentials_v1_2_core.json` to **qwen 9B + structural governance**.
- `CLAUDE.md` records the outcome: do **not** stack L0 Essentials prompt
  injection on top of the v2.1 structural-governance path without a new
  evaluation, because it degraded restraint on ambiguous queries.
- Current Small RC3.3 uses the 9B `mobius_engine` path plus the
  `small_routing_stabilizer`, but its profile does not directly inject
  L0 Essentials.
- Current Large RC3.3 and Medium RC3.3 profiles use the
  route-transformer / post-validator path and do not reference
  L0 Essentials.

Therefore `data/evaluation/L0_Essentials_v1_3_core.json` is current as a
compact L0 artifact, but it should not be described as currently loaded
into Box 0 for Medium/Large or as a live Medium/Large runtime layer.

## Box 0 Self-Reference Authority

Updated on 2026-05-21.

Box 0 now contains the current L0 v8.4 authority files for
self-reference / self-description retrieval:

- `corpus_box_0/MMV_SYSTEM_OVERVIEW_RC3_3.md`
- `corpus_box_0/l0_integrated_v8_4.md`
- `corpus_box_0/mobius_l0_v8_4_protocol.json`

The Box 0 FAISS index was rebuilt with
`intfloat/multilingual-e5-large`, preserving v8.2 as inherited
constitutional substrate:

- `data/box_0/index_manifest.json` lists both v8.4 current authority
  files and `l0_integrated_v8_2.md`.
- `scripts/check_box0_l0_authority.py` verifies the manifest contract.
- `tests/test_box_0_v8_4_ingest.py` verifies corpus, manifest, and chunk
  signatures.

Runtime boundary: this makes v8.4 available to Box 0 self-reference
retrieval. It does not change the OPERATE-FR no-tool Medium/Large
evaluation path, which remains route-transformer / post-validator based.

## Box A Mathematical Modeling Doctrine

Updated on 2026-05-21.

Box A now contains the current system overview and mathematical-modeling
doctrine as governed workspace/current documents:

- `docs/current/MMV_SYSTEM_OVERVIEW_RC3_3.md`
- Box A source copy:
  `corpus/MMV_SYSTEM_OVERVIEW_RC3_3.md`
- `docs/current/MMV_MATHEMATICAL_MODELING_DOCTRINE_RC3_3.md`
- Box A source copy:
  `corpus/MMV_Mathematical_Modeling_Doctrine_and_Formalism_EN.md`

The Box A index was rebuilt with `intfloat/multilingual-e5-large` from
these RC3.3 / L0 v8.4-aware documents. It now covers the current S/M/L
system overview, route set,
date-bound answer model, re-anchor model, Box selection model,
release-line separation model, and evidence claim-boundary model.

Use `scripts/check_current_overview_and_math.py` to verify that the
current overview and mathematical doctrine are present and indexed.

## Frontier Chat Trial Pack

Added on 2026-05-21.

The paste-ready trial artifact is:

- `docs/current/MMV_FRONTIER_CHAT_TRIAL_PACK_RC3_3_L0V8_4.md`
- metadata:
  `docs/current/MMV_FRONTIER_CHAT_TRIAL_PACK_RC3_3_L0V8_4.sources.json`

This is a prompt-level demonstration bundle for frontier model chat
windows. It integrates L0 v8.4, L0 Essentials v1.3, the RC3.3 system
overview, and the current mathematical-modeling doctrine into one
copy/paste instruction pack.

Boundary: it is not the full MMV runtime and must not be described as
structural RoutingEngine, Box retrieval, post-validator execution, or
independent Core-500 validation evidence. The 2026-05-21 Core-500 candidate
evidence is a Smoke-100-derived controlled stress run recorded separately.
