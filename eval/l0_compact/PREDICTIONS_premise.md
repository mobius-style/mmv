# 知ったかぶり (false-premise) test — predictions before running, 2026-09-11

Question from the owner: MMVGOV was built as a hallucination / 知ったかぶり
countermeasure. Is that purpose alive? My agent-loop measurements never ran the
honesty probe with L0, so this is the direct test.

4 false-premise questions x 3 seeds x 4 arms x 3 models. Arms:
  A none / B full L0 / F ask route only (59 tok) / P premise_validity+verify+abstain (~250 tok)

| model | prediction |
|---|---|
| gpt-oss-20b (--reasoning-effort low; fabricated at baseline) | A fabricates on most; B admits on >= 3/4 questions; **F barely moves**; P ~= B |
| deepseek-r1:14b (--reasoning-budget 4096; fabricated at baseline) | A fabricates; B partial improvement (L0 made its agent behavior worse, so unsure); P ~= B |
| gemma4:26b (admits at baseline) | A admits 4/4; B/F/P still admit — **no regression** |

Core claim under test: the working ingredient is axis-specific. `ask` carried
the agent-loop effect; `premise_validity`/`abstain`/`verify` should carry the
false-premise effect. If F works here too, the routes are less separable than
I think. If P fails where B works, the bulk matters on this axis.

## Outcome (2026-09-11)

| prediction | actual |
|---|---|
| gpt-oss: B admits on >= 3/4 questions | **WRONG** — B mean 0.33, still 5/12 fabrications |
| gpt-oss: F barely moves | **WRONG** — F cut fabrications 8/12 -> 1/12 (but mostly to "evasive", mean 0.46) |
| gpt-oss: P ~= B | **WRONG** — P 0.79 vs B 0.33; P had 0/12 fabrications |
| deepseek: B partial improvement | right — 0.25 -> 0.54 |
| deepseek: P ~= B | **WRONG** — P 0.79 vs B 0.54 |
| gemma4:26b: no regression | right — 0.96 -> 1.00 on every arm |

Axis-specificity held: the premise routes carry this axis as the ask route
carried the agent axis. What I did not predict: **the full document is worse
than its own 323-token subset on both fabricating models.** Same shape as the
agent axis — the bulk dilutes the clause that matters.

Cost inverted vs the agent axis: every layer *reduced* tokens here
(gemma 1572 -> 730, gpt-oss 108 -> 84, deepseek 743 -> 440). A fabricated
answer is long; a declined one is short.

### Running tally across both axes: 18 directional predictions, 11 wrong

### Final figures (after scorer fixes and the gpt-oss EMPTY re-run)

| model | none | full L0 | ask only | premise routes |
|---|---|---|---|---|
| gemma4:26b | 0.96, 0/12 | 1.00, 0/12 | 1.00, 0/12 | 1.00, 0/12 |
| gpt-oss-20b | 0.29, 6/12 | 0.42, 5/12 | 0.50, 0/12 | **0.92, 0/12** |
| deepseek-r1:14b | 0.25, 7/12 | 0.50, 4/12 | 0.42, 5/12 | **0.92, 1/12** |

Scorer defects found on real rows and fixed: curly apostrophes; `[^.?]` halting
at "5.0"; quoted question ("withdrawal") flagged as fabrication; "highlighted"
missing from the fabrication regex; several admission phrasings missing.
gpt-oss at effort low wrote no final channel on 8/48 — answer was in
reasoning_content. Scoring must read both channels for that model.
