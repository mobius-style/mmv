"""deletion_manager.py — user-side deletion proposal flow.

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.5.

Lifecycle on a successful proposal:
    1. Validate the request (proposer pseudonym, reason length).
    2. Generate `proposal_id` = "del_YYYYMMDD_HHMMSS_<hex2>".
    3. Append DeletionProposal to pattern.lifecycle.deletion_proposals.
    4. Set pattern.lifecycle.audit_status = "user_deletion_proposed".
    5. Append LifecycleEvent (event="deletion_proposed").
    6. Atomically rewrite the source JSONL file (all patterns from that
       file are re-serialized with the updated one in place).
    7. Append a record to data/pattern_library/audit_log/proposals.jsonl
       so out-of-band T review has a single feed.

Errors raise ProposalError; the caller is expected to surface a
user-facing message and a 4xx HTTP status.
"""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

from src.retrieval.pattern_schema import (
    DeletionProposal, LifecycleEvent, Pattern,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "pattern_library"
DEFAULT_AUDIT_DIR = REPO_ROOT / "data" / "pattern_library" / "audit_log"
DEFAULT_AUDIT_PATH = DEFAULT_AUDIT_DIR / "proposals.jsonl"

MAX_REASON_CHARS = 1000
MIN_REASON_CHARS = 5
MAX_PROPOSER_CHARS = 80
ANONYMOUS = "anonymous"


class ProposalError(ValueError):
    """User-facing validation error for deletion proposals."""


@dataclass
class ProposalResult:
    proposal_id: str
    pattern_id: str
    saved_to: Path


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_proposal_id(now: datetime) -> str:
    return (
        "del_" + now.strftime("%Y%m%d_%H%M%S") + "_"
        + secrets.token_hex(2)
    )


def _validate(proposer: str, reason: str) -> tuple[str, str]:
    proposer = (proposer or "").strip() or ANONYMOUS
    reason = (reason or "").strip()
    if len(proposer) > MAX_PROPOSER_CHARS:
        raise ProposalError(
            f"proposer field too long ({len(proposer)} > "
            f"{MAX_PROPOSER_CHARS})"
        )
    if not reason or len(reason) < MIN_REASON_CHARS:
        raise ProposalError(
            f"reason must be at least {MIN_REASON_CHARS} characters"
        )
    if len(reason) > MAX_REASON_CHARS:
        raise ProposalError(
            f"reason too long ({len(reason)} > {MAX_REASON_CHARS})"
        )
    return proposer, reason


_FILE_LOCK = Lock()


class DeletionManager:
    """Mutating writer for deletion proposals.

    Single-process safe via threading.Lock; multi-process-safe enough
    for the local-first PoC since file writes are atomic via
    temp+rename. Multi-host concurrent edits are not supported in
    Phase 1."""

    def __init__(
        self,
        config_dir: Path = DEFAULT_CONFIG_DIR,
        audit_path: Path = DEFAULT_AUDIT_PATH,
    ) -> None:
        self.config_dir = Path(config_dir)
        self.audit_path = Path(audit_path)

    # ─────────────────────────────────────────────────────────────────

    def propose(
        self, pattern_id: str, proposer: str, reason: str,
        *, when: Optional[datetime] = None,
    ) -> ProposalResult:
        proposer, reason = _validate(proposer, reason)
        now = when or _now()

        with _FILE_LOCK:
            source_path = self._find_source(pattern_id)
            if source_path is None:
                raise ProposalError(
                    f"pattern not found: {pattern_id}"
                )
            patterns = self._load_jsonl(source_path)
            target_idx = next(
                (i for i, p in enumerate(patterns) if p.id == pattern_id),
                None,
            )
            if target_idx is None:
                raise ProposalError(
                    f"pattern disappeared during write: {pattern_id}"
                )
            patt = patterns[target_idx]
            proposal = DeletionProposal(
                proposal_id=_gen_proposal_id(now),
                proposer=proposer, date=now,
                reason=reason, status="pending",
            )
            event = LifecycleEvent(
                timestamp=now, event="deletion_proposed",
                actor=f"user_{proposer}" if proposer != ANONYMOUS else "anonymous",
                detail=f"proposal_id={proposal.proposal_id} reason={reason[:80]}",
            )
            patt.lifecycle.deletion_proposals.append(proposal)
            patt.lifecycle.audit_status = "user_deletion_proposed"
            patt.lifecycle.history.append(event)
            patterns[target_idx] = patt
            self._atomic_rewrite(source_path, patterns)
            self._append_audit_log(proposal, pattern_id, now, source_path)

        return ProposalResult(
            proposal_id=proposal.proposal_id,
            pattern_id=pattern_id, saved_to=source_path,
        )

    # ─────────────────────────────────────────────────────────────────
    # IO
    # ─────────────────────────────────────────────────────────────────

    def _find_source(self, pattern_id: str) -> Optional[Path]:
        for jsonl in sorted(self.config_dir.glob("*.jsonl")):
            if jsonl.name.startswith("_"):
                continue
            for line in jsonl.open("r", encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if raw.get("id") == pattern_id:
                    return jsonl
        return None

    def _load_jsonl(self, path: Path) -> list[Pattern]:
        out: list[Pattern] = []
        for line in path.open("r", encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            try:
                out.append(Pattern.model_validate(raw))
            except Exception as e:
                raise ProposalError(
                    f"existing pattern {raw.get('id', '?')} fails schema: {e}"
                )
        return out

    def _atomic_rewrite(self, path: Path, patterns: list[Pattern]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for p in patterns:
                fh.write(
                    p.model_dump_json(exclude_none=False) + "\n"
                )
        os.replace(tmp, path)

    def _append_audit_log(
        self, proposal: DeletionProposal, pattern_id: str,
        now: datetime, source_path: Path,
    ) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "proposal_id": proposal.proposal_id,
            "pattern_id": pattern_id,
            "proposer": proposal.proposer,
            "reason": proposal.reason,
            "source": source_path.name,
        }
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
