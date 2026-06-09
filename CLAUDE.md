# MOBIUS MMV — Claude Code Operating Manual

**Version: v2.1.0 (frozen 2026-04-19)**

## Project Identity

MOBIUS MMV is a local-first conversational AI runtime implementing **Answer Entitlement Architecture**.
The central governing principle: determine whether answering is justified before generating a response.

Author: Taiko Toeda / MOBIUS LLC
Work directory: `$HOME/デスクトップ/mobius_ai/MOBIUS_MMV`
Runtime: Python venv313 (activated via `mobius` alias)
Primary model: qwen3.5:9b Q4_K_M via Ollama (`think:False` required — see below)
L0 Protocol: v8.4 (`prompts/l0_integrated_v8_4.md`)

---

## Non-Negotiable Constraints

### Never break these:
- **Green test suite** — always run full pytest after any change. The invariant is `0 failed` with `~3 xfailed`; the pass count is in the 1500+ range and grows as the system evolves. Use `pytest -q tests/` for the current exact numbers — do not hardcode them here.
- **Local-First** — no mandatory cloud dependency
- **source_type="local_rag"** — Frozen v1.0. Never change this value
- **S-1 CSV** (`eval_results_20260322_073658.csv`) — permanent immutable archive. Never modify
- **Phase separation** — audit (accountability) and memory (continuity) are distinct systems. Never merge
- **Chrome Remote Desktop (CRD)** — never `pkill chrome` on the reference workstation

### Model policy:
- `phi4-mini` = paper/reference baseline (Phase A–H)
- `qwen3.5:9b` = practical verified recommendation (v2)
- Do not silently promote candidate models (ministral-3:8b, gpt-oss:20b) to reference status

### qwen3.5:9b critical note:
- Ollama versions after March 2026 enable thinking mode by default
- `api/generate` endpoint requires `"think": False` in payload
- Without this, `response` field is empty and `reasoning` field contains chain-of-thought
- OllamaAdapter uses `api/generate` + `think: False` (already implemented)

### Governance layering policy:
- **Do not combine L0 Essentials prompt injection with v2.1 structural governance.**
  - Condition I evaluation (2026-04-19, 500 queries, qwen3.5:9b) showed that injecting
    `data/evaluation/L0_Essentials_v1_2_core.json` into the Ollama system field on top
    of the full RoutingEngine stack **degrades restraint on ambiguous queries**
    (Δ = −3.44/20, Wilcoxon p = 3.72e-07) with **no lift in any of the other 8
    categories**.
  - Mechanism: 17/50 ambiguous queries flip `ask → answer`; the `MISSING_CONSTRAINTS`
    reason_code disappears and `SUFFICIENTLY_SPECIFIED` fires instead.
  - Evidence: `data/evaluation/eval_v8_essentials_v1_2_500q_cond_I_summary.md`,
    `..._cond_I_analysis.json`, and `..._with_cond_I_summary.md` (9-condition ranking).
  - Structural governance saturates the effect; execution-layer injection is redundant
    at best and harmful to restraint at worst when both layers are active.
  - Current compact artifact is `data/evaluation/L0_Essentials_v1_3_core.json`
    (L0 v8.4 / RC3.3 aligned), but the layering warning still applies until a
    new v1.3-specific stacking evaluation says otherwise.
  - Applies to Forge Gateway design: protect `adapter._system_prompt` from user-side
    prompt injection that looks Essentials-like (Answer Entitlement / TVS / MKR / KVS /
    route_taxonomy / μQK terminology), or the same restraint-collapse can be triggered
    by an end user.

---

## Architecture: Two Retrieval Pipelines

**These two pipelines are independent. Do not merge them.**

### Pipeline 1 — Adapters layer (EAL path)
File: `src/adapters/retrieval_selector.py`
Flow: Box M → Box A → Box W (Wikipedia) → Stage 2b (Kiwix complement) → Box S (Brave)

> Naming: the Wikipedia box is **Box W** in the current routing namespace
> (`box_0`...`box_7`, `box_w`; see `RouteConfig.primary_box`). Legacy adapter
> internals may still expose `box_b`, `MOBIUS_BOX_B`, or `box_used="B"` for
> backward compatibility; read those as legacy wire labels for **Box W**, not as
> the reserved Box B document slot. External/web search is **Box S**, not Box C.

### Pipeline 2 — Kernel production (verify route)
File: `src/kernel/routing_engine.py`
Flow: Stage 1 (Local RAG) → Stage 1b (Kiwix fallback) → Stage 2 (Brave)

---

## Slot Architecture — Critical

```
web_search_adapter slot → Brave Search ONLY (freshness queries)
kiwix_adapter slot      → Kiwix ONLY (static/non-freshness queries)
```

**`make_default_adapter()` must always return BraveSearchAdapter.**
Kiwix is never routed through `make_default_adapter()`.

---

## Routing Engine — Rule Priority

```
Rule 0:   safety_relevant → abstain
Rule 0.5: self_referential → answer (suppressed when context_dependent + unresolved)
Rule 1:   under_specified OR context_dependent_unresolved → ask
Rule 2:   stable_fact + KVS pass → answer (LOW_STAKES_STABLE)
Rule 2b:  stable_fact + KVS fail → verify
Rule 3:   freshness_sensitive OR high uncertainty → verify
Rule 4:   default → answer
```

### v2.1 additions:
- **Box M Hybrid Context Resolution**: 3-layer (L0/L1/L2) pattern match + ME5 context search
  - `config/referential_patterns.json`: 8-language deictic + context-dependent patterns
  - `src/memory/context_processor.py`: Background ME5 daemon (shares Box W model)
  - Bare verb commands (やって/直して) and continuation references (もっと/続き) → ask when no context
- **Reasoning Guard**: If-then/hypothetical patterns exempt from under_specified
- **Confirmatory Guard**: Evaluative statements (This is great/それで合っています) exempt from under_specified
- **Financial Realtime Patterns**: BTC/NASDAQ/為替 etc. → TVS HIGH + REFERENT_ANCHORS
- **Creative Presentation Mode (QK_42)**: Creative intent → no citation markers in response

---

## Box W (Wikipedia) — ME5 Cross-Lingual

- Index: `Wiki/wiki_index_ivfpq_me5.faiss` (IndexIVFPQ, nlist=4096, m=64, nbits=8, INNER_PRODUCT; 5,458,524 vectors, 392MB)
- Chunks: `Wiki/wiki_chunks_clean.jsonl.gz` (1.3GB)
- Embedding: `intfloat/multilingual-e5-large` (1024-dim, CPU, "query: " prefix)
- No translation step needed — Japanese queries match English articles directly (scores 0.77–0.78)
- nprobe: 32, metric: INNER_PRODUCT
- Distribution: pulled from `huggingface.co/datasets/moebiusT7/mmv-wiki-index` via `scripts/fetch_wiki_index.py` (config `config/wiki_index_source.yaml`)
- Historical label: "Box B"; current canonical name: Box W

---

## Hardware & Environment

- Machine: the reference workstation, Ubuntu 24.04
- GPU spec target (9B runtime): single RTX 3070 (PCIe 4.0), 8 GB VRAM
- PSU: 750W Gold
- Kiwix ZIM: `~/デスクトップ/mobius_ai/kiwix/wikipedia_en_all_mini_2026-03.zim` (12.4GB)

---

## Key Files (v2.1)

| File | Purpose |
|---|---|
| `prompts/l0_integrated_v8_4.md` | L0 Protocol v8.4 (current authority) |
| `prompts/00_SINGLE_PASTE__FULL_STACK__v8_0.txt` | L0 v8.0 (historical) |
| `src/kernel/routing_engine.py` | Core routing + Box M integration |
| `src/kernel/appraisal.py` | Query appraisal + context-dependent detection |
| `src/kernel/kvs.py` | TVS/MKR computation + financial patterns |
| `src/memory/context_processor.py` | Box M background daemon (ME5) |
| `src/memory/memory_indexer.py` | Box M 3-layer SQLite + FAISS |
| `src/adapters/wiki_adapter.py` | Box W ME5 cross-lingual search |
| `src/adapters/question_kernel.py` | QK 42-kernel catalogue + fire policy |
| `config/referential_patterns.json` | 8-language deictic/context patterns |
| `data/evaluation/L0_Essentials_v1_3_core.json` | Current Essentials JSON; do not stack on structural governance without new evaluation |

---

## Scope Discipline

Before implementing anything, state:
1. The task you believe you are executing
2. Which files you will touch
3. Which files you will NOT touch
4. Completion condition (pytest result)

**When in doubt, do less. Report and ask.**

---

## Secretary addon — token offload for read-heavy surveys

`addons/secretary/` (post-Core addon; see `docs/SECRETARY_ADDON_STRATEGY.md`
and `docs/MMV_CORE_FREEZE_POLICY.md`) is Claude's MMV-Large delegate
for token-heavy *read* work. Default to it for exploratory surveys
before reaching for direct Read.

**Reach for the secretary when**:

- Reading >3 files in a directory to understand its shape
- Surveying recent activity / who-touched-what
- Repo-wide grep that needs structural roll-up
- Don't yet remember what verbs / capabilities exist

```
secretary list                            # what verbs exist
secretary git-history --last 80           # recent activity distribution
secretary eval-results --target <dir>     # eval/* CSVs + JSONLs
secretary pattern-library                 # config/pattern_library/
secretary docs [--recent-days N]          # docs/*.md catalog by prefix
secretary bench-summary --target <dir>    # benchmarks/reports/
secretary repo-grep --pattern X           # structured grep + roll-up
secretary review-packet --target <dir>    # human-review packet bundle
secretary explain <verb>                  # spec + recent invocations
```

(`secretary` shorthand for `python -m addons.secretary`.)

**Skip the secretary when** the task is a targeted edit, a single-line
debug, or <3 files are in scope — direct Read is faster than spawning
a subprocess.

**Supervision channels**:

- Per-invocation JSONL at `addons/secretary/state/logs/<verb>_<ts>.jsonl`
- `touch addons/secretary/state/halt` to abort a long-running verb
- `addons/secretary/permission_ladder.yaml` declares each verb's
  read / write / network surface (canary test enforces every verb
  in the CLI has a declared entry)

**`--with-synthesis`** (currently only on `review-packet`) trades
Claude tokens for Groq tokens via MMV Large. The structural digest
above the synthesis section is ground truth; the synthesis is
LLM-derived and may hallucinate. The live `--with-synthesis` API
path verifies on first real use — surface failures honestly, don't
paper over them.

**Active release auto-sync**: every secretary invocation reads
`operate-fr-bench/releases/large/current.yaml`. On a freeze bump,
`secretary bump --to MMV-L-RC3.X --profile <name> --freeze-note <path>`
updates the pointer; subsequent invocations use the new release with
no other code changes.
