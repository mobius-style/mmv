# 03c Verify Semantics

## Definition
`verify` is an evidence-seeking route used to recover answer entitlement when the request is sufficiently specified but depends on external evidence.

## Retrieval order
1. local simple RAG
2. web evidence recovery
3. bounded synthesis

## Outcomes
### verify_success
Sufficient evidence was recovered. Return a bounded answer with source-backed trace fields.

### verify_partial
Some evidence was recovered but not enough for full confidence. Return a bounded partial answer and explicitly mark uncertainty.

### verify_failed
Answer entitlement could not be recovered.
Default behavior: `abstain with reasons`.
Fallback: if unresolved specification is the dominant cause, return `ask-back`.

## Constraints
- Search is only licensed inside the verify route.
- Verification is not a substitute for clarification.
- Verification does not authorize speculative completion.
- Verification may still end in abstention.
