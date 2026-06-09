# OPERATE-FR — Non-Assertion Covenant (draft)

> **Draft; subject to legal review. Not legal advice.**

This covenant accompanies the OPERATE-FR v0.1 specification and runnable
artifact. Its purpose is to clarify what claims operators of evaluations
may and may not make about results obtained with this benchmark track.

## 1. Scope

This covenant applies to:

- Any party that publishes evaluation results obtained by running
  OPERATE-FR v0.1 (Smoke-100 or any successor suite released under this
  spec) against a system.
- Any party that incorporates the OPERATE-FR data, labels, classifier,
  scorer, or harness in a derivative benchmark.

## 2. Status disclosure

OPERATE-FR v0.1 is a **candidate operational benchmark track**. It is
**not** a validated standard benchmark. Operators must:

- Describe v0.1 results as obtained from a candidate track, not from a
  standard benchmark.
- Not represent the OPERATE-FR taxonomy, dataset, or scorer as
  industry-endorsed or independently validated until external validation
  exists.

## 3. Composite-score discipline

- v0.1 does not define an official composite score.
- Operators must report the component vector (route correctness,
  stale-commitment rate, over-verification rate on stable controls,
  date-boundary clarity rate, verification completion rate, response
  length, latency, failure-mode counts).
- Operators may publish optional internal scorecards but must:
  - Label them clearly as non-official.
  - Disclose all weights, normalisations, and exclusions.

## 4. Comparative claims

- Operators must not claim that any system is "best" on OPERATE-FR
  unless their report shows the cost-side trade-offs as well as the
  freshness-side gains.
- If a system does not lose on at least one cost-side dimension
  (latency, response length, friction, directness on stable controls),
  operators should treat this as a stress-test trigger for the
  benchmark itself, not as proof of universal superiority for the
  system.
- Operators of MOBIUS-MMV-originating systems must report MMV results
  in a separate MMV-side technical report and must not present them as
  the lead result in a neutral baseline report.

## 5. Adjudication transparency

- Operators must publish or link the route-adjudication rules they used.
- Operators must not rely on an LLM judge as the sole route classifier.
- If an operator augments OPERATE-FR's rule-based classifier, that
  augmentation must be disclosed and the rule-based baseline reported
  alongside.

## 6. Data and privacy

- Operators must not log API keys, secrets, or proprietary prompts beyond
  what the benchmark requires.
- If full conversation logs are retained, operators must publish their
  retention and access policy.

## 7. Variant releases

- Any variant of OPERATE-FR (renamed, re-weighted, language-extended,
  domain-extended) must:
  - Cite OPERATE-FR v0.1 as origin.
  - Indicate the diff against v0.1.
  - Not use the unqualified name "OPERATE-FR" if the routing taxonomy
    or scorer differs from this spec.

## 8. Revision

This covenant is provisional. It will be re-issued upon external legal
review and upon external validation of the OPERATE-FR taxonomy. Until
that point, the header notice (Draft; subject to legal review; not legal
advice) takes precedence over any specific clause.
