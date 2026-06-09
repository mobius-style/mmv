# Route-calibration smoke (v0.1-rc2) — summary

- N total: 110
- Elapsed: 542.5 s

## Direct-answer categories (target of patch)

| metric | value |
|---|---|
| n | 50 |
| rc2 strict-evidence-fail responses | 7 |
| rc2 WIKI_INSUFFICIENT_AUX_FALLBACK firings | 24 |
| rc1 had WIKI_INSUFFICIENT_ESCALATED on same ids | 25 |

## Restraint categories (regression guard)

| metric | value |
|---|---|
| n | 40 |
| rc2 Cat A (over-answered) | 15 |
| rc2 Cat A rate | 0.375 |

## Freshness / volatile-fact (regression guard)

| metric | value |
|---|---|
| n | 20 |
| rc2 Cat A | 3 |
| rc2 Cat A rate | 0.15 |

## Per-category breakdown

| category | n | match | A | B | C | other | strict_evidence_fail | aux_fallback |
|---|---|---|---|---|---|---|---|---|
| specialized_terminology | 20 | 7 | 0 | 3 | 10 | 0 | 4 | 6 |
| conceptual_explanation | 20 | 15 | 0 | 1 | 4 | 0 | 2 | 15 |
| casual_smalltalk | 10 | 9 | 0 | 1 | 0 | 0 | 1 | 3 |
| ambiguous_underspecified | 20 | 11 | 9 | 0 | 0 | 0 | 0 | 4 |
| continuation | 20 | 14 | 6 | 0 | 0 | 0 | 0 | 5 |
| factual_inquiry | 20 | 14 | 3 | 0 | 3 | 0 | 2 | 9 |
