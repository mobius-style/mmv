"""variants_generator.py — paraphrase expansion of pattern.examples.

Phase 2 Commit 14 implementation.

Flow:
    1. Multi-temperature generation (3 Groq calls @ T=0.3/0.7/1.0)
       → up to 3*per_call_n raw candidate paraphrases
    2. String-level dedup (case-insensitive, whitespace-normalized)
    3. Self-judge grade: a separate Groq call asks the model to score
       each candidate 0-5 on "preserves intent" axis. Threshold 4+
       accepted.
    4. Conflict gate against existing pattern.examples — cosine ≥ 0.95
       on ME5 means the candidate is a near-duplicate of an existing
       example; drop. Reuses scripts/build_pattern_index.py's encoder
       conventions ("passage: " prefix, L2-normalized).
    5. Returns VariantsResult with accepted + rejected (with reasons)
       and the originating ConsensusResult metadata for origin tagging.

Token budget per pattern:
    Stage 1 (generate): 3 calls * ~800 tokens ≈ 2400
    Stage 3 (grade):    1 batched call * ~600 tokens ≈ 600
    Stage 4 (conflict): no Groq cost (local FAISS)
    Total:              ~3000 tokens / pattern.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from src.retrieval.pattern_schema import Pattern
from .groq_client import AutogenGroqClient, ConsensusResult

CONFLICT_COSINE = 0.95
QUALITY_THRESHOLD = 4
ME5_MODEL = "intfloat/multilingual-e5-large"


@dataclass
class VariantsResult:
    pattern_id: str
    accepted: list[str] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)
    consensus: Optional[ConsensusResult] = None
    grader_consensus: Optional[ConsensusResult] = None
    raw_candidate_count: int = 0


class VariantsGenerator:
    GENERATOR_SYSTEM_PROMPT = (
        "You produce paraphrase variants for a single intent. "
        "Each variant must preserve the underlying intent of the input "
        "examples. Variants should differ in surface form (word choice, "
        "syntax, formality) while staying faithful to what the user is "
        "asking. Avoid redundancy — each variant should be substantively "
        "different from the others. "
        "Output STRICT JSON only, no preface or commentary: "
        '{"variants": ["...", "...", ...]}. '
        "If you cannot produce N variants, produce as many as you can."
    )

    GRADER_SYSTEM_PROMPT = (
        "You grade candidate paraphrase variants for an intent on a "
        "0-5 integer scale. 5 = preserves intent perfectly + reads "
        "naturally. 4 = preserves intent with minor naturalness loss. "
        "3 = ambiguous intent or awkward. 2 = different intent or "
        "broken phrasing. 1 = unrelated. 0 = empty/garbage. "
        "Output STRICT JSON only: "
        '{"grades": [{"variant": "...", "score": N, "reason": "..."}, ...]}. '
        "List one entry per input candidate, in the same order."
    )

    def __init__(self, client: Optional[AutogenGroqClient] = None,
                 encoder=None) -> None:
        self.client = client or AutogenGroqClient()
        self._encoder = encoder  # injectable for tests

    def _ensure_encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(ME5_MODEL)
        return self._encoder

    # ─────────────────────────────────────────────────────────────────

    def _build_generator_user_prompt(self, p: Pattern, per_call_n: int) -> str:
        joined = "\n".join(f"- {e}" for e in p.examples[:8])
        return (
            f"Intent: {p.intent}\n"
            f"Topic: {p.topic}\n"
            f"Existing examples:\n{joined}\n\n"
            f"Produce exactly {per_call_n} new paraphrase variants of "
            f"this intent. Do not repeat any of the existing examples "
            f"verbatim. Output strict JSON."
        )

    def _build_grader_user_prompt(
        self, p: Pattern, candidates: list[str],
    ) -> str:
        joined_candidates = "\n".join(
            f"{i+1}. {c}" for i, c in enumerate(candidates)
        )
        joined_examples = "\n".join(f"- {e}" for e in p.examples[:5])
        return (
            f"Intent: {p.intent}\n"
            f"Topic: {p.topic}\n"
            f"Reference examples:\n{joined_examples}\n\n"
            f"Candidate variants to grade (give one entry per "
            f"candidate, in the SAME order):\n{joined_candidates}\n\n"
            f"Output strict JSON with the schema in the system message."
        )

    @staticmethod
    def _normalize(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().lower())

    @staticmethod
    def _dedup(candidates: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for c in candidates:
            key = VariantsGenerator._normalize(c)
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(c.strip())
        return out

    def _generate_raw(
        self, p: Pattern, per_call_n: int, batch_id: Optional[str] = None,
    ) -> tuple[list[str], ConsensusResult]:
        prompt_user = self._build_generator_user_prompt(p, per_call_n)
        consensus = self.client.consensus(
            self.GENERATOR_SYSTEM_PROMPT, prompt_user,
            max_tokens=1200, prompt_version="variants_v1",
            batch_id=batch_id,
        )
        all_variants: list[str] = []
        for call in consensus.calls:
            if not call.parsed:
                continue
            v = call.parsed.get("variants", [])
            if isinstance(v, list):
                for entry in v:
                    if isinstance(entry, str) and entry.strip():
                        all_variants.append(entry)
        return self._dedup(all_variants), consensus

    def _grade(
        self, p: Pattern, candidates: list[str],
        batch_id: Optional[str] = None,
    ) -> tuple[dict[str, int], ConsensusResult]:
        if not candidates:
            return {}, ConsensusResult(
                calls=[], primary_used=True, accepted=False,
                batch_id=batch_id or "skipped",
                groq_run_id="skipped", prompt_version="variants_grade_v1",
                started_at="", finished_at="",
            )
        prompt_user = self._build_grader_user_prompt(p, candidates)
        # 2500 cap to fit ~30 candidates × short JSON entry on a
        # reasoning model that uses budget for thinking + content.
        consensus = self.client.consensus(
            self.GRADER_SYSTEM_PROMPT, prompt_user,
            max_tokens=2500, prompt_version="variants_grade_v1",
            batch_id=batch_id,
        )
        # Aggregate scores. PRIMARY path: index-based — the grader
        # was told to return one entry per candidate IN THE SAME ORDER.
        # FALLBACK: text match (for cases the LLM rephrased the
        # variant slightly).
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

    def _conflict_filter(
        self, p: Pattern, candidates: list[str],
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """Drop candidates that are ≥0.95 cosine to any existing example.
        Returns (kept, rejected_with_reasons)."""
        if not candidates:
            return [], []
        encoder = self._ensure_encoder()
        import numpy as np
        existing = encoder.encode(
            ["passage: " + e for e in p.examples],
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")
        cand_emb = encoder.encode(
            ["passage: " + c for c in candidates],
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")
        # cand_emb @ existing.T : (N_cand, N_existing)
        sims = cand_emb @ existing.T
        max_sims = sims.max(axis=1)
        kept: list[str] = []
        rejected: list[tuple[str, str]] = []
        for i, cand in enumerate(candidates):
            ms = float(max_sims[i])
            if ms >= CONFLICT_COSINE:
                rejected.append(
                    (cand, f"duplicate of existing example (cos={ms:.3f})")
                )
            else:
                kept.append(cand)
        return kept, rejected

    # ─────────────────────────────────────────────────────────────────

    def generate(
        self, p: Pattern, per_call_n: int = 10,
        batch_id: Optional[str] = None,
    ) -> VariantsResult:
        """Generate, grade, and filter variant candidates for `p`.

        Returns up to ~per_call_n*3 accepted variants tagged with
        origin metadata via the ConsensusResult on the result. Caller
        is responsible for appending to the pattern's source JSONL."""
        result = VariantsResult(pattern_id=p.id)

        raw, gen_consensus = self._generate_raw(p, per_call_n, batch_id)
        result.consensus = gen_consensus
        result.raw_candidate_count = len(raw)

        if not raw:
            return result

        # Conflict filter (cheap; do this BEFORE the grader call)
        kept, conflict_rejected = self._conflict_filter(p, raw)
        result.rejected.extend(conflict_rejected)

        if not kept:
            return result

        # Grade
        scores, grader_consensus = self._grade(p, kept, batch_id)
        result.grader_consensus = grader_consensus

        for cand in kept:
            score = scores.get(cand, 0)
            if score >= QUALITY_THRESHOLD:
                result.accepted.append(cand)
            else:
                result.rejected.append(
                    (cand, f"quality grade {score} < {QUALITY_THRESHOLD}")
                )

        return result


def smoke():  # pragma: no cover
    print("variants_generator full implementation OK")


if __name__ == "__main__":
    smoke()
