# Public Release Readiness Checklist — MMV Core v0.1-rc1

> Historical note (2026-05-21): this checklist records rc1-era public
> release readiness. Current document authority is
> `docs/current/DOCS_AUTHORITY_MAP.md`; current L0 authority is
> `prompts/l0_integrated_v8_4.md`.

**Status of this document**: assessment, not a release action. Each item
records the current state so the user can decide whether to proceed
with publication.

**Anchors**:
- Freeze: `mmv_core_v0_1_rc1_freeze_20260428_1751` (Phase 5A).
- Release prep: `mmv_core_v0_1_rc1_release_prep_<UTC>` (this Phase 5B
  commit; updates this checklist with the Phase 5B work landed).
- Closure: `phase4_close_20260429_0056`.

**Phase 5B update (2026-04-29)**: README amended additively for
v0.1-rc1; QUICKSTART.md, THIRD_PARTY_LICENSES.md,
docs/ISM_CORPUS_DISTRIBUTION_POLICY.md, and
docs/INDEX_DISTRIBUTION_POLICY.md created. The previously-✗ items in
sections (a), (b), (c), (h), and (i) below now read ✓ or △ with an
explicit decision recorded.

Legend:
- ✓ ready — meets the bar for v0.1-rc1
- △ partial — usable for rc but flag in release notes / known limitations
- ✗ not ready — must be addressed before publishing
- N/A — not applicable to v0.1-rc1

---

## a. README readiness

| Item | State |
|---|---|
| `README.md` exists at repo root | ✓ |
| Project identity (name, license, author) | ✓ (covered by `README.md` + `LICENSE`) |
| One-paragraph "what this is" | ✓ (covered in `README.md` and `CLAUDE.md`) |
| Quickstart link or section | ✓ — Phase 5B added explicit link to [QUICKSTART.md](../QUICKSTART.md) |
| Phase 4 closure / RC1 caveats called out | ✓ — Phase 5B added "Release status — v0.1-rc1" block + "Known limitations (v0.1-rc1)" section |
| Link to release notes (`docs/MMV_CORE_V0_1_RC1_RELEASE_NOTES.md`) | ✓ — Phase 5B added |

Action before public push: re-read once for ergonomics; consider a
short top-of-file project summary refresh after public-channel
decisions land. The minimum-additive amendments required for v0.1-rc1
have been applied; further README polish is not blocking.

## b. Install / quickstart readiness

| Item | State |
|---|---|
| Python version pinned | ✓ — `pyproject.toml` `requires-python = ">=3.13"`; QUICKSTART §1 confirms |
| `requirements.txt` / `pyproject.toml` exists and installable | ✓ — both present; QUICKSTART documents `pip install -e .` and the optional `[ui]` / `[dev]` extras |
| First-run command documented | ✓ — [QUICKSTART.md](../QUICKSTART.md) §4 (headless smoke + Gradio UI) |
| ME5 / FAISS index distribution policy | ✓ — [docs/INDEX_DISTRIBUTION_POLICY.md](INDEX_DISTRIBUTION_POLICY.md) (rebuild-on-install for Pattern Library; fetch-on-demand for Wikipedia; ISM/QK rebuilt from corpus *if available*) |
| Ollama / qwen3.5:9b dependency documented | ✓ (`CLAUDE.md` + QUICKSTART §1, §4) |
| GPU / CPU expectations documented | ✓ (`CLAUDE.md` + QUICKSTART §6 + index policy doc §4) |

Phase 5B closed all of (b). Sanity-check command set in QUICKSTART §7
verifies that installer state matches the v0.1-rc1 baseline (139 / 26
patterns, 505 / 200 golden entries).

## c. License files readiness

| Item | State |
|---|---|
| `LICENSE` present at repo root | ✓ AGPL-style (header `MOBIUS LLC`, author `Taiko Toeda`) |
| License headers in source files | △ — partial; not all files carry headers (Phase 5B did not amend headers; not blocking for v0.1-rc1) |
| Third-party licenses inventoried | ✓ — Phase 5B created [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md) covering Python deps, models (ME5, qwen3.5), external APIs (Brave/Groq/Ollama/HF), and third-party data artifacts |
| Author attribution policy | ✓ (LICENSE) |
| Commercial-license terms clarified | ✓ — Phase 5B added "Commercial / non-AGPL licensing" section to README pointing inquiries to **info@mobius.style** with the reasoning (AGPL copyleft trade-off) called out |

A future polish pass could add per-file SPDX headers
(`SPDX-License-Identifier: AGPL-3.0-or-later`); not blocking v0.1-rc1.

## d. .env.example readiness

| Item | State |
|---|---|
| `.env.example` is tracked | ✓ |
| `.env` is gitignored | ✓ (verified `.gitignore`) |
| All required keys documented in `.env.example` | ✓ — `BRAVE_API_KEY`, `GROQ_API_KEY`, Ollama endpoints, etc. |
| No real values committed in `.env.example` | ✓ — values are blank placeholders |
| `.env` permission `0600` on dev box | ✓ (`-rw-------`) |

## e. Secret scan readiness

See [PHASE_5A_CORE_FREEZE_REPORT.md](PHASE_5A_CORE_FREEZE_REPORT.md)
"Release hygiene scan" section for the actual scan output performed at
the freeze line. The bar for v0.1-rc1 is:

- No live API keys, OAuth tokens, or private keys reachable from a
  public clone path.
- `.env`, `.credentials.json`, and other secret-bearing files are
  gitignored at this freeze.

State: see scan results in the freeze report.

## f. Test pass readiness

| Item | State |
|---|---|
| pytest pass rate | see Phase 5A freeze report (lightweight pytest run recorded there) |
| Constitutional Invariants | ALL PASS expected (Phase 4 closure baseline) |
| Existing-fixes (7/7 + engine + C-2 + ME5 + Phase 3 stab C44) | INTACT (Phase 4 baseline) |
| Golden 200 (pattern_library_golden_set_v1) | 88.5% (177/200), all 6 topics ≥ 85% (Phase 4 closure record) |
| Golden 505 (long_tail_v1) | Cat A 0/505 at thresholds 0.50–0.85 (Phase 4 closure record) |
| 33-scen N=5 baseline | not re-measured at freeze (Phase 3 stab N=5 mean 30.40 inherited) |
| 33-scen N=1 smoke | optional at freeze; recorded in report if run |

The Phase 4 closure result is the canonical baseline. Phase 5A does not
re-run heavy validation; only lightweight checks confirm nothing
regressed since closure.

## g. Known limitations

To list verbatim in the release notes:

1. Single long-tail-Cat-A milestone (505 entries, 0% Cat A). Phase 4
   closure criterion (b) requires 2 milestones for *strict* stability;
   this rc1 ships with informational-pass via criterion (a).
2. Long-tail Japanese coverage at **22.4%**, target was 33.3%. Carried
   forward as a Phase 5 candidate; does not block rc1.
3. 33-scenario harness baseline is **N=5 mean 30.40** inherited from
   Phase 3 stab; **not re-measured** at Phase 4 close. Cheap N=1 smoke
   in Phase 5A only confirms order-of-magnitude continuity.
4. Pattern Library saturated around 4-of-5 sub-topics at threshold 0.92
   (Phase 4 b14 evidence). Further growth requires sub-topic taxonomy
   refinement — Phase 5 work, not rc1 work.
5. ME5 / FAISS indices are large and gitignored. Distribution model
   (rebuild-on-install vs. fetch-on-demand) is not yet decided.
6. **0/505 Cat A is *not* deployment-wide validation.** It is a single
   informational milestone on a researcher-curated long-tail surface.
   Generality across other domains is unmeasured.
7. Patent attorney review remains DEFERRED (Path C). Public release on
   AGPL is gated on user clearing this with their attorney.

## h. Artifact inclusion / exclusion policy

| Artifact | Public package |
|---|---|
| `src/`, `prompts/`, `config/pattern_library/*.jsonl`, `tests/` | INCLUDE |
| `LICENSE`, `README.md`, `CLAUDE.md`, `QUICKSTART.md`, `THIRD_PARTY_LICENSES.md`, `docs/MMV_CORE_*`, `docs/PUBLIC_RELEASE_*`, `docs/SECRETARY_*`, `docs/INDEX_DISTRIBUTION_*`, `docs/ISM_CORPUS_DISTRIBUTION_*` | INCLUDE |
| `docs/PHASE_4_*`, `docs/PATTERN_LIBRARY_PHASE4_*`, `docs/PHASE_5A_*`, `docs/PHASE_5B_*` | INCLUDE (closure + freeze + release-prep record) |
| `data/pattern_library/index.faiss` (1,252 vectors) | EXCLUDE — rebuild on install per [INDEX_DISTRIBUTION_POLICY.md](INDEX_DISTRIBUTION_POLICY.md) |
| `data/raf/teacher_data_raw.jsonl` (36,282) | EXCLUDE per [ISM_CORPUS_DISTRIBUTION_POLICY.md](ISM_CORPUS_DISTRIBUTION_POLICY.md) decision (provenance audit + redaction not done; defer to v0.2) |
| `data/raf/ism_index.faiss`, `data/raf/qk_index.faiss` (~150 MB each) | EXCLUDE — derived from corpus; rebuild path documented |
| `Wiki/wiki_index_*` (Box W) | EXCLUDE — fetch-on-demand from project HF mirror per [INDEX_DISTRIBUTION_POLICY.md](INDEX_DISTRIBUTION_POLICY.md) §3 |
| `kiwix/*.zim` | EXCLUDE — third-party ZIM (obtain from kiwix.org) |
| `.env`, `.credentials.json`, `~/.claude/` | EXCLUDE (already gitignored) |
| `.phase4_autodriver_*`, `.cron_backups/` | EXCLUDE (already gitignored) |
| `addon/secretary/` (when it lands) | EXCLUDE from rc1 — separate addon package |

Phase 5B closed all the DECISION REQUIRED items in (h). The corpus is
deferred to v0.2; all derived artifacts have rebuild paths.

## i. Attorney review / commercial-license note

| Item | State |
|---|---|
| Patent attorney review (Path C) | DEFERRED — flagged in Phase 4 prompt and rc1 known limitations; **T-gated, not Claude work** |
| AGPL contagion notice in README | ✓ — Phase 5B added; explains AGPL copyleft trade-off and points commercial inquiries to **info@mobius.style** |
| Commercial dual-licensing channel | ✓ — Phase 5B established `info@mobius.style` as the inquiry path; pricing / terms remain a T decision |
| Trademark / brand-name policy ("MOBIUS") | △ — not yet a separate doc; the LICENSE + README's "MOBIUS LLC" attribution is the current de-facto policy. Trademark registration is out of scope for v0.1-rc1 |

Action remaining: T resolves patent attorney review externally before
public AGPL push. The runtime / packaging surface is otherwise ready.

---

## Summary by readiness class

State after Phase 5B (release-prep) work landed:

| Class | Items |
|---|---|
| ✓ Ready | LICENSE present; .env.example complete; .env gitignored; pattern library + golden sets at closure baselines; README v0.1-rc1 amendments applied; QUICKSTART.md present; THIRD_PARTY_LICENSES.md present; ISM-corpus distribution policy decided (defer to v0.2); FAISS/ME5 index distribution policy decided (rebuild-on-install + fetch-on-demand for Wikipedia); commercial-license channel articulated (info@mobius.style) |
| △ Partial | per-file SPDX license headers (cosmetic; not blocking); trademark policy doc (current README attribution suffices for rc1) |
| ✗ Pending before public push | **Patent attorney review** — externally gated by T (Path C deferred from Phase 2; not Claude work) |
| N/A | feature-additive items deferred to v0.2 (ISM corpus inclusion, taxonomy refinement, Japanese-ratio correction, etc.) |

**Bottom line after Phase 5B**: the runtime side AND the packaging /
external-facing surface are at v0.1-rc1 quality. The only remaining ✗
item before public AGPL push is the **patent attorney review** — a
T-gated external action, not a Claude task. Once that clears, the
release can proceed using the artifact inclusion/exclusion policy in
§h above.
