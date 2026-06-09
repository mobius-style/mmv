# Release Notes — v7.4.8 MMV Runtime Bundle

## Nature of this release
This is an implementation starter bundle aligned to Möbius L0 v7.4.8 frontier synchronization and the finalized MMV runtime blueprint.

## Main additions
- route / answer-shaping separation in source layout
- verify semantics with success / partial / failed
- route-driven simple RAG and web verification boundaries
- active_language state tracking
- kernel-level B-lite language detection policy
- Python source scaffold for runtime development

## Benchmark honesty
No fresh benchmark claim is made in this bundle.


## Update note
- retrieval selector corrected to enforce local-RAG-first behavior for verify
- regression test added for retrieval plan selection


## Update 2
- Fixed routing tests to align with ask/verify precondition rules.
- Replaced ambiguous freshness test with explicit ask-case and specified verify-case.


## Update 2.1
- Removed `__pycache__/`, `.pytest_cache/`, and `*.pyc` from the distribution bundle.
- Added `.gitignore` entries to keep future bundles clean.
