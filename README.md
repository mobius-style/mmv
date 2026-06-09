# MOBIUS MMV — Answer Entitlement Runtime

MOBIUS MMV is a local-first AI runtime that determines whether answering
is justified before generating a response.

Author: Taiko Toeda / MOBIUS LLC

## Try it now (no install)

Want to feel the governance behavior before installing anything? Paste the
single self-contained prompt in **[TRY_MOBIUS.md](TRY_MOBIUS.md)** into a fresh
ChatGPT / Claude / Gemini chat — **one paste, no setup.** It's a prompt-level
demo of the L0 v8.4 governance layer (answer / verify / ask / abstain), not the
full retrieval + evidence-adjudication runtime — that's the install below.

**Grab the prompt in one click:** open the
**[copy page](https://mobius-style.github.io/mmv/)** and hit *Copy prompt* — or open
[TRY_MOBIUS.md](TRY_MOBIUS.md) and use GitHub's **Copy raw file** button (or the
[raw text](https://raw.githubusercontent.com/mobius-style/mmv/main/TRY_MOBIUS.md), clean UTF-8).

## Release status — L0 v8.4 (v8.4.1 abstain revision) / MMV RC3.3 current workspace

This workspace now reads **L0 v8.4** as the current protocol authority.
Current behavior is the **v8.4.1** reason-aware abstain point-revision
(2026-06-05) layered on v8.4: it changes abstain behavior only and
deliberately retains the v8.4 file names (see
[docs/L0_v8_4_1_ABSTAIN_VALIDATION.md](docs/L0_v8_4_1_ABSTAIN_VALIDATION.md)).
v8.4 is an RC3.3 empirical-sync overlay: it inherits the v8.2
constitutional substrate, retires the Cline-derived v8.3 prototype as
historical, and folds in the MMV-L-RC3.3 / MMV-M-RC3.3 / MMV-S-RC3.3
release line (OPERATE-FR Smoke-100 evidence for L/S, Core-500 candidate
stress evidence for M).

Read these before drawing conclusions:

- [docs/current/DOCS_AUTHORITY_MAP.md](docs/current/DOCS_AUTHORITY_MAP.md) — current vs historical document authority
- [prompts/l0_integrated_v8_4.md](prompts/l0_integrated_v8_4.md) — current L0 v8.4 overlay
- [docs/L0_V8_4_RC3_3_SYNC_NOTE.md](docs/L0_V8_4_RC3_3_SYNC_NOTE.md) — why v8.4 supersedes v8.2/v8.3 as current authority
- [docs/L0_V8_3_SUPERSEDED_NOTE.md](docs/L0_V8_3_SUPERSEDED_NOTE.md) — Cline-specific v8.3 path retired
- [operate-fr-bench/README.md](operate-fr-bench/README.md) — OPERATE-FR Smoke-100 artifact and RC3.3 report links

The older rc1 release notes and readiness checklist remain historical
evidence, not the current reading when they conflict with the files above.

## Quick Start (Small line — local `qwen3.5:9b`)

The Gradio app (`src/ui/app.py`) runs the **Small line** (`qwen3.5:9b`
via Ollama) and reads `.env` for its endpoint and optional keys. Follow
the steps **in order** — skipping the `.env` or Ollama steps is the
usual reason a first run fails:

```bash
# 1. install
git clone https://github.com/mobius-style/mmv.git
cd mmv
python3.13 install.py

# 2. configure — copy the template, then fill the keys you have
cp .env.example .env && chmod 600 .env
#    BRAVE_API_KEY → optional, Box S freshness / web-search queries
#    GROQ_API_KEY  → optional, in-UI Self-Governance supervisor

# 3. pull the Box W ME5 index from HuggingFace (~1.74 GB; see "Heavy data")
python scripts/fetch_wiki_index.py

# 4. start the local backend (in a separate terminal) — a single 8 GB GPU is enough
ollama serve
ollama pull qwen3.5:9b

# 5. run
python src/ui/app.py
# Open http://localhost:7860
```

> ⚠️ Blank answers from `qwen3.5:9b` mean Ollama thinking mode is on —
> see [QUICKSTART.md](QUICKSTART.md) §4/§8.

**Running Medium or Large instead.** These are harness / secretary
lines, selected via the release pointer (see the table below), **not**
by `app.py`:

- **Medium** (`gemma4:12b`, local) — `ollama pull gemma4:12b`; dense
  11.9B model (prior binding `gemma4:26b`), above the 8 GB Small target —
  see the [Medium freeze note](operate-fr-bench/docs/MMV_Medium_RC3_3_FREEZE_NOTE.md)
  for the measured hardware profile.
- **Large** (`gpt-oss-120b`, cloud) — set `GROQ_API_KEY` in `.env` (get a
  key at <https://console.groq.com/>); no local model pull, but the line
  needs network access.

Full walk-through (env setup, first run, test command, index handling,
and troubleshooting): **[QUICKSTART.md](QUICKSTART.md)**.

## Release lines — Large / Medium / Small

The runtime shares one codebase; the three release lines differ only in
which model profile drives generation. Each line has its own release
pointer under `operate-fr-bench/releases/`.

| Line | Release tag | Provider / model | Pointer | Use when |
|---|---|---|---|---|
| **Large** | `MMV-L-RC3.3` | Groq `openai/gpt-oss-120b` (OpenAI-compatible) | [`operate-fr-bench/releases/large/current.yaml`](operate-fr-bench/releases/large/current.yaml) | Highest-quality cloud path; OPERATE-FR Smoke-100 validated. |
| **Medium** | `MMV-M-RC3.3` | Local Ollama `gemma4:12b` | [`operate-fr-bench/releases/medium/current.yaml`](operate-fr-bench/releases/medium/current.yaml) | Local dense-12B sibling under the Large stack (prior binding `gemma4:26b`; same RC3.3 governance, model binding only); above the 8 GB Small target — see [Medium freeze note](operate-fr-bench/docs/MMV_Medium_RC3_3_FREEZE_NOTE.md) for hardware. **Bootstrap evidence floor** (N=100 Smoke-100 + N=500 Core-500 candidate, 12b-vs-26b head-to-head). |
| **Small** | `MMV-S-RC3.3` | Local Ollama `qwen3.5:9b` | [`operate-fr-bench/releases/small/current.yaml`](operate-fr-bench/releases/small/current.yaml) | Single-GPU local path (RTX 3070-class, 8 GB VRAM); OPERATE-FR Smoke-100 validated. |

Large is the secretary default. Medium and Small are invoked explicitly:

```bash
# Inspect the active release binding
python -m addons.secretary version

# Switch to Medium for a run
python -m addons.secretary version \
  --release_pointer_path operate-fr-bench/releases/medium/current.yaml

# Switch to Small for a run
python -m addons.secretary version \
  --release_pointer_path operate-fr-bench/releases/small/current.yaml
```

The harness consumes the same pointer file via `--release_pointer_path`.
See `operate-fr-bench/README.md` for full benchmark invocation.

## Heavy data — fetched from HuggingFace

Two artifact classes are too large for git and are pulled separately:

1. **Wikipedia / Box W ME5 index** (~1.74 GB across 4 files):
   `Wiki/wiki_index_ivfpq_me5.faiss`, `Wiki/wiki_chunks_clean.jsonl.gz`,
   `Wiki/line_offsets.npy`, `Wiki/line_offsets.gzidx`.
   - **Fetch**: `python scripts/fetch_wiki_index.py`
   - **Source**: configurable in [`config/wiki_index_source.yaml`](config/wiki_index_source.yaml);
     default `huggingface.co/datasets/moebiusT7/mmv-wiki-index`.
   - **License**: CC BY-SA 4.0 (Wikipedia-derived).
2. **Models** (Ollama side): pulled with `ollama pull qwen3.5:9b`
   (Small) and `ollama pull gemma4:12b` (Medium). The Large path uses a
   cloud endpoint — no local model pull required.

Pattern Library / ISM / QK indices are rebuilt from corpus on install
(seconds for Pattern Library, optional for ISM/QK). See
[docs/INDEX_DISTRIBUTION_POLICY.md](docs/INDEX_DISTRIBUTION_POLICY.md).

## What It Does

- **Answer Entitlement**: Routes queries through appraisal → route decision →
  evidence retrieval → EAL adjudication → bounded synthesis
- **6 Routes**: answer, verify, ask, date_bound_answer, re_anchor, abstain
- **Evidence Adjudication Layer (EAL)**: Validates evidence before committing to a response
- **Question Kernels (QK)**: 42 governance prompts with ISM-adaptive injection
- **Audit Trail**: Every response includes route, TVS, MKR, sources, and trace

## Requirements

- Python 3.13+
- Ollama + qwen3.5:9b (or other supported models)
- FAISS index (Wikipedia vectors, available on HuggingFace)
- Optional: Kiwix (local Wikipedia), Brave Search API

## Architecture

```
User → Appraisal → Route Decision → Evidence Retrieval → EAL → Synthesis → Response
                                     ↑                    ↑
                                   Box W (FAISS)      Adjudication
                                   Kiwix (local)      Admissibility
                                   Brave (web)        Boundedness
```

## Models

| Model | Size | Role |
|-------|------|------|
| qwen3.5:9b | 9B | MMV-S-RC3.3 (Small line, local Ollama) |
| gemma4:12b | 12B | MMV-M-RC3.3 (Medium line, local Ollama; prior binding gemma4:26b) |
| openai/gpt-oss-120b | 120B | MMV-L-RC3.3 (Large line, Groq cloud) |
| phi4-mini | 3.8B | Paper reference baseline |

## Test Suite

```bash
pytest tests/ -q
# RC3.3 workspace baseline (2026-05-31):
# 1092 passed, 36 skipped, 3 xfailed, 0 failed
```

## Known limitations

A condensed list — see current L0 / RC3.3 notes for the full set:

1. **0/505 long-tail Cat A is a single informational milestone**, not
   deployment-wide validation. Generality across other domains is
   unmeasured.
2. **Long-tail Japanese coverage is 22.4%** (target was 33.3%). Carried
   forward as a Phase 5+ candidate.
3. **33-scenario harness baseline is N=5 mean 30.40 inherited from
   Phase 3 stab** — not re-measured at Phase 4 close.
4. **Pattern Library saturated** around 4-of-5 sub-topics at threshold
   0.92 during Phase 4 b14. Library growth past this point requires
   sub-topic taxonomy refinement (Phase 5+).
5. **ME5 / FAISS indices and the ISM corpus are large generated
   artifacts** that are not committed. The Wikipedia / Box W ME5 index
   ships on HuggingFace and is pulled by
   [`scripts/fetch_wiki_index.py`](scripts/fetch_wiki_index.py); ISM /
   QK indices rebuild from corpus if present. Distribution policy is
   documented in [docs/INDEX_DISTRIBUTION_POLICY.md](docs/INDEX_DISTRIBUTION_POLICY.md)
   and [docs/ISM_CORPUS_DISTRIBUTION_POLICY.md](docs/ISM_CORPUS_DISTRIBUTION_POLICY.md).
6. **RC3.3 is Smoke-100 evidence, not Core-500 validation.** Core-500
   remains pending for wider claims.
7. **L0 v8.3 is superseded.** Its Cline-specific path was abandoned; only
   client-agnostic boundary ideas survive in v8.4.

## Publications

- Mobius Reflective Framework: [doi.org/10.5281/zenodo.14538829](https://doi.org/10.5281/zenodo.14538829)
- P-7: Question Kernels as Outer Conscience (forthcoming)
- MOBIUS Codex (forthcoming)

## Pattern Library

The Pattern Library subsystem (`src/retrieval/pattern_*`,
`src/ui/library_inspector/`, `scripts/pattern_autogen/`,
`config/pattern_library/`) was completed in Phase 2 across 14
commits and ships with the runtime.

When operating the Pattern Library Inspector, keep it on the
local-only default (`127.0.0.1:5000`). Treat `--public` mode as a
deliberate exposure decision: the inspector surfaces governance
internals and is not hardened for untrusted networks.

## Licensing

Unless otherwise stated, this repository follows a dual-layer licensing
structure administered by MOBIUS LLC.

Software, source code, JSON configurations, schemas, protocol files, runtime
components, scripts, and reference implementations are licensed under
**AGPL-3.0-or-later**.

Documentation, essays, diagrams, theoretical descriptions, explanatory
materials, manuals, reports, and other non-executable written materials are
licensed under **CC BY-NC-SA 4.0**.

Unofficial non-commercial translations and adaptations may be shared under
CC BY-NC-SA 4.0, provided that they are clearly marked as unofficial and do not
imply sponsorship, endorsement, approval, authorization, or official status by
MOBIUS LLC.

Official translations, authorized editions, branded editions, commercial
publications, proprietary integrations, commercial exceptions, official support,
certification, and any use that avoids or replaces AGPL obligations require
prior written permission or a separate written agreement with MOBIUS LLC.

Author of record and concept originator: **Taiko Toeda**.  
Rights holder and licensing authority: **MOBIUS LLC**.

Wikipedia-derived data remains subject to CC BY-SA 4.0. Third-party
dependencies and data sources are inventoried in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

See [LICENSE_NOTICE.md](LICENSE_NOTICE.md) for details.

### Commercial / non-AGPL licensing

MMV Core is AGPL-3.0-or-later. The AGPL is a strong copyleft license
and triggers source-availability obligations for network-deployed
modifications. If you need a license without the AGPL's copyleft
requirements (for proprietary integration, embedded distribution, or
SaaS without source-availability), contact:

- **info@mobius.style** — please include intended deployment context.

Bug reports, ergonomic feedback, and questions about the current RC3.3 /
L0 v8.4 workspace are welcome through the project's issue channel
(channel TBD before public push).
