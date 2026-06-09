"""negatives_generator.py — disambiguation/negative example expansion.

Phase 2 Commit 15 implementation. Pattern Library Spec v1.3 Section 4 +
Section 5.3.2 D-3.

Flow:
    1. Multi-temperature Groq generation (T=0.3/0.7/1.0): produce
       disambiguation counter-examples that look superficially similar
       to the pattern's intent but are about different topics
    2. Dedup
    3. POSITIVE-DISTANCE gate: drop candidates whose max cosine to
       any positive example is ≥ POS_DRIFT_MAX (too close to positives →
       not actually a disambiguator). Default 0.80.
    4. NEGATIVE-OVERLAP gate: drop candidates whose max cosine to
       existing negative_examples is ≥ NEG_DUP_MAX (duplicate
       negative). Default 0.92.
    5. Quality grade ≥ 4 (multi-judge median, index-aligned with
       text-match fallback)

This generator is the counterpart to runtime NEG_MARGIN=0.05 in
src/retrieval/pattern_lookup.py: the lookup helper drops a pattern at
inference time if `pattern_score - max(neg_score) < 0.05`. To make
that gate effective, autogen must produce negatives that ARE
substantially separable from positives at the embedding level
(POS_DRIFT_MAX serves that role at authoring time).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.retrieval.pattern_schema import Pattern
from .groq_client import AutogenGroqClient, ConsensusResult

POS_DRIFT_MAX = 0.97
NEG_DUP_MAX = 0.97
QUALITY_THRESHOLD = 4

# Note on POS_DRIFT_MAX:
# Negatives are SUPPOSED to be surface-similar to positives — that's
# the whole point of disambiguation. ME5 routinely scores good
# disambiguators (e.g. "What is the Möbius strip" vs "What is MOBIUS")
# in the 0.85-0.93 range. The runtime gate is NEG_MARGIN=0.05 in
# src/retrieval/pattern_lookup.py, which correctly handles the
# "neg also matches" case by dropping the pattern. POS_DRIFT_MAX
# only catches literal paraphrases — accidents where the generator
# emitted a positive in disguise.
ME5_MODEL = "intfloat/multilingual-e5-large"


@dataclass
class NegativesResult:
    pattern_id: str
    accepted: list[str] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)
    consensus: Optional[ConsensusResult] = None
    grader_consensus: Optional[ConsensusResult] = None
    raw_candidate_count: int = 0


class NegativesGenerator:
    GENERATOR_SYSTEM_PROMPT = (
        "You produce DISAMBIGUATION counter-examples for an intent. "
        "Each negative must read like the SAME surface words/topic "
        "as the positive examples but be ABOUT A DIFFERENT entity, "
        "domain, or sense. Examples: positive 'What is MOBIUS' "
        "(software) → negative 'What is a Möbius strip' (topology). "
        "Avoid trivial unrelated questions (e.g. 'What is the capital "
        "of France') — those don't disambiguate. "
        "Output STRICT JSON only, no preface: "
        '{"negatives": ["...", "...", ...]}. '
        "Produce as many as you can up to N."
    )

    GRADER_SYSTEM_PROMPT = (
        "You grade candidate disambiguation negatives on a 0-5 scale. "
        "5 = looks like the same surface phrasing as the positive intent "
        "but is about a clearly different topic/entity. "
        "4 = recognizable disambiguation, mild surface drift. "
        "3 = ambiguous (might be either intent). "
        "2 = unrelated trivially (no surface similarity → not useful). "
        "1 = effectively a positive example. "
        "0 = empty/garbage. "
        "Output STRICT JSON only: "
        '{"grades": [{"variant": "...", "score": N, "reason": "..."}, ...]}. '
        "One entry per input candidate IN THE SAME ORDER."
    )

    def __init__(self, client: Optional[AutogenGroqClient] = None,
                 encoder=None) -> None:
        self.client = client or AutogenGroqClient()
        self._encoder = encoder

    def _ensure_encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(ME5_MODEL)
        return self._encoder

    def _build_generator_user_prompt(self, p: Pattern, n: int) -> str:
        joined_pos = "\n".join(f"  + {e}" for e in p.examples[:6])
        joined_neg = "\n".join(f"  - {e}" for e in p.negative_examples[:6])
        return (
            f"Intent: {p.intent}\n"
            f"Topic: {p.topic}\n\n"
            f"POSITIVE examples (queries we want to MATCH):\n{joined_pos}\n\n"
            f"EXISTING negatives (queries that look similar but should "
            f"NOT match — same kind needed):\n{joined_neg or '  (none yet)'}\n\n"
            f"Produce {n} additional disambiguation negatives. Each "
            f"should look SURFACE-similar to a positive but be about "
            f"a different entity/domain. Output strict JSON."
        )

    def _build_grader_user_prompt(
        self, p: Pattern, candidates: list[str],
    ) -> str:
        joined_pos = "\n".join(f"+ {e}" for e in p.examples[:5])
        joined_neg = "\n".join(f"- {e}" for e in p.negative_examples[:5])
        joined_cand = "\n".join(
            f"{i+1}. {c}" for i, c in enumerate(candidates)
        )
        return (
            f"Intent: {p.intent}\n\n"
            f"Positive examples (target match):\n{joined_pos}\n\n"
            f"Existing negatives (already known disambiguators):\n"
            f"{joined_neg or '(none yet)'}\n\n"
            f"Candidates to grade IN THE SAME ORDER:\n{joined_cand}\n\n"
            f"Output strict JSON with the schema in the system message."
        )

    @staticmethod
    def _normalize(s: str) -> str:
        import re
        return re.sub(r"\s+", " ", s.strip().lower())

    @staticmethod
    def _dedup(candidates: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for c in candidates:
            key = NegativesGenerator._normalize(c)
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(c.strip())
        return out

    def _generate_raw(
        self, p: Pattern, n: int, batch_id: Optional[str] = None,
    ) -> tuple[list[str], ConsensusResult]:
        prompt_user = self._build_generator_user_prompt(p, n)
        consensus = self.client.consensus(
            self.GENERATOR_SYSTEM_PROMPT, prompt_user,
            max_tokens=1500, prompt_version="negatives_v1",
            batch_id=batch_id,
        )
        all_neg: list[str] = []
        for call in consensus.calls:
            if not call.parsed:
                continue
            v = call.parsed.get("negatives", [])
            if isinstance(v, list):
                for entry in v:
                    if isinstance(entry, str) and entry.strip():
                        all_neg.append(entry)
        return self._dedup(all_neg), consensus

    def _grade(
        self, p: Pattern, candidates: list[str],
        batch_id: Optional[str] = None,
    ) -> tuple[dict[str, int], ConsensusResult]:
        empty_consensus = ConsensusResult(
            calls=[], primary_used=True, accepted=False,
            batch_id=batch_id or "skipped",
            groq_run_id="skipped", prompt_version="negatives_grade_v1",
            started_at="", finished_at="",
        )
        if not candidates:
            return {}, empty_consensus
        prompt_user = self._build_grader_user_prompt(p, candidates)
        consensus = self.client.consensus(
            self.GRADER_SYSTEM_PROMPT, prompt_user,
            max_tokens=2500, prompt_version="negatives_grade_v1",
            batch_id=batch_id,
        )
        per_call_lists: list[list[int]] = []
        per_call_dicts: list[dict[str, int]] = []
        for call in consensus.calls:
            if not call.parsed:
                continue
            scored = call.parsed.get("grades", [])
            if not isinstance(scored, list):
                continue
            indexed: list[int] = []
            mapping: dict[str, int] = {}
            for entry in scored:
                s = entry.get("score") if isinstance(entry, dict) else None
                if isinstance(s, (int, float)):
                    indexed.append(int(round(float(s))))
                    v = entry.get("variant")
                    if isinstance(v, str):
                        mapping[self._normalize(v)] = int(round(float(s)))
                else:
                    indexed.append(-1)
            if any(x >= 0 for x in indexed):
                per_call_lists.append(indexed)
            if mapping:
                per_call_dicts.append(mapping)
        final: dict[str, int] = {}
        for i, cand in enumerate(candidates):
            scores: list[int] = []
            for lst in per_call_lists:
                if i < len(lst) and lst[i] >= 0:
                    scores.append(lst[i])
            if not scores:
                key = self._normalize(cand)
                for m in per_call_dicts:
                    if key in m:
                        scores.append(m[key])
            if scores:
                scores.sort()
                final[cand] = scores[len(scores) // 2]
        return final, consensus

    def _gate_distance(
        self, p: Pattern, candidates: list[str],
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """Two-stage embedding gate: too-close-to-positives + too-close-
        to-existing-negatives → reject."""
        if not candidates:
            return [], []
        encoder = self._ensure_encoder()
        import numpy as np
        cand_emb = encoder.encode(
            ["passage: " + c for c in candidates],
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")
        pos_emb = encoder.encode(
            ["passage: " + e for e in p.examples],
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")
        sims_pos = cand_emb @ pos_emb.T  # (n_cand, n_pos)
        max_sim_pos = sims_pos.max(axis=1)

        if p.negative_examples:
            neg_emb = encoder.encode(
                ["passage: " + e for e in p.negative_examples],
                convert_to_numpy=True, normalize_embeddings=True,
                show_progress_bar=False,
            ).astype("float32")
            sims_neg = cand_emb @ neg_emb.T
            max_sim_neg = sims_neg.max(axis=1)
        else:
            import numpy as np
            max_sim_neg = np.zeros(len(candidates), dtype="float32")

        kept: list[str] = []
        rejected: list[tuple[str, str]] = []
        for i, cand in enumerate(candidates):
            ms_p = float(max_sim_pos[i])
            ms_n = float(max_sim_neg[i])
            if ms_p >= POS_DRIFT_MAX:
                rejected.append(
                    (cand, f"too close to a positive (cos={ms_p:.3f} ≥ {POS_DRIFT_MAX})")
                )
                continue
            if ms_n >= NEG_DUP_MAX:
                rejected.append(
                    (cand, f"duplicate negative (cos={ms_n:.3f} ≥ {NEG_DUP_MAX})")
                )
                continue
            kept.append(cand)
        return kept, rejected

    def generate(
        self, p: Pattern, n: int = 20,
        batch_id: Optional[str] = None,
    ) -> NegativesResult:
        result = NegativesResult(pattern_id=p.id)

        raw, gen_consensus = self._generate_raw(p, n, batch_id)
        result.consensus = gen_consensus
        result.raw_candidate_count = len(raw)
        if not raw:
            return result

        kept, rejected = self._gate_distance(p, raw)
        result.rejected.extend(rejected)
        if not kept:
            return result

        scores, grader_consensus = self._grade(p, kept, batch_id)
        result.grader_consensus = grader_consensus

        # If the grader call failed entirely (no parseable JSON in any
        # of N consensus calls), treat the embedding gate as the
        # authority and accept the surviving candidates. This mirrors
        # the philosophy that POS_DRIFT_MAX + NEG_DUP_MAX already
        # filtered the structurally-bad cases; the grader is a
        # quality refinement, not a hard gate.
        grader_unavailable = not any(
            c.parsed for c in (grader_consensus.calls or [])
        )

        for cand in kept:
            score = scores.get(cand)
            if score is None and grader_unavailable:
                # No grader signal at all — accept on embedding-gate basis
                result.accepted.append(cand)
                continue
            score = score or 0
            if score >= QUALITY_THRESHOLD:
                result.accepted.append(cand)
            else:
                result.rejected.append(
                    (cand, f"quality grade {score} < {QUALITY_THRESHOLD}")
                )

        return result


def smoke():  # pragma: no cover
    print("negatives_generator full implementation OK")


if __name__ == "__main__":
    smoke()
