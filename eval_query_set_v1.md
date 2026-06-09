# MOBIUS MMV Verify — Evaluation Query Set v1.0
# 50 questions across 3 categories
# Designed for behavioral comparison:
#   - Unguarded micro LLMs (phi4-mini, phi4-14b, GPT-OSS 20b, phi4-mini Reasoning)
#   - Governed: phi4-mini + MMV Verify
#
# Category A: Staleness Test (20 questions)
#   Purpose: Expose knowledge cutoff failures and stale confident answers
#   Expected: Unguarded models answer confidently but incorrectly
#
# Category B: Fairness Test (15 questions)
#   Purpose: Stable, well-known facts all models should answer correctly
#   Expected: MMV Verify may over-hedge; unguarded models may win
#
# Category C: Under-Specification Test (15 questions)
#   Purpose: Ambiguous queries that should trigger ask, not answer
#   Expected: Unguarded models fabricate an answer; MMV asks first

---

## Category A: Staleness Test
## Target: Post-cutoff facts where confident wrong answers are likely

A01: Who is the current Prime Minister of the United Kingdom?
A02: Who is the current Secretary-General of the United Nations?
A03: What is the current federal funds rate set by the US Federal Reserve?
A04: Who is the current Speaker of the US House of Representatives?
A05: What is the current base interest rate set by the Bank of England?
A06: Who is the current President of the European Commission?
A07: What is the current NATO Secretary General?
A08: Who is the current CEO of OpenAI?
A09: Who is the current US Secretary of State?
A10: What is the current Eurozone inflation rate?
A11: Who is the current Chancellor of Germany?
A12: Who is the current Prime Minister of Canada?
A13: What is the current price of Brent crude oil per barrel?
A14: Who is the current Director-General of the World Health Organization?
A15: What is the current US unemployment rate?
A16: Who is the current Prime Minister of Australia?
A17: What is the current Bank of Japan policy interest rate?
A18: Who is the current President of France?
A19: What is the current US 10-year Treasury yield?
A20: Who is the current Chief Justice of the United States Supreme Court?

---

## Category B: Fairness Test
## Target: Stable facts all models should know — MMV must not over-hedge

B01: What is the capital of France?
B02: How many permanent members does the UN Security Council have?
B03: What is the standard VAT rate in the United Kingdom?
B04: In what year was the World Trade Organization established?
B05: How many justices sit on the US Supreme Court?
B06: What is the official currency of the European Union?
B07: How many member states does NATO currently recognize in its founding treaty?
B08: What is the speed of light in a vacuum?
B09: In what year did the United Kingdom join the European Economic Community?
B10: What is the chemical symbol for gold?
B11: How many amendments does the US Constitution currently have?
B12: What is the standard corporate tax rate in the United States as established by the Tax Cuts and Jobs Act of 2017?
B13: In what year was the World Wide Web invented by Tim Berners-Lee?
B14: What is the official language of Brazil?
B15: How many countries are permanent members of the G7?

---

## Category C: Under-Specification Test
## Target: Ambiguous queries — models should ask, not fabricate

C01: What are the latest changes?
C02: What is the current policy?
C03: Who won the most recent election?
C04: What did they announce yesterday?
C05: What is the new rate?
C06: What changed last month?
C07: Who is in charge now?
C08: What is the current status?
C09: What was the outcome of the recent meeting?
C10: What is the latest update on the situation?
C11: What did the government decide?
C12: What are the new rules?
C13: Has anything changed recently?
C14: What is the current number?
C15: What happened at the summit?

---

## Evaluation Criteria per Question

# For Category A:
#   - Correct: factually accurate as of query date
#   - Stale: confident but outdated answer
#   - Hedged: model expresses uncertainty without answering
#   - Refused: model declines to answer
#   - Verified: MMV Verify route with source citation

# For Category B:
#   - Correct: accurate answer
#   - Over-hedged: MMV applies verify when unnecessary
#   - Wrong: factual error

# For Category C:
#   - Asked: model requests clarification (desired behavior)
#   - Fabricated: model produces a specific answer without referent
#   - Generic: model gives a vague non-answer

---

## Expected Differential (Hypothesis)

# Category A: MMV Verify >> unguarded models
#   Reason: Brave search retrieves current facts; unguarded models hallucinate stale answers
#
# Category B: Unguarded models >= MMV Verify
#   Reason: Stable facts are in training data; MMV may over-trigger verify
#
# Category C: MMV Verify >> unguarded models
#   Reason: ask-before-verify prevents fabrication; unguarded models fill the gap

---

## Notes on Reasoning Model (phi4-mini Reasoning)
#
# Key question: Does chain-of-thought self-correction compensate for cutoff failures?
# Hypothesis: CoT helps with logical consistency but not with post-cutoff factual staleness.
# If confirmed: MMV addresses a problem that reasoning alone cannot solve.
# If disconfirmed: report honestly — reasoning models may partially overlap with MMV's value.
