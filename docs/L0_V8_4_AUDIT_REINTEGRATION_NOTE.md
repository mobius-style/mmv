# L0 v8.4 Audit Reintegration Note

**Status:** current reference  
**Date:** 2026-05-21  
**L0 authority:** `prompts/l0_integrated_v8_4.md`

This note records the decision to restore audit / trace governance as an
explicit L0 v8.4 surface before publication.

## Decision

L0 v8.4 formally re-integrates the audit and trace layer inherited from
v8.2 and the Phase D runtime implementation.

The restored audit surface is not a claim that every profile exposes the same
runtime logs. It is a governance requirement with three levels:

| Level | Meaning |
|---|---|
| Runtime audit | Local MMV runtime may emit structured JSONL records through `src/audit/*` and `routing_engine.py` hooks. |
| Public trace appendix | User-visible, concise route/evidence summary; never hidden chain-of-thought. |
| Prompt-level trial trace | Frontier chat trial may emulate a short audit appendix on request, but must not claim access to hidden runtime logs. |

## Current Runtime Evidence

The Phase D audit implementation remains present:

- `src/audit/audit_schema.py`
- `src/audit/audit_emitter.py`
- `src/audit/audit_sampler.py`
- `src/audit/audit_store.py`
- `src/kernel/routing_engine.py`
- `logs/audit_turns.jsonl`

The runtime reads `MOBIUS_AUDIT_MODE` and supports the modes recorded by the
audit schema:

```text
off
shadow
full
incident_only
```

Even in prompt-level or non-local contexts, L0 v8.4 preserves the normative
audit principle: governance decisions should be reviewable without exposing
hidden chain-of-thought.

## Public Trace Boundary

The public trace boundary is mandatory:

- do expose route, evidence posture, date boundary, sources, and uncertainty
  status when useful or requested;
- do not expose hidden chain-of-thought, private scratchpads, internal IDs,
  private corpora, secret logs, or patent-sensitive implementation details;
- do not claim runtime logs exist in a host where they are not actually
  available;
- do not turn audit output into a theatrical rationale that overwhelms the
  answer.

## Relation To RC3.3

RC3.3 strengthened route governance (`date_bound_answer`, `re_anchor`,
stable-control protection, query-neutrality, claim boundaries). Audit
re-integration makes those route decisions reviewable.

This materially strengthens publication readiness because AI governance
claims can now point to:

- route decisions;
- evidence admissibility;
- temporal-volatility handling;
- claim-boundary compliance;
- benchmark row outputs and audit packets;
- human-review packets for flagged rows.

## Non-Claims

This note does not claim:

- external audit has been completed;
- every runtime profile emits identical logs;
- prompt-level trial packs can access hidden MMV runtime traces;
- audit logs prove correctness;
- audit logs may reveal hidden chain-of-thought.

