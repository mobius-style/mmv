---
doc_status: current
authority: canonical
scope: setup_and_release_gaps
last_verified_utc: 2026-05-16
overall_verdict: PARTIAL/YELLOW
---

# Setup gaps — current

Small remaining gaps that block neither runtime nor RC3 build but
that T may want to resolve before a public-push window. Each item
here is a T-gated cosmetic; none is a runtime or import blocker.

## Cosmetic version labels

| Item | Where | Action (T-gated) |
|---|---|---|
| `pyproject.toml` `version` field | repo root | bump to `0.1rc3` (or `0.1.0rc3`, depending on T's PEP-440 preference) if T wants the wheel/sdist metadata to match the current tag |
| `THIRD_PARTY_LICENSES.md` header version line, if any | `docs/THIRD_PARTY_LICENSES.md` | optional sync; the legal content does not change |
| `README.md` "current release" badge / line, if present | `README.md` top section | optional rewrite to reference RC3 once T is ready to publish |

These are pure metadata changes. They do not affect anything tested
by Stage 0-A through 0-F regression smokes.

## RC3 release notes

| Item | Where | Action |
|---|---|---|
| RC3 release-notes draft | `docs/MMV_CORE_V0_1_RC3_RELEASE_NOTES.md` (does not yet exist) | T to draft; Secretary CLI can produce a starter brief via `--brief-type release_brief` |

The Secretary CLI's `release_brief` output is a usable first draft.
T should review and edit before publishing.

## OpenCode-related note (NOT a release gap)

OpenCode (Stage 0-F) was installed user-local at `~/.opencode/bin/`
under the operator's `$HOME`. It is **outside the repo** and is
**not** part of the public release tarball. Future fresh-shell use
of OpenCode requires:

```bash
export PATH="$HOME/.opencode/bin:$PATH"
export GROQ_API_KEY="$(grep '^GROQ_API_KEY=' .env | cut -d= -f2-)"
```

This is operator convenience, not a release gap.

## Standard-benchmark dependencies

| Item | Where | Action |
|---|---|---|
| `lm-evaluation-harness 0.4.11` install in `venv_bench` | bench clone (`MOBIUS_MMV_BENCH_RC3/`) | already installed; bench-only, NOT in the public release tarball |
| Bench-clone smoke artefacts | bench clone | not in the public tarball; only the source-repo `eval/phase5*` summaries are |

Bench dependencies are operator-only.

## Untracked working-tree paths

| Item | Count | Recommendation |
|---|---|---|
| `tests/` untracked | 67 | **Defer to v0.2** (Stage 0-C T-decision brief default) |
| `scripts/` untracked | 40 | Defer to v0.2 |
| `eval/` untracked | 24 | Defer to v0.2 |
| `docs/` untracked | 12 | Defer to v0.2 |
| `prompts/`, `corpus/`, `config/` | small | Defer to v0.2 |

Detailed analysis + Option A/B/C in
[`eval/secretary_stage0c/t_decision_brief_untracked_files.md`](../../eval/secretary_stage0c/t_decision_brief_untracked_files.md).

## What "READY" would look like

For the cosmetic gaps above:

- `pyproject.toml` version updated (T-gated; small).
- `docs/MMV_CORE_V0_1_RC3_RELEASE_NOTES.md` drafted and reviewed
  (T-gated; medium).
- README "current release" line synced (T-gated; small).

For the larger T-gated items, see `docs/current/RELEASE_STATUS.md`
and `docs/current/PUBLIC_RELEASE_READINESS.md`.

## What is NOT a setup gap (in spite of older docs saying so)

- ✓ RC3 tag creation — already done
  (`mmv_core_v0_1_rc3_release_candidate_20260430_2336` → `7f53fe1`).
- ✓ Pattern Library state — closed at Phase 4 closure.
- ✓ M-1 micro-fix — applied before RC3 was cut.
- ✓ Standard-benchmark bridge — Phase 5N–5P landed; bench clone is
  reproducible.
- ✓ Secretary addon — Stage 0-A through 0-F shipped; OpenCode
  integration optional.

If an older doc lists any of the ✓ items above as "still needed",
that older doc is stale relative to this file.
