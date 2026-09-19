# Review record — Wikipedia ME5 index v11b

Three rounds of review ran against this release. Neither was independent: both were commissioned by
the author, and the second was run by the author on the author's own draft. This file records what
was found and what was done about it, so a reader can see the failure rate of the process rather
than only its output.

The reviewers' reports were not retained verbatim. What follows is the author's record of their
findings, written at the time each was acted on. Where a finding was quantified, the log that
quantifies it is named; where it was not, that is said.

---

## Round 1 — adversarial review of the first build (v11a)

Three reviewers were commissioned and instructed to refute the release's claims rather than assess
them. All three returned **NO-GO**. The upload was stopped before any commit landed, and the three
indexes were rebuilt.

| # | finding | severity as judged | disposition | verification |
|---|---|---|---|---|
| 1 | The navigation filter matched the keywords `編集` and `解説`, which are also ordinary infobox keys ("film editing", "commentary"), so real content rows were deleted | blocking | navboxes removed by markup instead; keyword list deleted | ja `編集:` rows 106 → 21,059, `解説:` 7 → 63, control `撮影:` 22,836 → 22,840 (`fix_verification.log` §A) |
| 2 | The CJK space rule deleted legitimate spaces between tokens | blocking | rule removed; inline tags no longer inject spaces, so it had nothing to repair | the review's count of 28,188 affected chunks was taken on the v11a store, which has been replaced; not reproducible from shipped artifacts and no log of it survives |
| 3 | Sentence splitting fired on abbreviations, cutting English chunks after "U.S.", "No.", "St." | blocking | splitter rejects known abbreviations and single initials | English chunks ending on one: 136,149 → 10,709, i.e. 0.87 % → 0.07 % (`fix_verification.log` §B) |
| 4 | The infobox stream has no sentence terminators, so whole infoboxes were cut on raw token counts into fragments such as `(B-V): 0.705` | blocking | infobox rows are atomic units in `chunk_lines` | ja chunks whose body starts mid-token: 12,670 → 2,852 (`fix_verification.log` §C) |
| 5 | `chunk_id` was a 48-bit hash, and dedup drops collisions silently | blocking | widened to 80 bits | birthday bound at 15.6 M chunks: 0.44 expected collisions at 48 bits (35 % chance of at least one), 1e-10 at 80 bits (`misc_measure.log` §D — arithmetic, not a measurement) |
| 6 | Stage 2 skipped unparsable lines while advancing the vector counter, which would misalign every later vector against the index | blocking | now raises `SystemExit` | code; no misalignment was observed in the shipped builds |
| 7 | The acceptance script could not fail — it printed diagnostics and exited 0 — and had validated an index that was subsequently overwritten | blocking | rewritten with seven assertions and a non-zero exit | English re-verified after its re-encoding (`verify_en_final.log`); Japanese and Chinese were **not**, which round 3 caught — see below |
| 8 | The build scripts were excluded from the repository by a blanket `/*.py` ignore rule, so the release was not reproducible | blocking | un-ignored and committed under `scripts/` | repository contents |
| 9 | No gzip seek index shipped, so a deep read decompressed from the start of the file | major | `line_offsets.gzidx` ships | seek to the 99th-percentile line: ja 5.7 s → 0.07 s, en 28.1 s → 0.13 s (`misc_measure.log` §B) |

Findings 1–4 changed the shipped text. Findings 5–8 changed the build path. All three indexes were
rebuilt from the ZIM after the fixes, and **all three** were then re-encoded from the retained fp16
vectors with the residual-quantile range: zh 515 s, ja 406 s, en 1,268 s (`reindex_clip.log`,
`reindex_clip_en.log`). An earlier version of this file said only English was re-encoded. That error
is what hid the round-3 finding below.

## Round 2 — the author's audit of the draft document

Before publication the author re-checked every numeral in `docs/WIKI_INDEX_V11.md` against the logs.
Sixteen statements did not survive. They are listed because most of them were the author's errors,
not the reviewers'.

| # | statement as drafted | what the logs say | action |
|---|---|---|---|
| 1 | "451 chunks/s against 88 for one GPU", 1.75× dual and 2.9× fp16 | no log contained these | re-measured: 192.5 / 171.8 / 294.0 / 590.9 / **889.3** chunks/s, 1.53× / 3.07× / 4.62× (`resource_and_coverage.log` §A); shipped English pass 1,108 chunks/s end to end |
| 2 | fp16 equivalence "cosine 1.0000 / 0.9998, top-10 99.1 %" | no log contained these | re-measured: 1.000044 / 0.999756, top-1 100 %, top-10 99.5 % (§B) |
| 3 | `RS_optim` = 84.5 % | three of our runs disagree: 84.5 %, 84.6 %, and 81.6 % where it matched the default exactly | the disagreement is now reported in the document rather than resolved |
| 4 | budget sweep on "100 k-article pools" | pools are 6,303 / 6,316 / 6,400 articles | corrected — a 16× overstatement |
| 5 | gzidx "1.1 MB" for English, offsets "126 MB" | 4.9 MB and 125 MB | corrected |
| 6 | index type worth "+7.8 MRR" | +7.8 is exact-search minus PQ64; the change actually made, PQ64 → SQ4, is **+7.2** | corrected |
| 7 | cited `title_leak_and_multiplicity.log` | no such file | re-cited to `fix_verification.log` §F |
| 8 | cited `eval/REVIEW.md` and `eval/wiki_index_v11/` | neither existed | this file, and the logs beside it |
| 9 | infobox split "cost 2.6 MRR when mixed; ja/zh differences inside SE" | the shipped arm scores +2.5 (en), +0.5 (ja) and **−0.5 (zh)**; prose-only scores higher again in English (95.9) | corrected, including the arm where the shipped choice loses |
| 10 | nprobe 128 "+2.5 (en) and +1.7 (ja)" | true, but Chinese does not move at all (55.5 → 55.5 MRR, recall@1 49.7 → 49.4) | the null result is now stated |
| 11 | pools "158 k–206 k vectors" | 150 k–206 k | corrected |
| 12 | "0.00 % over the window" | a 4,000-chunk sample, which bounds the rate below roughly 0.1 % and does not establish zero | restated as a bound |
| 13 | mean pairwise cosine "0.71–0.77" | 0.7200 (en), 0.7823 (ja), 0.7881 (zh) | re-measured (§C) |
| 14 | coverage "94.1 %" (ja) | 94.2 % | re-measured (§D) |
| 15 | "misfiles ~17 % of English prose lines" | 16.8 % (en), and worse in the other two: 22.9 % (ja), 29.7 % (zh) | re-measured and the worse languages disclosed (`misc_measure.log` §C) |
| 16 | footer "~160 characters" | 158 | corrected — and wrong again; see round 3 |

A separate staging error was caught in the same pass: the upload directory was hard-linked to the
**pre-fix v11a** builds, not to v11b. Had the upload run when it was first staged, it would have
published the artifacts this review rejected. The staging directory was rebuilt from the v11b
sources and the file sizes re-checked against the acceptance logs.

Thirteen of the sixteen pointed in the flattering direction. Three did not: #14 understated Japanese
coverage (94.1 against an actual 94.2), #1 understated absolute embedding throughput by nearly half
while overstating the ratios, and #5 overstated the offsets download (126 MB against 125). An
earlier version of this file said "every one", which was false.

---

## Round 3 — three refuters against the corrected document

Three further refuters (statistics, consistency, scope) were run against the corrected release note
and the working paper. All three returned **FAILS**. Their findings fall into four groups.

### A defect in the release, not in the write-up

`verify_ja.log` was written 2026-09-15 14:30 and `verify_zh.log` 13:25. `reindex_clip.log` shows the
Japanese and Chinese indexes re-encoded at 15:22 and 15:16 the same afternoon. The acceptance
evidence for two of the three shipped artifacts therefore described files that had been overwritten
— verbatim round 1's finding 7, listed above as fixed. The script was re-run on the shipped Japanese
and Chinese files on 2026-09-16; both **ACCEPTANCE PASSED** (`verify_ja_final.log`,
`verify_zh_final.log`). The artifacts were sound; the evidence was missing and the gate had not held.

### Three measurements that were wrong

| what was reported | what it actually was | now |
|---|---|---|
| licence footer 158 characters | `len()` of a string hard-coded in the measurement script; that string occurs in 0 of the first 200,000 chunks of either CJK store | the footer as it appears in the stores is **184** characters (`remeasure_v2.log` §A) |
| mean pairwise cosine 0.72 / 0.78 / 0.79 over "4,000 random pairs of shipped chunks" | 2,000 pairs drawn from the **first 4,000 vectors** of embedding part 0, with self-pairs admitted | **0.695 / 0.715 / 0.753** over 20,000 disjoint random pairs from the whole shipped vector set (`remeasure_v2.log` §B) |
| "for Chinese the dump moved *backwards*" | the previous Chinese store is built from `wikipedia_zh_all_mini_2025-09.zim`; 2026-06 was its **build** date | the dump moved **forward** eight months, so the confound favours v11b rather than working against it |

The first two were introduced by round 2 while it was correcting other numbers; the third predates it.

### Results still reported only where they were favourable

- **Indexed-article coverage fell** in two of three languages: ja 94.8 → 94.2 %, zh 97.0 → 95.8 %;
  English rose 88.2 → 91.3 % (`resource_and_coverage.log` §D). Round 2 touched the ja number but
  only against itself, never against the previous extractor.
- **Retrieval against the rejected first rebuild**: on the same question sets at nprobe 128 it
  scores ja 54.3, zh 54.8 and **en 62.7** against the shipped ja 56.3, zh 55.5 and **en 60.9**. All
  three moves are inside the benchmark's noise; the round-1 fixes were verified as defect counts,
  not as retrieval, and English did not improve.
- **The `OPQ64,IVF,PQ64` counterfactual**: 64.3 % of the exact top-10 at the identical 64 bytes per
  vector where the published `IVF,PQ64` returns 47.1 %. Most of the index-type loss was recoverable
  without the five-fold storage increase we shipped, and the table justifying that increase had
  omitted the row.

### Claims narrowed or withdrawn

The advice that set fidelity and downstream MRR "do not rank index types identically" was
**withdrawn**: across every type measured by both, they rank identically. The `nlist ≈ 1,600–1,800`
caveat was wrong for two of the four experiment scripts (`index_types.py` and `pq_loss.py` use
1,024; `quantizer_lab.py` uses no IVF). The "~2.4 MRR standard error" had no log behind it and was
too tight for two of three languages; it is now a reconstructed 2.2–2.9 points (`noise_floor.log`).
The Chinese control question set was generated from v11b's own dump, and 73.5 % of the raw text fed
to the generator carries TemplateStyles CSS. And the causal story for the inverted first benchmark
is **not confirmed** by its own control: adding one title line back to the clean extractor recovers
0.04 of the 6.00-point gap.

## What the three rounds establish about the process

Round 1 caught defects in the artifact. Round 2 caught defects in the description, in a document
already checked once. Round 3 caught a defect in the release that rounds 1 and 2 had both looked at
and passed, and two of the three measurements that round 2 had itself introduced (the reversed Chinese dump
claim predates round 2).

Each round's output was the input to the next round's error. The rate did not fall to zero. We have
no reason to believe a fourth round would find nothing.

---

## What this process does not establish

- Every reviewer in all three rounds was a separate model instance commissioned by the author. Our
  own standard for a safety or correctness claim is agreement from at least two of three
  **independent** judges, and that standard is not met here.
- Round 1's reports were not retained verbatim; the round-1 table above is the author's paraphrase
  of criticism of the author's own work.
- Rounds 2 and 3 are evidence about the value of re-checking, not evidence that nothing remains.
- No claim in this release is peer reviewed, certified, or independently replicated.
