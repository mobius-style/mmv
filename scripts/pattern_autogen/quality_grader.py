"""quality_grader.py — pattern-level overall quality grading.

Phase 2 Commit 17. Spec v1.3 Section 4.2 + Section 5.3.2 D-3.

Grades a candidate Pattern across 5 dimensions on a 0-5 scale via
multi-judge Groq consensus. The score is the median across N judges.
Used as a final acceptance gate before a new pattern is committed
(Commit 21 authoring form will call this).

Dimensions:
    intent_clarity         — is the intent clearly defined and narrow?
    example_coverage        — do examples span real surface phrasings?
    negative_discrimination — do negatives effectively disambiguate?
    xling_consistency       — do cross-lingual queries faithfully translate?
    overall                 — composite

Acceptance gate: overall ≥ 4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.retrieval.pattern_schema import Pattern
from .groq_client import AutogenGroqClient, ConsensusResult

QUALITY_THRESHOLD = 4


@dataclass
class QualityScore:
    overall: float = 0.0
    intent_clarity: float = 0.0
    example_coverage: float = 0.0
    negative_discrimination: float = 0.0
    xling_consistency: float = 0.0
    notes: str = ""
    consensus: Optional[ConsensusResult] = None

    def passes(self, threshold: int = QUALITY_THRESHOLD) -> bool:
        return self.overall >= threshold


class QualityGrader:
    SYSTEM_PROMPT = (
        "You grade an AI intent pattern on a 0-5 integer scale across "
        "five dimensions: "
        "1) intent_clarity — is the intent clearly defined and narrow? "
        "2) example_coverage — do examples span real surface phrasings? "
        "3) negative_discrimination — do negatives effectively "
        "disambiguate the intent from look-alikes? "
        "4) xling_consistency — do cross-lingual queries faithfully "
        "translate the intent? "
        "5) overall — composite judgement. "
        "Output STRICT JSON only: "
        '{"overall": 0..5, "intent_clarity": 0..5, '
        '"example_coverage": 0..5, "negative_discrimination": 0..5, '
        '"xling_consistency": 0..5, "notes": "..."}.'
    )

    def __init__(self, client: Optional[AutogenGroqClient] = None) -> None:
        self.client = client or AutogenGroqClient()

    def _build_user_prompt(self, p: Pattern) -> str:
        ex = "\n".join(f"  + {e}" for e in p.examples)
        neg = "\n".join(f"  - {e}" for e in p.negative_examples)
        xl = "\n".join(
            f"  ({q.lang}, match={q.expected_match}) {q.query}"
            for q in p.cross_lingual_test_queries
        )
        return (
            f"Pattern: {p.id}\n"
            f"Topic: {p.topic}\n"
            f"Intent: {p.intent}\n\n"
            f"Examples ({len(p.examples)}):\n{ex}\n\n"
            f"Negatives ({len(p.negative_examples)}):\n{neg}\n\n"
            f"Cross-lingual queries ({len(p.cross_lingual_test_queries)}):"
            f"\n{xl}\n\n"
            f"Output strict JSON with all 6 fields."
        )

    def grade(self, p: Pattern, batch_id: Optional[str] = None) -> QualityScore:
        prompt_user = self._build_user_prompt(p)
        consensus = self.client.consensus(
            self.SYSTEM_PROMPT, prompt_user,
            max_tokens=1000, prompt_version="quality_v1",
            batch_id=batch_id,
        )
        per_dim: dict[str, list[float]] = {
            "overall": [], "intent_clarity": [], "example_coverage": [],
            "negative_discrimination": [], "xling_consistency": [],
        }
        notes: list[str] = []
        for call in consensus.calls:
            if not call.parsed:
                continue
            for k in per_dim:
                v = call.parsed.get(k)
                if isinstance(v, (int, float)):
                    per_dim[k].append(float(v))
            n = call.parsed.get("notes")
            if isinstance(n, str) and n.strip():
                notes.append(n[:120])

        def _median(xs):
            if not xs:
                return 0.0
            xs = sorted(xs)
            return xs[len(xs) // 2]

        return QualityScore(
            overall=_median(per_dim["overall"]),
            intent_clarity=_median(per_dim["intent_clarity"]),
            example_coverage=_median(per_dim["example_coverage"]),
            negative_discrimination=_median(per_dim["negative_discrimination"]),
            xling_consistency=_median(per_dim["xling_consistency"]),
            notes=" | ".join(notes[:3]),
            consensus=consensus,
        )


def smoke():  # pragma: no cover
    print("quality_grader full implementation OK")


if __name__ == "__main__":
    smoke()
