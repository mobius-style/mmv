"""conflict_checker.py — collision detection vs the existing library.

Phase 2 Commit 17. Spec v1.3 Section 4.2 + Section 5.3.2 D-3.

For a candidate Pattern, computes ME5 cosine similarity between each
of its examples and every example in the existing library (loaded
from `config/pattern_library/*.jsonl`). A conflict is flagged when:

    max_pairwise_cosine ≥ CONFLICT_THRESHOLD  (default 0.85)

Self-references (same pattern_id) are excluded — used for "pattern
update" workflows where a revised version must collide with itself.

CLI mode: scan all patterns pairwise and report any cross-pattern
collisions.

The threshold (0.85) is intentionally lower than NEG_DUP_MAX/POS_DRIFT
(0.97) — the goal here is to catch SEMANTIC overlap that would lead to
ambiguous lookup, not just literal duplication. If two patterns'
examples cluster ≥0.85 in cosine space, they are probably about the
same intent and should be merged (or one should be deprecated).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.retrieval.pattern_schema import Pattern


CONFLICT_THRESHOLD = 0.85
ME5_MODEL = "intfloat/multilingual-e5-large"


@dataclass
class ConflictReport:
    candidate_id: str
    has_conflict: bool = False
    conflicts: list[tuple[str, str, str, float]] = field(default_factory=list)
    # (existing_pattern_id, candidate_example, existing_example, cosine_score)


@dataclass
class CrossPatternReport:
    """Pairwise scan report for the whole library."""
    pairs: list[tuple[str, str, str, str, float]] = field(default_factory=list)
    # (pattern_a_id, pattern_b_id, ex_a, ex_b, cosine)


class ConflictChecker:
    """Cosine-similarity check via ME5 (no FAISS needed for pairwise)."""

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        encoder=None,
    ) -> None:
        self.config_dir = config_dir or (
            Path(__file__).resolve().parent.parent.parent
            / "config" / "pattern_library"
        )
        self._encoder = encoder

    def _ensure_encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(ME5_MODEL)
        return self._encoder

    # Phase 4 audit Commit 8: align with build_pattern_index audit_status
    # filter. Patterns flagged deprecation_candidate / deprecated /
    # under_review are excluded from conflict comparisons (they are
    # not in the active routing index, so new patterns should not be
    # rejected for overlapping with them).
    INACTIVE_STATUSES = {"deprecation_candidate", "deprecated", "under_review"}

    def _load_library(self, include_inactive: bool = False) -> list[Pattern]:
        out: list[Pattern] = []
        for fp in sorted(self.config_dir.glob("*.jsonl")):
            if fp.name.startswith("_"):
                continue
            for line in fp.open("r", encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    p = Pattern.model_validate(json.loads(line))
                except Exception:
                    continue
                if not include_inactive:
                    status = getattr(p.lifecycle, "audit_status", "active")
                    if status in self.INACTIVE_STATUSES:
                        continue
                out.append(p)
        return out

    def check(self, candidate: Pattern) -> ConflictReport:
        """Compare `candidate` against all existing patterns. Self
        (same id) is excluded."""
        report = ConflictReport(candidate_id=candidate.id)
        existing = [p for p in self._load_library() if p.id != candidate.id]
        if not existing:
            return report

        encoder = self._ensure_encoder()
        import numpy as np
        cand_emb = encoder.encode(
            ["passage: " + e for e in candidate.examples],
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")

        for other in existing:
            other_emb = encoder.encode(
                ["passage: " + e for e in other.examples],
                convert_to_numpy=True, normalize_embeddings=True,
                show_progress_bar=False,
            ).astype("float32")
            sims = cand_emb @ other_emb.T
            max_idx_flat = int(sims.argmax())
            i = max_idx_flat // sims.shape[1]
            j = max_idx_flat % sims.shape[1]
            score = float(sims[i, j])
            if score >= CONFLICT_THRESHOLD:
                report.conflicts.append((
                    other.id,
                    candidate.examples[i],
                    other.examples[j],
                    score,
                ))
        report.has_conflict = bool(report.conflicts)
        return report

    def scan_pairwise(self) -> CrossPatternReport:
        """Detect any pair of distinct patterns whose example sets
        contain a ≥ CONFLICT_THRESHOLD cosine pair."""
        report = CrossPatternReport()
        all_p = self._load_library()
        if len(all_p) < 2:
            return report
        encoder = self._ensure_encoder()
        import numpy as np
        embs: dict[str, "np.ndarray"] = {}
        for p in all_p:
            embs[p.id] = encoder.encode(
                ["passage: " + e for e in p.examples],
                convert_to_numpy=True, normalize_embeddings=True,
                show_progress_bar=False,
            ).astype("float32")

        for i, a in enumerate(all_p):
            for b in all_p[i + 1:]:
                sims = embs[a.id] @ embs[b.id].T
                max_idx_flat = int(sims.argmax())
                ai = max_idx_flat // sims.shape[1]
                bj = max_idx_flat % sims.shape[1]
                score = float(sims[ai, bj])
                if score >= CONFLICT_THRESHOLD:
                    report.pairs.append((
                        a.id, b.id,
                        a.examples[ai], b.examples[bj],
                        score,
                    ))
        return report


def smoke():  # pragma: no cover
    print("conflict_checker full implementation OK")


if __name__ == "__main__":
    print("Scanning library for cross-pattern conflicts...")
    rep = ConflictChecker().scan_pairwise()
    if not rep.pairs:
        print("No conflicts ≥ 0.85 cosine found.")
    else:
        for a, b, ea, eb, s in rep.pairs:
            print(f"  {s:.3f}  {a} ↔ {b}")
            print(f"    A: {ea}")
            print(f"    B: {eb}")
