# Evidence for the v11b Wikipedia index

Every number in `WIKI_INDEX_V11.md`, in `REVIEW.md` and in the dataset cards is traceable to a file
here. Two builds are represented, and the distinction matters:

- **v11b** is what ships. Chunk counts: en 15,648,632 · ja 3,009,820 · zh 3,367,718.
- **v11a** was the first build. Three commissioned reviewers rejected it, it was never published,
  and it was rebuilt. Chunk counts: en 15,696,612 · ja 3,008,848 · zh 3,360,260. Logs measuring it
  carry `_v11a` in the name and are kept because `REVIEW.md` cites them as the "before" side.

## Documents

| file | what it is |
|---|---|
| `WIKI_INDEX_V11.md` | the release note: what was wrong, what changed, what was measured |
| `WIKI_INDEX_FORENSICS_PAPER_v1_0_rc.md` | the working paper, with the three review rounds reported at the same level of detail as the results |
| `REVIEW.md` | all three review rounds, their findings, and what was done about each |

## Acceptance — the shipped artifacts

| file | what it shows |
|---|---|
| `verify_en_final.log`, `verify_ja_final.log`, `verify_zh_final.log` | **the acceptance evidence for the shipped artifacts.** `verify_wiki_index.py`: row count = FAISS `ntotal` = offsets length = manifest count, `chunk_id` unique, token distribution, two live queries. Exits non-zero on failure. All three PASSED |
| `verify_en.log`, `verify_ja.log`, `verify_zh.log` | **superseded.** These ran before the indexes were re-encoded with the residual-quantile range, so they describe files that were then overwritten. Round 3 of the review caught this; see `REVIEW.md` |
| `build_en.log`, `build_ja.log`, `build_zh.log` | the shipped build runs, including end-to-end throughput |
| `offsets_{en,ja,zh}.log` | the offset table and gzip seek index builds, with their file sizes |
| `reindex_sq4.log`, `reindex_clip.log`, `reindex_clip_en.log` | the two re-encodings of all three indexes from the retained fp16 vectors: FAISS min/max first, then the residual-quantile range that ships |

## Retrieval

| file | what it shows |
|---|---|
| `final_eval_en.log`, `final_eval_ja.log`, `final_eval_zh.log` | the numbers in the cards: whole corpus at nprobe 32 and 128, plus the head-to-head against the previously published store on both question sets |
| `questions_*.json` | the question sets themselves, including the `_oldextract` controls |
| `eval_{en,ja,zh}.json` | the title-query A/B of §6: the benchmark that ranked the defective extractor higher, with chunk counts and footer rates per arm |
| `evalscale_{en,ja,zh}.json` | the same three extractor arms scored with generated questions instead of the title, on ~7,000–8,800-chunk pools |
| `evalqa_{en,ja,zh}.json` | the small-pool question sets those two used |
| `old_vs_new_v11a.log` | the same head-to-head run against **v11a**. Superseded by `final_eval_{ja,zh}.log` |
| `acceptance_full_corpus_v11a.log` | whole-corpus retrieval on **v11a**. Superseded by `final_eval_*.log` |

## Design decisions, each measured before it was made

| file | decision it settles |
|---|---|
| `window_footer_uniform.log` | how much of the published stores ran past the 512-token window, and how much of each store carried the licence footer |
| `sweep_budget.log` | the 256-token budget, against 160 / 360 / 480 |
| `infobox_ab_gpu1.log` | keeping infobox rows in a separate chunk stream, and the arm where that loses |
| `index_types.log`, `index_e2e.log` | `IVF,SQ4` over PQ64, PQ256, PCA+SQ8 and SQ8, by set fidelity and end to end |
| `pq_loss.log` | how much of the exact top-10 the previous `IVF,PQ64` returned |
| `quantizer_lab.log` | percentile clipping against Lloyd-Max levels and a decorrelating rotation |
| `faiss_rangestat.log`, `faiss_range_fix.log`, `faiss_range_residual.log` | the quantiser range. The first attempt clipped raw-vector quantiles and made the index worse; the index encodes residuals. The three runs disagree about `RS_optim`, which `REVIEW.md` records rather than resolves |
| `sizes.log` | bytes per vector, measured on the index files rather than derived |

## After-the-fact verification

| file | what it shows |
|---|---|
| `fix_verification.log` | each v11a defect counted on both stores: navigation-keyword deletion, abbreviation splits, mid-token starts, title leakage in the question set, chunks per gold article |
| `resource_and_coverage.log` | embedding throughput per GPU and precision, fp16-vs-fp32 equivalence, indexed-article coverage. **§C (mean pairwise cosine) is superseded** by `remeasure_v2.log` §B: it drew 2,000 pairs from the head of one embedding file, not 4,000 random pairs of the store |
| `misc_measure.log` | deep-read cost with and without the gzip seek index, the 60-character prose/facts pattern rate, the `chunk_id` collision arithmetic. **§A (licence-string length) is superseded** by `remeasure_v2.log` §A: it measured a string that occurs in no artifact |
| `remeasure_v2.log` | the corrected licence-footer length (184 characters, as it appears in the stores) and the corrected mean pairwise cosine over 20,000 disjoint random pairs of the whole shipped vector set |
| `noise_floor.log` | the standard error of one MRR figure on these question sets, reconstructed from the reported rates because per-question ranks were not retained |
| `forensics.log` | the first pass over the published artifacts, which started all of this |

`WIKI_INDEX_V11.md` (the release note) and `WIKI_INDEX_FORENSICS_PAPER_v1_0_rc.md` (the working
paper) also ship here, so the evidence and the documents that cite it travel together.

The `.py` files beside the logs are the scripts that produced them. In the GitHub repository the
build pipeline itself — `build_wiki_index_me5_bplus.py`, `build_offsets.py`, `reindex_sq4.py` and
the acceptance script `verify_wiki_index.py` — lives in `scripts/`, not here; copies ship beside the
logs in each dataset repository.

Where two logs measure the same quantity, the later one is named as superseding the earlier in the
tables above. Three such corrections exist, all found by round 3 of the review; `REVIEW.md` lists
what each earlier measurement got wrong.

## What this evidence does not establish

The question sets are synthetic, generated by one local model, with no human relevance judgements
and no check that a question is answerable from its gold article; the reconstructed standard error
of one MRR figure on them is 2.2–2.9 points. Every reviewer was a model instance commissioned by the
author. Every index-type and quantiser number comes from 150 k–206 k-vector pools at three different
partition settings, not from the shipped 3–15.6 M-vector indexes. Nothing here is peer reviewed,
certified, or independently replicated.
