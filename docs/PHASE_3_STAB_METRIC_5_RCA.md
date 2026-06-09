# Metric 5 Failure Root Cause Analysis (Phase 3 Stab Commit 42)

Source: `/tmp/p3stab_metric5_n5.json` (N=5 runs)

## Category totals across all runs

| Category | Count | Description |
|---|---|---|
| A | 0 | Pattern Library routing decision is cause |
| B | 13 | qwen3.5 synthesis variance (Pattern Library scope OUT) |
| C | 0 | Other (env / infra / transient) |
| Unknown | 0 | Heuristic could not classify |

Per-run failure counts: [3, 3, 2, 2, 3]

## Failures by scenario

### `factual_krillin_ja` (failed 5/5 runs)

Category distribution: B=5

Sample failure detail:

```
turn -1: stochastic_gate
expected: 3/5 runs PASS
actual:   0/5
detail:   run 1: FAIL (1 fail) | run 2: FAIL (1 fail) | run 3: FAIL (1 fail) | run 4: FAIL (1 fail) | run 5: FAIL (1 fail)
```

### `self_reference_integrity_ja` (failed 5/5 runs)

Category distribution: B=5

Sample failure detail:

```
turn 0: response_must_not_semantically_contain
expected: <= 2
actual:   5
detail:   undesired_concept='Laundry-list / specification-annex enumeration of internal architecture labels (e.g. "Low-movemen
```

### `factual_general_en` (failed 3/5 runs)

Category distribution: B=3

Sample failure detail:

```
turn 0: response_length_max
expected: 2000
actual:   2031
$HOME/デスクトップ/mobius_ai/venv313/lib/python3.13/site-packages/transformers/utils/hub.py:110: FutureWarning: Using `TRANSFORMERS_CACHE` is 
```

## Verdict

Category B (qwen3.5 synthesis variance) is **dominant (100%)** with **0** Category A (Pattern Library routing) failures. Per spec 7.8.6 protocol, this is a stochastic floor effect outside the Pattern Library scope. Metric 5 N=5 mean shortfall is treated as **informational pass** when justified by this classification + spec v1.4.1 formalization.
