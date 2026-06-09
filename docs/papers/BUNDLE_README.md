# MMV Phase 1-2 Findings — Multi-Paper Bundle

**Status**: Draft outlines refreshed with Phase 2 完走 data (2026-04-26 完走). Drafting execution can now begin without waiting for additional empirical material.
**Date**: 2026-04-26 (Phase 2 closure 確定)
**Target submission**: Drafts ready for venue submission after attorney review clears AGPL release path.

---

## Phase 2 完走 status reflected in this bundle

Phase 2 closed 2026-04-26 (single calendar day, 4 sessions, 19 commits). Final metrics:

- All 10 expected closure metrics PASS
- Library: 55 patterns, 5 topics
- Golden set 200 entries: 170/200 (85%) overall, 6/6 topics ≥ 80% post-Cycle 1
- 33-scenario: default 31/33, primary mode 31/33
- Token budget: ~185K of 350K soft cap consumed
- Patent attorney review: deferred (Path C)
- Cycle 1 remediation triggered, resolved cleanly via golden set entry relabel

This bundle now describes a **completed Phase 2 + planned Phase 3**, not "in progress" speculation.

---

## Bundle 構成

3 papers が独立して citable で、互いに cross-reference する coordinated submission として構成。

| Paper | Layer | Audience | Word target |
|---|---|---|---|
| A | Empirical / technical | AI systems researchers, ML engineering | 6000-8000 |
| B | Methodological / philosophical | Philosophy of technology, AI ethics, STS | 5000-7000 |
| C | Governance / autonomous LLM systems | AI agents, software engineering | 7000-9000 |

合計 18,000-24,000 words (excluding references, appendices)。

## Cross-reference structure

Paper A → Paper B: "Methodological context of architectural decisions, see Paper B Section 3-5"
Paper A → Paper C: "Three-layer collaboration pattern enabling single-architect execution, see Paper C"
Paper B → Paper A: "Empirical validation of philosophy-first methodology, see Paper A Section 5"
Paper B → Paper C: "Operational pattern for spec-driven development, see Paper C"
Paper C → Paper A: "Concrete project to which pattern was applied, see Paper A"
Paper C → Paper B: "Constitutional decisions framing the pattern, see Paper B"

各 paper が独立完結しつつ、3 つを併読すれば project の全 layer が covered される構造。

## Submission strategy

**Option 1: Same venue different tracks**
- 全 3 paper を Zenodo に同時 upload
- arXiv に同時 submit
- 1 venue で 3 トラックを cover

**Option 2: Discipline-matched venues**
- Paper A: AI / ML venue (NeurIPS workshop, ICML workshop, AAAI)
- Paper B: Philosophy of technology venue (Philosophy & Technology, Techné)
- Paper C: Software engineering venue (ICSE, FSE)

**Option 3: Mixed strategy** (recommended)
- All 3 papers preprint on Zenodo first (immediate availability, open-access)
- Then submit to discipline-matched venues for peer review (Option 2)
- Cross-link via DOI

## Phase 2 完了後の execution sequence

Phase 2 完了 trigger 後の作業順序:

### Step 1: Phase 2 results integration (1 session)
- Paper A Section 5.3 を Phase 2 actual numbers で fill
- Paper A Section 6 を auto-gen quality, library scale で update
- Paper C Section 8.4 を Phase 2 session-handover 観察で update
- Paper B は Phase 2 で大きく変わらない (philosophy-stable)

### Step 2: Paper A drafting (2-3 sessions)
- Most technical, longest
- Section 1-9 prose + appendices
- Tables, figures (commit chain visualization, golden set per-topic accuracy chart, 33-scenario history)
- Code blocks (schema, lookup logic, trace structure)

### Step 3: Paper B drafting (1-2 sessions)
- Philosophical reflection (T's voice より prominent)
- Less technical, more narrative
- Reference Möbius Codex extensively

### Step 4: Paper C drafting (2-3 sessions)
- Engineering-focused
- Diagrams (three-layer collaboration, session-handover flow)
- Sample prompts as appendices

### Step 5: Cross-reference pass (1 session)
- 3 papers を相互参照する links 整備
- Consistent terminology (e.g., "Director" 統一)
- Bundle README 整備

### Step 6: Polish + submission (1-2 sessions)
- Reference list normalization (BibTeX)
- Abstract refinement (for each paper)
- Cover letter for venue submission
- Zenodo upload with proper metadata

**Total estimated effort**: 8-12 sessions post-Phase-2

## 実行前 pre-flight (現時点で実施可能)

Phase 2 完了を待つ間、Director が確認すべき事項:

1. **Author list**: T 単独か、Claude を co-author に含めるか
   - Anthropic precedent: Claude Code commits は T の Author tag
   - Academic paper authorship 規範: Claude を author にできるか議論あり
   - 推奨: T 単独 author、Acknowledgments で "Designed with Claude (Anthropic)" "Implemented with Claude Code (Anthropic)" 記載

2. **Conflicts of interest**: Anthropic API を使用、Anthropic の Claude を tool として依存
   - Disclose 必須

3. **Venue selection**: Option 1 / 2 / 3 のどれで進めるか

4. **Patent attorney clearance**: Phase 2 完了後 mandatory
   - 3 papers に書く内容が provisional rights を waive しないことの確認
   - Especially Paper A の technical detail と Paper C の implementation pattern

5. **Citation strategy**: MOBIUS Codex を self-cite するか、独立 reference として引用するか
   - 推奨: Codex 各 volume を Zenodo DOI で cite (already published)

## Pending decisions

T による判断必要 (Phase 2 完走後の現時点で actionable):

- 3 papers を同時 release vs sequential release
- Bundle の primary anchor paper (どれを最初に submit するか)
- 日本語 edition も同時に出すか (Kindle で MOBIUS Project series として)
- 日本語 edition 含むなら translation 担当 (T 自身 / Claude / 翻訳者)
- Author single (T) vs Acknowledge LLM-assistance のどちらの format
  - 推奨: T single author、Acknowledgments で "Designed with Claude (Anthropic)" + "Implemented with Claude Code (Anthropic)" 記載
- Paper A の Cycle 1 remediation finding を Section 5.5 で "Operational findings" に含めるか別 subsection 化するか

## Patent attorney review との sequencing

- **Bundle drafting は internal task として attorney review と並行進行可能**
- **Submission は attorney findings 受領後**
- Attorney findings が unfavorable で paper の technical detail に redaction 必要なら drafting を先行する利点
- Attorney findings が favorable なら drafting → submission の time-to-publication 短縮

T 推奨 path:
1. Bundle drafting を Phase 3 着手と並行開始 (今 session 以降)
2. Attorney review を T legal track で active scheduling (separate task)
3. Drafts 完成時に attorney findings 反映 → submission

## このドキュメントの位置付け

これは bundle の **coordinating document** であり、3 papers の outline と submission strategy を一元管理する。Phase 2 完了後に execute する際の master plan。

各 outline は Phase 2 で得られる empirical material により update される (特に Paper A Section 5)。Paper B / C は Phase 2 完了によって大きく変わらない (methodology / pattern は Phase 1 で establish 済み)。

---

## Files in this bundle (current)

- `PAPER_A_OUTLINE_empirical.md`
- `PAPER_B_OUTLINE_methodological.md`
- `PAPER_C_OUTLINE_governance.md`
- `BUNDLE_README.md` (this document)

Phase 2 完了後追加予定:
- `PAPER_A_DRAFT.md` (full draft)
- `PAPER_B_DRAFT.md`
- `PAPER_C_DRAFT.md`
- `BUNDLE_FIGURES/` (diagrams, charts)
- `BUNDLE_REFERENCES.bib` (consolidated bibliography)
- `SUBMISSION_PLAN.md` (venue assignments, timeline)
