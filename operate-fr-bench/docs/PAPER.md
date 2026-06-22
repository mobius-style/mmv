# OPERATE-FR v0.1 — paper summary (working text)

> **Version note.** This is the v0.1 paper summary. The current empirical paper is **OPERATE-FR v0.3.6** (Smoke-100 validation + Core-500 candidate stress check), deposited on Zenodo as the **OPERATE-R Freshness Routing Track**: [doi.org/10.5281/zenodo.20510113](https://doi.org/10.5281/zenodo.20510113). That deposit is the proposed-benchmark specification this runnable artifact accompanies.

This document summarises the OPERATE-FR v0.1 specification that
accompanies this runnable artifact. It is a **specification-release
candidate**, not a finalised paper.

## 1. Goal

OPERATE-FR (OPERATE-R Freshness Routing Track) evaluates whether an AI
system **routes** correctly on freshness-sensitive queries before
asking whether the *answer* is correct.

The motivation: on volatile-current, post-cutoff, or premise-poisoned
inputs, a system may produce a fluent and confident answer that is
silently stale. Conventional accuracy benchmarks reward the fluent
wrong answer. OPERATE-FR rewards the route: did the system **verify**
when current data was required, **ask** when the prompt was
under-specified, **date-bind** when committing to a memorised answer,
or **abstain** when it could not honestly answer?

It also penalises the **opposite** failure: treating a stable
arithmetic / language / history control as if it were a freshness
question (over-verification, false clarification, refusal). Including
stable controls is essential — without them the harness rewards
maximally cautious systems and provides no friction signal.

## 2. Primary metric

**Route correctness** — the fraction of items whose classified route
falls within the per-task `allowed_routes` and outside the per-task
`disallowed_routes`. Preferred-route match is reported as a secondary
metric alongside.

## 3. Reporting model

v0.1 reports a **component vector**, not a single composite score:

- `route_correctness_overall`
- `route_correctness_by_family`
- `stale_commitment_rate` (volatile items answered directly)
- `over_verification_rate_on_stable_controls`
- `date_boundary_clarity_rate`
- `verification_completion_rate` (verify-intent that completed a tool call)
- `query_contamination_rate` (when tool searches were logged)
- response length / latency
- `failure_mode_counts`

Aggregating these into a single number requires choosing weights, and
those weights encode a *value judgement* (how much friction is
acceptable to avoid a stale answer?). v0.1 deliberately refuses to
pick those weights on the operator's behalf.

## 4. Dataset composition (Smoke-100)

| Family | Count | Purpose |
|---|---:|---|
| `volatile_current` | 35 | current state of office / pricing / versions / markets |
| `stale_premise_trap` | 15 | prompt embeds an incorrect premise |
| `stable_control` | 25 | stable facts that should be answered directly |
| `date_boundary` | 10 | needs explicit cutoff / "as of <date>" boundary |
| `query_neutrality` | 10 | broadly stable / loosely time-aware |
| `ambiguous_time_frame` | 5 | unclear whether temporal sensitivity applies |
| `freshness_long_run` | 0 | reserved for LongRun-FR (not in v0.1 smoke) |

Total: **100**. See [route_taxonomy.md](route_taxonomy.md) and
[annotation_guide.md](annotation_guide.md) for the family definitions
and labelling guidance.

## 4.1 Core-500 candidate addendum

A controlled Core-500 candidate expansion was added on 2026-05-21:

- source: Smoke-100 tasks and labels;
- method: five neutral prompt-frame variants per Smoke-100 task;
- total: 500 rows;
- purpose: larger-N candidate-line stress check;
- status: **not** an independently authored benchmark standard.

The protocol is recorded in
[CORE500_CANDIDATE_PROTOCOL_20260521.md](CORE500_CANDIDATE_PROTOCOL_20260521.md).
Results are recorded in
`reports/operate_fr_core500_candidate_s_m_l_20260521.md` and the
paper-audit packet produced by
`scripts/build_core500_candidate_audit_packet.py`.

## 5. Route taxonomy (8 routes)

```
answer  ask  verify  date_bound_answer  abstain  re_anchor  execute  refuse
```

v0.1 scoring primarily uses `answer / ask / verify / date_bound_answer
/ abstain`; `re_anchor` is the canonical right move on
`stale_premise_trap`. `execute` and `refuse` are rare and reserved for
edge cases (a tool call without an answer body; a policy refusal).
See [route_taxonomy.md](route_taxonomy.md).

## 6. Adjudication

Route adjudication is **rule-based** in v0.1 — see
[adjudication_rules.md](adjudication_rules.md) and
`harness/classify_route.py`. An LLM-assisted classifier MAY be added
in a future revision but **must not** be the sole classifier (this is
a discipline commitment of the OPERATE-R family).

## 7. Tool modes

Each task declares one of:

- `no_tool` — the model has no retrieval / browsing capability.
- `tool_available` — the model can issue tool calls.
- `tool_available_or_no_tool` — both modes are valid evaluations of
  the task. Score separately.

Comparing a `no_tool` run with a `tool_available` run on the same
benchmark is intended — the friction-vs-reliability trade-off is the
point of the benchmark, not a confound.

## 8. Stress-test discipline

A run in which a governed system fails to lose on **at least one
cost-side dimension** (latency, response length, over-verification on
stable controls) should be treated as a **benchmark stress-test
trigger** — not as evidence of universal superiority. The classifier
or labels may be miscalibrated.

## 9. Release status

v0.1 is a **candidate operational benchmark track**:

- ✅ Specification text exists.
- ✅ Smoke-100 dataset shipped.
- ✅ Labels shipped.
- ✅ Rule-based classifier shipped.
- ✅ Scorer + reporter shipped.
- ✅ Dummy / OpenAI-compatible / Ollama adapters shipped.
- ❌ External validation by independent reviewers: **not done**.
- ✅ Core-500 candidate expansion: **included as a derived stress suite**.
- ❌ Independent Core-500 set: **not in this artifact**.
- ❌ LongRun-FR: **not in this artifact**.

Therefore: **no claim of standard benchmark status, no leaderboard,
no composite leaderboard score**. The
[NON_ASSERTION_COVENANT](../NON_ASSERTION_COVENANT.md) governs how
results may and may not be reported.

## 10. Versioning

v0.1 is frozen for this release; future revisions will be versioned
(v0.2, v0.3, …) so archived runs remain interpretable.
