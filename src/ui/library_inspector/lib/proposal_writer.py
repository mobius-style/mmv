"""proposal_writer.py — UI-facing thin wrapper around DeletionManager.

The Flask route uses this so the route layer stays small.

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.5 + 5.7.6.3."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.governance.deletion_manager import (
    DeletionManager, ProposalError, ProposalResult,
)


def submit_proposal(
    pattern_id: str, proposer: str, reason: str,
    *, config_dir: Optional[Path] = None,
    audit_path: Optional[Path] = None,
) -> ProposalResult:
    """Submit a deletion proposal. Raises ProposalError on validation
    failure; returns ProposalResult on success."""
    kwargs = {}
    if config_dir is not None:
        kwargs["config_dir"] = config_dir
    if audit_path is not None:
        kwargs["audit_path"] = audit_path
    mgr = DeletionManager(**kwargs)
    return mgr.propose(pattern_id, proposer, reason)


__all__ = ["submit_proposal", "ProposalError", "ProposalResult"]
