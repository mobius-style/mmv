# Review record — Wikipedia ME5 index v11b

Two rounds of review ran against this release. Neither was independent: both were commissioned by
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
| 7 | The acceptance script could not fail — it printed diagnostics and exited 0 — and had validated an index that was subsequently overwritten | blocking | rewritten with seven assertions and a non-zero exit; re-run on the shipped files | `acceptance_full_corpus.log`, `verify_en_final.log` |
| 8 | The build scripts were excluded from the repository by a blanket `/*.py` ignore rule, so the release was not reproducible | blocking | un-ignored and committed under `scripts/` | repository contents |
| 9 | No gzip seek index shipped, so a deep read decompressed from the start of the file | major | `line_offsets.gzidx` ships | seek to the 99th-percentile line: ja 5.7 s → 0.07 s, en 28.1 s → 0.13 s (`misc_measure.log` §B) |

Findings 1–4 changed the shipped text. Findings 5–8 changed the build path. All three indexes were
rebuilt from the ZIM after the fixes; the English index was additionally re-encoded from the
retained fp16 vectors after the residual-range change, which took 21 minutes.

## Round 2 — the author's audit of the draft document

Before publication the author re-checked every numeral in `docs/WIKI_INDEX_V11.md` against the logs.
Twelve statements did not survive. They are listed because most of them were the author's errors,
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
| 16 | footer "~160 characters" | 158 | corrected (§A) |

A separate staging error was caught in the same pass: the upload directory was hard-linked to the
**pre-fix v11a** builds, not to v11b. Had the upload run when it was first staged, it would have
published the artifacts this review rejected. The staging directory was rebuilt from the v11b
sources and the file sizes re-checked against the acceptance logs.

## What this process does not establish

- The reviewers were commissioned by the author. Our own standard for a safety or correctness claim
  is agreement from at least two of three **independent** judges, and that standard is not met here.
- Round 2 was self-review. It caught sixteen errors in a document the author had already checked
  once, which is evidence about the value of re-checking, not evidence that none remain.
- No claim in this release is peer reviewed, certified, or independently replicated.
