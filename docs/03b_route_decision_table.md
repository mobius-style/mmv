# 03b Route Decision Table

| Condition | Primary route | Notes |
|---|---|---|
| Safety violation or inadmissible request | abstain | final route |
| Target/timeframe/constraints unclear | ask | search disabled |
| Clear question, evidence external or freshness-sensitive | verify | retrieval/web may run |
| Clear, low-stakes, answerable from current state | answer | then apply answer-shaping |

## Edge cases
### Ambiguous + recency-sensitive
Ask first. Do not verify a vague target.

### Verify fails because evidence is unavailable
If the failure is epistemic, return `abstain with reasons`.
If the failure is primarily missing specification, return `ask-back`.

### Deep but ordinary question
Use `answer` plus answer shaping only if reframing is nearby and helpful.
Do not force reframing.
