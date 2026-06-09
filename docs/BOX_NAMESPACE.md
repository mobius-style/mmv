# MOBIUS MMV — Box Namespace & Rules (single source of truth)

**Status:** current namespace authority (created 2026-05-30; normalized
2026-06-09). Purpose: eliminate box-naming misrecognition after the
renumbering. Where this doc and an older doc disagree about a box *role*,
**this doc wins**; where they disagree about runtime *behavior*, the code wins
and this doc is a bug.

Legend: ✅ confirmed in code/data · 🅴 design intent (owner-stated), partially
wired · ⬜ reserved, role TBD · 🔴 known hazard.

---

## 1. Two addressing layers (do not conflate them)

MMV currently uses **two coexisting box-addressing schemes**. This is the #1
source of confusion.

- **Route-decision namespace** — numbers + `box_w`. Used by the Pattern Library
  and routing decisions (`RouteConfig.primary_box`, `BOX_NS`):
  `box_0, box_1, box_2, box_3, box_4, box_5, box_6, box_7, box_w`.
- **Retrieval backend boxes** — letters. The actual stores/adapters with
  on-disk corpora: `Box 0, Box A, Box B, Box C, Box W, Box M, Box X, Box S,
  Box Kiwix`.

The two layers are **only partially bridged** (see §5). Treat a number and a
letter as the *same* box only where §2/§3 says so explicitly.

---

## 2. Route-decision namespace (numbers + box_w)

| Token | Role | State |
|---|---|---|
| `box_0` | System canonical / self-reference / governance concepts (MMV-internal) | ✅ used (`primary_box="box_0"` in taxonomy) |
| `box_1` `box_2` `box_3` | **User space** (renumbered from the former user-space Box A/B/C document managers) | 🅴 declared; not yet routed (`primary_box="box_1.."` unused; "Phase G.11 reserved user-space") |
| `box_4` `box_5` `box_6` `box_7` | Reserved for **future user-space expansion** (per the two-layer decision: numbers = user space) | ⬜ no role yet, no usage |
| `box_w` | Wikipedia (ME5 cross-lingual retrieval) | ✅ used |

Source of truth: `src/retrieval/pattern_schema.py` (`RouteConfig.primary_box`),
`src/ui/library_inspector/routes/author.py` (`BOX_NS`),
`docs/T_AUTHORING_GUIDE.md §3.4`.

`exclude_boxes`: boxes a query must never consult (e.g. self-ref pattern →
`exclude_boxes: ["box_w"]` to block Wikipedia ambiguity).

---

## 3. Retrieval backend boxes (letters) — roles, stores, ME5 status

| Box | Role | Store / adapter | ME5 | Number bridge |
|---|---|---|---|---|
| **Box 0** | Self-reference / system canonical | `box_0_adapter` (CustomRagAdapter), `data/box_0/` | ✅ | = `box_0` |
| **Box A** | 🅴 **Mobius-related foundational reference material** (system-side; *re-defined* from the old "user documents" role) | `BoxAManager`, `data/box_a/` (incl. `mobius_drive_library/`) | ✅ | — (no number) |
| **Box B** | 🅴 **Reserved document slot** — currently empty; future/optional governed documents. Not Wikipedia. Not web search. | `BoxBManager`, `data/box_b/documents/` (empty) | n/a until vectorized | — |
| **Box C** | 🅴 **Reserved document slot** — currently empty; future/optional governed documents. Not web search. | `BoxCManager`, `data/box_c/documents/` (empty) | n/a until vectorized | — |
| **Box W** | Wikipedia (ME5, the real retrieval body; legacy code/tests may still expose `box_b`/`box_used="B"` for this path) | `wiki_adapter`, `Wiki/wiki_index_ivfpq_me5.faiss` | ✅ | = `box_w` |
| **Box M** | Session memory + capsule memory index | `memory_indexer.py` + `memory_capsule.py` + `context_processor.py` (ME5 daemon) — all present ✅ | ✅ | — (no number) |
| **Box X** | High-trust accumulated / curated external **durable** knowledge (read-only reference layer). Receives promotions from Box S (`s_to_x_promotion.py`) | `src/memory/box_x.py` (`BoxXStore`/`BoxXEntry`) + `src/retrieval/box_x_consultation.py`; data `data/box_x/box_x.json` (91 entries) — present ✅ (Stage-9 test: 13 passed) | ✅ | — (no number) |
| **Box S** | **External / web search (Brave)** — transient search-quarantine, consulted after Wikipedia. **Current/latest name for the external-search box** (doctrine `S`; `query_reformulator` "BOX S (web search)"; results promotable to Box X via `s_to_x_promotion`). | `_BraveSearchAdapter` + `data/box_sk/` (transient holding) | n/a | — |
| **Box Kiwix** | Local Wikipedia complement to Box W (offline fallback) | `kiwix_adapter`, ZIM | n/a | — |

ME5 embedding rule (§4) is constitutional: every box that builds/consumes a
vector index uses `intfloat/multilingual-e5-large` (1024-dim).

**Empirical confirmation (store contents inspected 2026-05-30):** roles above
were verified against the *actual data*, not just docstrings —
- `data/box_0/` (371 chunks, ME5): MMV System Overview RC3.3 + L0 protocol → system authority ✅
- `data/box_a/` (10 chunks, ME5) + `mobius_drive_library/` (harvested Mobius Drive: catalog, pdf/docx/google_docs, extracted text): MMV Modeling Doctrine + Mobius corpus → **Mobius-foundational** ✅ (directly disproves the doctrine's "Box A = user documents")
- `data/box_b/`, `data/box_c/`: `documents/` empty → reserved ✅
- `data/box_m/` (`high_capacity/`, `memory.jsonl` schema `box_m_hc_distilled_v1`): distilled session memory ✅
- `data/box_x/box_x.json` (91 canonical-term entries, e.g. category-theory glossary): curated durable ✅
- `data/box_w_domain/` (category_theory / ml / physics + manifest): Box W curated domain pack
- `data/box_sk/` (`.gitkeep` only): Box S transient search-quarantine, empty by design ✅
- `data/box_0_e5`, `data/box_0_minilm_backup_20260423`: minilm→ME5 migration backups (not live boxes)

**Implementation status (2026-05-30 — stage-9 modules restored):** the 14
stage-9 modules the code imports were missing on this branch but **existed in
git** (commit `7f53fe1`, rc3 lineage); they were **restored**, not re-invented:
`src/memory/`{`box_x`, `context_processor`, `meta_recall`, `s_to_x_promotion`,
`box_p`, `user_map`, `trajectory_state`, `carryover`, `indexed_box_entry`,
`box_s_quarantine`} and `src/retrieval/`{`box_x_consultation`, `alias_resolver`,
`domain_corpus`, `domain_rerank`}. All import cleanly; the runtime is no longer
degraded. Box X Stage-9 test: 13 passed. The missing config
`config/referential_patterns.json` (8-language deictic/context-dependent
patterns) was also restored (commit `613ec99`) — it carries the ZH continuation
(`续/續...`) and bare-imperative (`^优化...那个...吧`) patterns; with it,
**`test_zh_phase3.py`: 66 passed (0 failed)** and the referential-affected test
groups regress clean (0 failed). Runtime now operates in full (non-degraded) mode.

Source of truth: this file for names/roles, `docs/EMBEDDING_RULE.md` for
embedding policy,
`src/kernel/routing_engine.py` (`__init__` wiring), `src/ui/app.py` (loaders),
`src/adapters/retrieval_selector.py` (consultation order + `box_w_label`).

### 3.2 Verify-time reference (consultation) order

Document/knowledge escalation during a verify route is:

```
Box A → Box B → Box C → Box W (Wikipedia) → Box S (external/web search)
 (docs:  Mobius   reserved  reserved)          (encyclopedic)   (live, last)
```

This ordering is *why* the document boxes are lettered A/B/C (1st/2nd/3rd
document source) and external search sits last. **Box B and Box C are currently
empty, so they are simply skipped** — the live path today is effectively
A → W → S. Box 0 (self-reference), Box M (session memory) and Box X (curated
durable) are consulted by their own triggers, not in this linear escalation.

(Legacy note: old code/comments may say "Box A → Box B → Box C" where "Box B"
meant Wikipedia and "Box C" meant Brave. Current names are Box W and Box S,
respectively; see §6.)

---

## 4. Constitutional rule — ME5 everywhere

All MMV-generated or MMV-consumed vector indexes **MUST** use
`intfloat/multilingual-e5-large` (1024-dim). Applies to Box 0, A, W, M, X, and
any future box. Device: `MMV_EMBEDDING_DEVICE` (`auto`/`cpu`/`cuda`). Tests must
assert the manifest's `model` field. Full text: `docs/EMBEDDING_RULE.md`.

The Wikipedia (Box W) index is distributed from
`huggingface.co/datasets/moebiusT7/mmv-wiki-index` via
`scripts/fetch_wiki_index.py` (config `config/wiki_index_source.yaml`, SHA256
verified). Index: IndexIVFPQ, nlist=4096, **m=64**, nbits=8, INNER_PRODUCT,
5,458,524 vectors (verified via `faiss.read_index`).

---

## 5. Env flags

| Flag | Default | Effect |
|---|---|---|
| `MOBIUS_BOX_0` | on | Box 0 (self/system canonical) |
| `MOBIUS_BOX_A` | on | Box A foundational/system reference material |
| `MOBIUS_BOX_W` | on | Box W Wikipedia retrieval (canonical flag) |
| `MOBIUS_BOX_B` | on | legacy alias for the Box W Wikipedia path in adapters; not the reserved Box B document slot |
| `MOBIUS_BOX_S` | on | Box S external/web search |
| `MOBIUS_BOX_KIWIX` | on | Kiwix complement |
| `MOBIUS_BOX_X` | on | Box X durable-knowledge consultation |

Backward-compat: the adapter path may still emit `box_used="B"` /
`"B-Kiwix"` and keep internal `box_b` variable names for the Wikipedia adapter.
Read those as **legacy wire labels for Box W**, not as the reserved Box B
document slot. New documentation and operator-facing names should say Box W.

---

## 6. Misrecognition hazards (read before touching boxes)

1. ✅ **`data/box_b` un-polluted (2026-05-30).** The legacy ML6 Wikipedia build
   (`wiki_chunks.db` ~36.7 GB + ML6 chunks/index/offsets, ~39 GB) was evicted
   from `data/box_b/` to the SG4T (SSHD / "T4") drive at
   `/media/happy/SG4T/mmv_ml6_legacy_box_b_20260530/`. `data/box_b/` now holds
   only `documents/` (the BoxBManager store). The ME5 Box W set is on HF
   (`moebiusT7/mmv-wiki-index`); the ML6 set is preserved on SG4T (and ML6
   `.jsonl.gz`/`.faiss` copies also remain in `Wiki/`).
2. ✅ **Legacy external-search name "Box C" → renamed to Box S.**
   Current adapter code uses `_box_s`, emits `box_used="S"` for external/web
   search, and reads `MOBIUS_BOX_S`. Current operator-facing documentation must
   call Brave/web search **Box S**. The Phase-G.11 **document-slot** "Box C"
   (`box_c_manager`, `data/box_c`) is intentionally kept as a reserved document
   slot. Wikipedia is the only intentionally retained legacy wire label:
   `box_used="B"` still means Box W.
3. ✅ **Box A role conflict resolved in the repository.** The current owner-ruled
   role is **Box A = Mobius-foundational material**; user/workspace documents
   live in `box_1-3` user space. Repository current surfaces have already been
   updated to this reading (`MMV_MATHEMATICAL_MODELING_DOCTRINE_RC3_3.md`,
   `MMV_FRONTIER_CHAT_TRIAL_PACK_RC3_3_L0V8_4.md`, `TRY_MOBIUS.md`, and
   `docs/EMBEDDING_RULE.md`). The only remaining publication risk is external:
   if the older wording exists in an already-frozen independent Zenodo DOI for
   the doctrine or trial pack, handle it as an erratum; if no such independent
   frozen DOI exists, no additional repository action is needed. See §7/§8.
4. 🟡 **Number↔letter bridge incomplete (by design — two layers).** `box_1-3`
   (user space) are declared but not yet wired into routing; Box M and Box X
   keep letters (no number); `box_4-7` are reserved for future user-space.

---

## 7. Decisions (owner-ruled 2026-05-30) & remaining

**Decided:**
- **Two permanent addressing layers.** Numbers = user space; letters = system
  boxes. They are *not* being merged. `box_4-7` = reserved for future
  user-space expansion. Box M / Box X keep letters (no number).
- **User space = `box_1` / `box_2` / `box_3`** (canonical).
- **Box A = Mobius-foundational material** (canonical). The published RC3.3
  doctrine's `A = user/workspace documents` (§8) is a **pre-rename snapshot
  written on old information** and is superseded by this doc.

- **Box S = external/web search** (Brave), latest name. **Box B and Box C =
  reserved document slots (future)** — search is its own box, so the letters B/C
  are free for documents.

**Repository clean-up status:**
- ✅ Code: legacy external-search "Box C" → "Box S" in `retrieval_selector.py`
  etc. (§6.2). Current code emits `box_used="S"` for external search; Wikipedia
  still emits legacy `box_used="B"` by design.
- ✅ Docs: stale `A = user/workspace documents` → Box A = Mobius-foundational
  (user docs → box_1-3) in `EMBEDDING_RULE.md`, `MMV_SYSTEM_OVERVIEW_RC3_3.md`,
  `MMV_MATHEMATICAL_MODELING_DOCTRINE_RC3_3.md`,
  `MMV_FRONTIER_CHAT_TRIAL_PACK_RC3_3_L0V8_4.md`.
- ✅ Formal-model decision (owner): doctrine box set `B = {M,0,A,W,S,C,X}` left
  unchanged; only Box A's role description was corrected (user space not added
  to the formal set).

**External publication check:** confirm whether the doctrine or frontier trial
pack was independently frozen under a Zenodo DOI before the Box A correction.
If yes, publish an erratum/correction note; if no, the repository and generated
artifacts are internally consistent.

## 8. Doctrine symbolic notation (3rd legend — recorded for disambiguation)

`MMV_MATHEMATICAL_MODELING_DOCTRINE_RC3_3.md` and the Frontier Trial Pack use a
**symbolic** box notation distinct from §2/§3. Recorded here so the three
legends are not confused:

| Symbol | Doctrine meaning | Reconciliation |
|---|---|---|
| `0` | Box 0 self-reference / system authority | = `box_0` |
| `A` | "user or workspace documents" | 🔴 **superseded** — now Box A = Mobius-foundational; user docs = `box_1-3` |
| `W` | stable encyclopedic knowledge | = Box W / `box_w` (Wikipedia) |
| `M` | session / memory / continuity context | = Box M |
| `S` | search quarantine / transient external search holding surface | = **Box S** (external/web search, Brave; store `data/box_sk/`) — the current external-search box |
| `C` | live verification path | the verification *route* (not a store). This symbolic `C` must not be confused with the Box C reserved document slot; external web search is Box S |
| `X` | curated durable external knowledge | = Box X |

Treat §2/§3 + §7 as the current map; §8 is the doctrine's (partly stale)
symbolic view.

## 9. Local vs Public separation (structural)

Public/private is a **structural property of box membership**, not a per-file
judgement. The public release = the local runtime minus the private containers:

| Box / container | Local | Public release |
|---|---|---|
| **Box 0** (system canonical) | ✅ content | ✅ content |
| **Box A** = **L0 v8.4 only** (System Overview + Mathematical-Modeling Doctrine + L0 protocol) — public canonical | ✅ | ✅ content |
| **Box B / Box C** = reserved document slots | optional local content | empty or isolated; never publish private contents |
| **Box W** (Wikipedia ME5) | ✅ / HF | ✅ via HuggingFace (`fetch_wiki_index.py`) |
| **Box M / X / user space (box_1-3)** | ✅ / runtime | ⛔ runtime/private, not bundled |
| Legacy local Drive harvest under `data/box_b/mobius_drive_library/` | may exist locally from earlier Box A/B experiments | ⛔ **legacy/local-only**; do not treat as the current Box B role |
| **Box H** = internal/historical docs (handovers, autonomous prompts, forensics, briefings) → `box_h/` | ✅ | ⛔ **isolated** (gitignored) |
| **`docs/patent/`** (provisional filings, drawings, attorney work product) | ✅ local | ⛔ **isolated** (gitignored — never publish) |

Rules:
- `data/`, `box_h/`, `docs/patent/`, `.env` are **gitignored** → never enter the
  repo / a push. Private reserved-box contents and patent material live only
  under those.
- The **code (`src/`) is identical** in both — only box *contents* differ. The
  public runtime keeps every box's *functionality*; the private boxes are simply
  empty, so the same code self-adjusts (empty reserved boxes skip in the
  A→B→C→W→S order).
- **Publication uses a clean snapshot** (single commit / orphan), never the full
  local history, because earlier commits' diffs contain patent/attorney material
  and internal docs even though the current tree is clean.
