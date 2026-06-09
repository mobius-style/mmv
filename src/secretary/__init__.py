"""MOBIUS Pattern Library Secretary — Phase 3 Commit 36.

Proposal-only auto-improvement loop scaffolding. The Secretary
observes routing decisions (via hit-count tracker, audit findings,
user proposals) and emits PROPOSALS for human review. It NEVER
mutates `config/pattern_library/*` directly — that requires T
approval per HARD CONSTRAINT 7 in the Phase 3 prompt.
"""
from __future__ import annotations

from src.secretary.secretary_core import (  # noqa: F401
    Proposal, ProposalStore, Secretary,
)
