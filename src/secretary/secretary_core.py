"""Secretary core — proposal-only auto-improvement loop.

Phase 3 Commit 36 (skeleton). Phase 3 Commit 37 wires the actual
trigger conditions and proposal generators on top of this skeleton.

Spec ref: docs/PATTERN_LIBRARY_SPEC_v1_4.md §4.3 (three-stage
automation amplification, stage 4) + §5.4.4 (Secretary Phase 3
proposal-only scope).

HARD CONSTRAINT 7 (Phase 3 prompt): the Secretary MUST NOT mutate
`config/pattern_library/*`. Tests in tests/secretary/ verify that
the library directory is unchanged after Secretary observes,
generates, and persists proposals.
"""
from __future__ import annotations

import json
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Optional


ProposalKind = Literal[
    "deprecate_pattern",
    "expand_examples",
    "add_negative_examples",
    "rebalance_threshold",
    "lower_priority",
]

ProposalStatus = Literal["pending", "approved", "rejected", "applied"]


@dataclass
class Proposal:
    """A Secretary proposal: a request to modify the library that
    requires T approval before any change is applied."""

    proposal_id: str
    kind: ProposalKind
    target_pattern_id: Optional[str]
    target_topic: Optional[str]
    rationale: str
    evidence: dict[str, Any]
    suggested_change: dict[str, Any]
    created_at: str
    status: ProposalStatus = "pending"
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    decision_note: Optional[str] = None

    @staticmethod
    def make(
        kind: ProposalKind,
        rationale: str,
        evidence: dict[str, Any] | None = None,
        suggested_change: dict[str, Any] | None = None,
        target_pattern_id: Optional[str] = None,
        target_topic: Optional[str] = None,
    ) -> "Proposal":
        now = datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z",
        )
        pid = "prop_" + now[:10].replace("-", "") + "_" + secrets.token_hex(3)
        return Proposal(
            proposal_id=pid, kind=kind,
            target_pattern_id=target_pattern_id,
            target_topic=target_topic,
            rationale=rationale,
            evidence=evidence or {},
            suggested_change=suggested_change or {},
            created_at=now,
        )

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class ProposalStore:
    """Persistent JSONL-backed proposal store. All Secretary writes
    land here, NOT in the library config dir."""

    proposals_path: Path
    _lock: threading.Lock = field(default_factory=threading.Lock,
                                    repr=False, compare=False)

    def append(self, proposal: Proposal) -> None:
        with self._lock:
            self.proposals_path.parent.mkdir(parents=True, exist_ok=True)
            with self.proposals_path.open("a", encoding="utf-8") as fh:
                fh.write(proposal.to_jsonl() + "\n")

    def list_all(self) -> list[Proposal]:
        if not self.proposals_path.exists():
            return []
        with self._lock:
            out: list[Proposal] = []
            for line in self.proposals_path.read_text(
                encoding="utf-8",
            ).splitlines():
                if line.strip():
                    out.append(Proposal(**json.loads(line)))
            return out

    def list_pending(self) -> list[Proposal]:
        return [p for p in self.list_all() if p.status == "pending"]

    def update_status(
        self, proposal_id: str, status: ProposalStatus,
        decided_by: str = "human:taiko",
        decision_note: Optional[str] = None,
    ) -> Optional[Proposal]:
        with self._lock:
            if not self.proposals_path.exists():
                return None
            entries = []
            updated: Optional[Proposal] = None
            for line in self.proposals_path.read_text(
                encoding="utf-8",
            ).splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj["proposal_id"] == proposal_id:
                    obj["status"] = status
                    obj["decided_at"] = datetime.now(
                        timezone.utc,
                    ).isoformat().replace("+00:00", "Z")
                    obj["decided_by"] = decided_by
                    obj["decision_note"] = decision_note
                    updated = Proposal(**obj)
                entries.append(obj)
            with self.proposals_path.open("w", encoding="utf-8") as fh:
                for obj in entries:
                    fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            return updated


@dataclass
class Secretary:
    """Proposal-only auto-improvement loop entry point.

    Phase 3 scope: collect signals from the audit / hit-count /
    user proposal sources and emit Proposals to the ProposalStore.
    NEVER mutates library JSONLs (HARD CONSTRAINT 7).
    """

    proposal_store: ProposalStore
    library_path: Path  # read-only reference

    def observe_audit(
        self, audit: dict, *, max_proposals: int = 20,
    ) -> list[Proposal]:
        """Trigger 1 (deprecation candidates) + Trigger 2 (xling
        floor violations). Audit dict shape per
        scripts/audit_pattern_library.py compute_audit() output.

        Caps at ``max_proposals`` to avoid flood. Each generated
        proposal is appended to the ProposalStore."""
        out: list[Proposal] = []
        if not isinstance(audit, dict):
            return out

        # Trigger 1: deprecation candidate → propose deprecate_pattern
        for c in audit.get("deprecation_candidates", [])[:max_proposals]:
            if not c.get("id"):
                continue
            prop = Proposal.make(
                kind="deprecate_pattern",
                target_pattern_id=c["id"],
                target_topic=c.get("topic"),
                rationale=(
                    f"Audit flagged: {c.get('reason', 'no_hits_after_threshold')}"
                    f" (age_days={c.get('age_days')})"
                ),
                evidence={
                    "trigger": "audit.deprecation_candidate",
                    "age_days": c.get("age_days"),
                    "intent": c.get("intent"),
                },
                suggested_change={
                    "set_audit_status": "deprecation_candidate",
                },
            )
            self.proposal_store.append(prop)
            out.append(prop)
            if len(out) >= max_proposals:
                return out

        # Trigger 2: xling floor violation → propose expand_examples
        for v in audit.get("xling_floor_violations", []):
            if len(out) >= max_proposals:
                break
            if not v.get("id"):
                continue
            prop = Proposal.make(
                kind="expand_examples",
                target_pattern_id=v["id"],
                target_topic=v.get("topic"),
                rationale=(
                    f"Cross-lingual pass rate "
                    f"{v.get('xling_pass_rate', 0):.2f} below floor"
                ),
                evidence={
                    "trigger": "audit.xling_floor_violation",
                    "xling_pass_rate": v.get("xling_pass_rate"),
                },
                suggested_change={
                    "add_examples_lang": ["ja", "zh"],
                    "min_examples_to_add": 4,
                },
            )
            self.proposal_store.append(prop)
            out.append(prop)
        return out

    def observe_hit_counts(
        self, snapshot: dict[str, int], *,
        anomaly_floor: int = 100,
        cold_threshold: int = 0,
        max_proposals: int = 20,
    ) -> list[Proposal]:
        """Trigger 3 (hot pattern saturation) + Trigger 4 (cold
        pattern accumulation).

        - Hot saturation: a single pattern accumulating > anomaly_floor
          hits suggests routing concentration; propose lower_priority
          and/or add_negative_examples to reduce false-positive load.
        - Cold accumulation: many patterns with hit_count==0 over the
          observation window — surfaces deprecation review need.
        """
        out: list[Proposal] = []
        if not isinstance(snapshot, dict):
            return out

        # Trigger 3: hot saturation
        for pid, hits in snapshot.items():
            if len(out) >= max_proposals:
                return out
            if hits > anomaly_floor:
                prop = Proposal.make(
                    kind="lower_priority",
                    target_pattern_id=pid,
                    rationale=(
                        f"High-volume pattern: {hits} hits since last "
                        f"reset; potential over-fire"
                    ),
                    evidence={
                        "trigger": "hit_count.saturation",
                        "hits": hits,
                        "anomaly_floor": anomaly_floor,
                    },
                    suggested_change={
                        "decrease_priority_by": 10,
                    },
                )
                self.proposal_store.append(prop)
                out.append(prop)

        # Trigger 4: cold accumulation (only if substantial cold set)
        cold_pids = [pid for pid, hits in snapshot.items()
                     if hits <= cold_threshold]
        if len(cold_pids) >= 5 and len(out) < max_proposals:
            prop = Proposal.make(
                kind="deprecate_pattern",
                target_pattern_id=None,
                rationale=(
                    f"{len(cold_pids)} patterns with 0 hits — review "
                    f"audit script output for deprecation candidates"
                ),
                evidence={
                    "trigger": "hit_count.cold_accumulation",
                    "cold_pattern_count": len(cold_pids),
                    "sample_ids": cold_pids[:10],
                },
                suggested_change={
                    "review_for_deprecation": True,
                },
            )
            self.proposal_store.append(prop)
            out.append(prop)
        return out

    def observe_threshold_drift(
        self, golden_per_topic: dict[str, float], *,
        target_min: float = 0.85,
    ) -> list[Proposal]:
        """Trigger 5: per-topic golden accuracy below the spec gate
        suggests threshold tuning is overdue. golden_per_topic maps
        topic -> accuracy in [0,1]."""
        out: list[Proposal] = []
        if not isinstance(golden_per_topic, dict):
            return out
        for topic, acc in golden_per_topic.items():
            if acc < target_min:
                prop = Proposal.make(
                    kind="rebalance_threshold",
                    target_topic=topic,
                    rationale=(
                        f"{topic} golden accuracy {acc:.3f} below "
                        f"{target_min:.2f} gate"
                    ),
                    evidence={
                        "trigger": "golden.threshold_drift",
                        "topic": topic,
                        "accuracy": acc,
                        "target": target_min,
                    },
                    suggested_change={
                        "tune_high_threshold_range": [0.80, 0.90],
                        "rerun_sweep": True,
                    },
                )
                self.proposal_store.append(prop)
                out.append(prop)
        return out

    def emit_user_proposal(
        self, kind: ProposalKind, rationale: str,
        suggested_change: dict[str, Any] | None = None,
        target_pattern_id: Optional[str] = None,
        target_topic: Optional[str] = None,
        evidence: dict[str, Any] | None = None,
    ) -> Proposal:
        """User-initiated proposal path (e.g. from Library Inspector
        UI). Returns the persisted proposal for echo."""
        prop = Proposal.make(
            kind=kind, rationale=rationale,
            evidence=evidence or {"source": "user"},
            suggested_change=suggested_change or {},
            target_pattern_id=target_pattern_id,
            target_topic=target_topic,
        )
        self.proposal_store.append(prop)
        return prop


def secretary_will_not_mutate_library(library_path: Path) -> dict[str, Any]:
    """Diagnostic helper used by tests. Returns a fingerprint of the
    library directory contents so tests can verify that Secretary
    operations leave the library unchanged."""
    out: dict[str, Any] = {}
    for jsonl in sorted(library_path.glob("*.jsonl")):
        if jsonl.name.startswith("_"):
            continue
        out[jsonl.name] = jsonl.read_bytes()
    return out
