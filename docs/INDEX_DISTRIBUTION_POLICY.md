# FAISS / ME5 Index — Distribution Policy (v0.1-rc1)

**Decision (default for v0.1-rc1)**: **Do not bundle pre-built FAISS
indices in the public package.** Use **rebuild-on-install** as the
primary path; document a **fetch-on-demand** option for the largest
artifact (the Wikipedia index) where the project has an existing HF
mirror.

This document records the reasoning. It complements
[docs/ISM_CORPUS_DISTRIBUTION_POLICY.md](ISM_CORPUS_DISTRIBUTION_POLICY.md) (which decides the
upstream corpus question for ISM/QK indices specifically).

## 1. Inventory

| Index | File(s) | Approx size | Source | Vector count | Used by |
|---|---|---|---|---|---|
| Pattern Library | `data/pattern_library/index.faiss` + `data/pattern_library/index_metadata.jsonl` | ~5 MB | rebuilt from `config/pattern_library/*.jsonl` (139 active patterns × ~7 examples) | 1,252 | `src/retrieval/pattern_lookup.py` |
| Wikipedia (Box W) | `Wiki/wiki_index_ivfpq_me5.faiss` + `Wiki/wiki_chunks_clean.jsonl.gz` | ~400 MB index + ~1.3 GB chunks | rebuilt from a Wikipedia dump → ME5 embeddings | 5,458,524 | `src/adapters/wiki_adapter.py` (cross-lingual) |
| ISM | `data/raf/ism_index.faiss` (+ `ism_chunks.jsonl`) | ~150 MB | rebuilt from `data/raf/teacher_data_raw.jsonl` ME5 embeddings | matches corpus chunk count (36,282 in v0.1-rc1) | ISM clustering paths |
| QK | `data/raf/qk_index.faiss` (+ `qk_chunks.jsonl`) | ~150 MB | rebuilt from QK chunks ME5 embeddings | matches QK chunk count (36,282 in v0.1-rc1) | QK firing-policy lookup |

All four are deterministically rebuildable from the input corpora and
the ME5 model — they are **derived data**, not original.

## 2. Why not bundle

1. **Size.** The four indices together exceed 1 GB. Adding them to the
   git tree would balloon clone times and force every contributor to
   fetch large binary blobs. They are already gitignored
   (`*.faiss`, `*.jsonl.gz`, `data/`).
2. **Mutability.** Index contents change every time the source corpus
   or the ME5 model version changes. A bundled index would go stale.
3. **License separation.** The Wikipedia index incorporates Wikipedia
   content (CC BY-SA 4.0). Other artifacts have different upstream
   licenses. Distributing them inside an AGPL-licensed repo would
   create an attribution-tracking problem for downstream packagers.
4. **Reproducibility.** Shipping the rebuild script forces the install
   path to exercise the same code that any user-modified deployment
   would use.

## 3. Distribution flow per index

### Pattern Library FAISS (~5 MB; rebuild always)

Rebuild is fast (seconds on CPU for the v0.1-rc1 1,252-vector library):

```bash
python -m scripts.build_pattern_index
# Writes:
#   data/pattern_library/index.faiss
#   data/pattern_library/index_metadata.jsonl
```

This is the only index the v0.1-rc1 quickstart instructs every
installer to run.

### Wikipedia FAISS (~400 MB; fetch-on-demand)

The project author maintains a Wikipedia index on Hugging Face that
matches a known Wikipedia snapshot date. v0.1-rc1's recommended path
is:

1. **Fetch the prebuilt index** from the project's HF repository.
2. Place at `Wiki/wiki_index_ivfpq_me5.faiss` and
   `Wiki/wiki_chunks_clean.jsonl.gz`.
3. (Alternative) Rebuild from a Wikipedia dump using the project's
   embedding script — significantly slower (multi-hour on CPU).

The HF URL and exact snapshot date are confirmed in the v0.1-rc1
release notes / installer. The fetch step is **optional**: the runtime
starts without the Wikipedia path enabled.

### ISM and QK indices (~150 MB each; rebuild from corpus)

Rebuild requires the ISM corpus (`data/raf/teacher_data_raw.jsonl`).
Per [docs/ISM_CORPUS_DISTRIBUTION_POLICY.md](ISM_CORPUS_DISTRIBUTION_POLICY.md), the corpus itself is
**not bundled in v0.1-rc1**. So:

- Installers who do not have the corpus → ISM/QK paths return empty /
  pass-through (the runtime tolerates this).
- Installers with their own ISM corpus → use the project's rebuild
  script (`scripts/ism_corpus/*.py`).
- Project author → has a private corpus snapshot for reproducibility.

This is the ISM corpus question, not an index-policy question; the
indices follow whatever the corpus does.

## 4. GPU policy at rebuild

Per `docs/CLAUDE_CODE_PHASE_4_AUTONOMOUS_PROMPT_v2_1.md` HARD
CONSTRAINT 5 (preserved as Phase 4 closure operational guidance for
this hardware), embedding work uses **GPU slot 1 only**:

```bash
CUDA_VISIBLE_DEVICES=0 python -m scripts.build_pattern_index
```

CPU rebuild also works and is the recommended path for the Pattern
Library (small; CPU is fast enough). The Wikipedia and ISM/QK rebuilds
benefit substantially from GPU slot 1.

The dual-GPU electrical-saturation prevention rule is a property of
the project author's specific hardware (dual RTX 3070 + 750W PSU) and
is documented mainly so other operators do not assume "more GPUs =
faster" without verifying their power envelope. Single-GPU and CPU
operators are unaffected.

## 5. Decision summary

| Index | Bundled? | Primary install path | Optional path |
|---|---|---|---|
| Pattern Library | no | rebuild on install (quick) | — |
| Wikipedia (Box W) | no | fetch from HF | rebuild from dump (slow) |
| ISM | no | rebuild from corpus *if installer has one* | runtime tolerates absence |
| QK | no | rebuild from corpus *if installer has one* | runtime tolerates absence |

This is the v0.1-rc1 default. Future releases (v0.2+) may revisit if
operational data justifies a different trade-off (e.g., a slim
"researcher-quickstart" tarball with a 200-chunk seed corpus + small
indices).

## 6. T decisions to confirm

If the user disagrees with the default:

1. **Ship a tarball with the Wikipedia index inline** — would require
   resolving the >100 MB-per-file git-LFS / release-asset story.
2. **Bundle the Pattern Library FAISS** — small enough that this is a
   defensible micro-optimization. Trade-off: index goes stale if the
   library changes; freeze policy says it won't, so this is low risk
   for v0.1-rc1.
3. **Skip Wikipedia entirely from the v0.1-rc1 surface** — ship
   only Pattern Library + ISM. Reduces installer complexity.

The current default is the most cautious. The user can override on
the path to public push.

## 7. Cross-references

- [docs/ISM_CORPUS_DISTRIBUTION_POLICY.md](ISM_CORPUS_DISTRIBUTION_POLICY.md) — corpus-level decision.
- [QUICKSTART.md](../QUICKSTART.md) §6 — installer-facing summary of this policy.
- [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md) §4 — third-party data artifact licenses.
- [docs/MMV_CORE_V0_1_RC1_RELEASE_NOTES.md](MMV_CORE_V0_1_RC1_RELEASE_NOTES.md) — known-limitation #5
  (ME5/FAISS indices distribution) refers to this policy.
