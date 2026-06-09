# MMV Core — Freeze Policy

> Historical note (2026-05-21): this policy records the rc1-era Core
> freeze. Current document authority is `docs/current/DOCS_AUTHORITY_MAP.md`;
> current L0 authority is `prompts/l0_integrated_v8_4.md`.

**Status**: Active.
**Adopted**: 2026-04-29 (Phase 5A).
**Anchor commit**: `68dc213` (Phase 4 closure handoff) on top of Phase 4
closure HEAD `c94eee4`.
**Closure tag**: `phase4_close_20260429_0056`.
**Recommended release label**: **MMV Core v0.1-rc1**.

## 1. Purpose

Phase 4 closed on criteria (a) ST1 diminishing returns AND (e) spec
v1.4.1 informational-pass framework — both met. The runtime is now in a
state where additional Core-level work would expand scope rather than
harden the existing surface. This policy freezes MMV Core at the Phase 4
closure state so it can be prepared for public release without further
feature drift, and so Secretary autonomy work can proceed in a clean
addon layer above the frozen Core.

## 2. What is "MMV Core"

For the purposes of this freeze:

- `src/kernel/` — routing, appraisal, KVS, presentation policy, profiles
- `src/adapters/` — Box A/B/C/W adapters; question kernel; ME5 path
- `src/memory/` — Box M/P/S/X; carryover; meta-recall; trajectory
- `src/retrieval/` — pattern lookup, domain corpus, query reformulator
- `src/services/` — ME5 singleton and other shared services
- `src/app/api.py` — public API surface
- `prompts/l0_integrated_v8_2.md` (and historical v8_1)
- `config/pattern_library/` — 139 active + 26 quarantined patterns,
  thresholds, taxonomy
- `data/pattern_library/` — FAISS index (1,252 vectors) + metadata
- `tests/golden_set/` — 200-entry pattern_library_golden_set_v1 +
  505-entry long_tail_v1
- `data/raf/` — ISM corpus (36,282 chunks via Phase 4 ST3 Op-1) and
  associated indices
- Phase 4 closure documentation:
  `docs/PATTERN_LIBRARY_PHASE4_RESULTS.md`,
  `docs/PHASE_4_FINDINGS_FOR_SPEC_v1_5.md`

## 3. What is in scope of the freeze (no new features)

| Area | Frozen state |
|---|---|
| Routing / appraisal / Pattern Library integration | Phase 4 closure as committed |
| Pattern Library size | 139 active / 26 quarantined |
| Long-tail golden set size | 505 entries |
| pattern_library_golden_set_v1 size | 200 entries |
| ISM corpus | 36,282 chunks |
| FAISS / ME5 index state | rebuilt at closure (1,252 PL vectors; ISM/QK rebuilt to 36,282) |
| `WITHIN_SUBTOPIC_STRICT` threshold | 0.92 (calibrated `d7f0d3b`) |
| Phase 4 closure docs | as-committed at `c94eee4` |

These artifacts are the v0.1-rc1 truth-set. They are not extended in
Core after this date.

## 4. What is explicitly out of scope (does not block freeze)

- **Secretary autonomy** — moved to addon layer; see
  [SECRETARY_ADDON_STRATEGY.md](SECRETARY_ADDON_STRATEGY.md).
- **Codex bidirectional integration** — Phase 5+.
- **AGPL release execution** — preparation only; the act of publishing is
  a separate step the user gates manually.
- **Phase 6 evaluation** — full benchmark sweeps deferred.
- **Large-scale data expansion** — no further Pattern Library, golden
  set, or ISM growth in Core.
- **Japanese ratio correction (long_tail_v1)** — known 22.4% vs target
  33.3%; carried into the v0.1-rc1 known-limitations list.
- **LT-2 deep-dive remediation** — recorded as Phase 5 candidate.
- **Sub-topic taxonomy refinement** — the saturation pattern observed
  during Phase 4 M1 motivates this work in Phase 5+, not now.
- **Spec v1.5 file creation** — findings are recorded in
  `docs/PHASE_4_FINDINGS_FOR_SPEC_v1_5.md`; turning that into a formal
  spec file is a Phase 5 task.

## 5. Freeze rule

After this policy is committed and the freeze tag is applied, only the
following classes of change are allowed in Core (i.e., the directories
and artifacts listed in §2):

1. **Bug fixes** — defect repair without behavioral change beyond fixing
   the defect.
2. **Documentation** — README, install/quickstart, license/attribution,
   release notes, comments, this freeze policy itself.
3. **Packaging / build** — pyproject/setup, requirements pinning,
   release artifacts (no code change).
4. **Security cleanup** — dependency upgrades for security advisories,
   secret scrubbing, credential redaction.

Disallowed in Core until Core unfreezes (post-public-release):

- New features in routing / appraisal / KVS / Pattern Library.
- New patterns / new golden entries / new ISM chunks.
- Threshold re-tuning beyond what is required to fix a regression.
- New adapters.
- Any change motivated by Secretary or Codex integration.

If a defect repair would meaningfully alter behavior, it stops the
freeze: the change is escalated to user for review and a new tag/release
candidate (`v0.1-rc2`, etc.) is cut.

## 6. Secretary lives outside Core

Secretary is a post-Core addon and dogfooding layer. It does not ship in
v0.1-rc1. Its boundaries and permission ladder are defined in
[SECRETARY_ADDON_STRATEGY.md](SECRETARY_ADDON_STRATEGY.md). The hard
boundary applicable to this freeze is:

- Secretary code lives outside `src/` (proposed: `addon/secretary/` or a
  separate package).
- Secretary has **no direct mutation rights** on Core artifacts (Pattern
  Library, golden sets, ISM corpus, FAISS indices, prompts).
- Secretary is not auto-installed or auto-enabled by the public Core
  package.

## 7. Release labelling

- Anchor: `c94eee4` (Phase 4 closure docs) on top of `61f4b6f` (b20
  long-tail 505).
- Closure tag: `phase4_close_20260429_0056` (already on `c94eee4`).
- Freeze tag (this Phase 5A work): `mmv_core_v0_1_rc1_freeze_<UTC>` —
  applied at the end of the Phase 5A commit.
- Public-release version: **MMV Core v0.1-rc1** (release-candidate;
  working prototype, not deployment-validated).

## 8. Unfreeze procedure

The freeze ends when one of the following occurs:

1. **Public release ships** — a Core unfreeze is approved post-release
   to begin v0.2 work. Until then, only allowed-class changes (§5) land.
2. **Security/correctness incident** that cannot be repaired within the
   allowed-class envelope — user gates the unfreeze decision explicitly.
3. **User decision** — user can unfreeze at any time by updating this
   policy.

A new freeze policy supersedes this one when amended; the previous
freeze remains visible in git history under this filename.
