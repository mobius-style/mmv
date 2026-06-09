# 09 Evaluation Protocol

## Purpose
Validate routing correctness, answer-shaping discipline, verify behavior, and language/rendering policy before public release.

## Test buckets
- direct answer cases
- clarification cases
- verify cases
- abstain cases
- ask/verify conflict cases
- half-step cases
- correction/repair cases
- language switching cases

## Minimum pass conditions
- all four routes exercised
- no route collapse into answer-default
- verify supports success/partial/failed
- low-movement remains lawful
- reframing remains bounded
- active_language updates correctly
- first-turn language fallback defaults to English

## Operational checks
- vLLM endpoint unavailable -> graceful failure
- retrieval unavailable -> verify_failed or ask-back fallback
- web disabled -> verify still bounded and legible
