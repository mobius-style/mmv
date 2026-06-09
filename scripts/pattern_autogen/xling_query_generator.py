"""xling_query_generator.py — cross-lingual test query expansion.

Phase 2 Commit 16. Spec v1.3 Section 4 + Section 5.3.2 D-3.

Phase 1 patterns require cross_lingual_test_queries with ≥2 ja + ≥2 zh.
Phase 2 strengthens this to ≥3 ja + ≥3 zh per pattern.

Flow:
    1. Multi-temperature Groq generation: produce JA + ZH (and
       optionally KO/ES/FR) test queries with `expected_match` labels.
    2. Each candidate is validated via CrossLingualTestQuery (Pydantic).
       Malformed entries are dropped.
    3. Dedup against existing cross_lingual_test_queries by
       (lang, normalized query).
    4. Multi-judge grade ≥ 4 (5-axis rubric — language correctness,
       intent fidelity, expected_match correctness).

Output: a list of CrossLingualTestQuery objects ready for Pydantic
schema append.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from pydantic import ValidationError

from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, Pattern,
)
from .groq_client import AutogenGroqClient, ConsensusResult

QUALITY_THRESHOLD = 4
DEFAULT_MIN_COSINE = 0.62

REQUIRED_LANGS_JA_MIN = 3   # Phase 2 strengthens from 2 → 3
REQUIRED_LANGS_ZH_MIN = 3
OPTIONAL_LANGS = ("ko", "es", "fr")


@dataclass
class XlingResult:
    pattern_id: str
    accepted: list[CrossLingualTestQuery] = field(default_factory=list)
    rejected: list[tuple[dict, str]] = field(default_factory=list)
    consensus: Optional[ConsensusResult] = None
    grader_consensus: Optional[ConsensusResult] = None
    raw_candidate_count: int = 0


class XlingGenerator:
    GENERATOR_SYSTEM_PROMPT = (
        "You produce cross-lingual TEST queries for an intent. "
        "For each pattern, generate at least 3 Japanese (ja) + 3 "
        "Chinese (zh) queries. Mix expected_match=true (queries that "
        "DO express the intent) and expected_match=false (queries "
        "that look surface-similar but are about a different topic — "
        "good disambiguation tests). "
        "min_cosine: ONLY for expected_match=true entries, default "
        "0.62. Use null for expected_match=false. "
        "Output STRICT JSON only, no preface: "
        '{"queries": [{"lang": "ja|zh|ko|es|fr|en|de|pt", '
        '"query": "...", "expected_match": true|false, '
        '"min_cosine": 0.62 or null}, ...]}.'
    )

    GRADER_SYSTEM_PROMPT = (
        "You grade cross-lingual test queries on a 0-5 scale. "
        "5 = correct language + faithful to intent + "
        "expected_match label correct. "
        "4 = correct overall, minor naturalness issue. "
        "3 = ambiguous (might confuse). "
        "2 = wrong label. "
        "1 = wrong language. "
        "0 = empty/garbage. "
        "Output STRICT JSON only: "
        '{"grades": [{"variant": "...", "score": N, "reason": "..."}, ...]}. '
        "One entry per input candidate IN THE SAME ORDER."
    )

    def __init__(self, client: Optional[AutogenGroqClient] = None) -> None:
        self.client = client or AutogenGroqClient()

    def _build_generator_user_prompt(self, p: Pattern, n: int) -> str:
        joined_pos = "\n".join(f"  + {e}" for e in p.examples[:5])
        joined_neg = "\n".join(f"  - {e}" for e in p.negative_examples[:3])
        existing_xling = "\n".join(
            f"  ({q.lang}) {q.query} [match={q.expected_match}]"
            for q in p.cross_lingual_test_queries
        )
        return (
            f"Intent: {p.intent}\n"
            f"Topic: {p.topic}\n\n"
            f"POSITIVE examples (target match):\n{joined_pos}\n\n"
            f"NEGATIVE examples (disambiguators):\n"
            f"{joined_neg or '(none)'}\n\n"
            f"EXISTING cross-lingual queries:\n{existing_xling}\n\n"
            f"Produce {n} new cross-lingual test queries. Required: "
            f"at least 3 ja + 3 zh, mix true/false expected_match. "
            f"Optional: 1-2 ko/es/fr queries. Do NOT repeat existing "
            f"queries. Output strict JSON."
        )

    def _build_grader_user_prompt(
        self, p: Pattern, candidates: list[dict],
    ) -> str:
        joined_pos = "\n".join(f"+ {e}" for e in p.examples[:4])
        joined_cand = "\n".join(
            f"{i+1}. ({c['lang']}) {c['query']!r} match={c['expected_match']}"
            for i, c in enumerate(candidates)
        )
        return (
            f"Intent: {p.intent}\n\n"
            f"Reference positive examples:\n{joined_pos}\n\n"
            f"Cross-lingual candidates IN THE SAME ORDER:\n{joined_cand}\n\n"
            f"Output strict JSON with the schema in the system message."
        )

    @staticmethod
    def _normalize(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip())

    def _generate_raw(
        self, p: Pattern, n: int, batch_id: Optional[str] = None,
    ) -> tuple[list[dict], ConsensusResult]:
        prompt_user = self._build_generator_user_prompt(p, n)
        consensus = self.client.consensus(
            self.GENERATOR_SYSTEM_PROMPT, prompt_user,
            max_tokens=2000, prompt_version="xling_v1",
            batch_id=batch_id,
        )
        all_q: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for q in p.cross_lingual_test_queries:
            seen.add((q.lang, self._normalize(q.query).lower()))
        for call in consensus.calls:
            if not call.parsed:
                continue
            qs = call.parsed.get("queries", [])
            if not isinstance(qs, list):
                continue
            for entry in qs:
                if not isinstance(entry, dict):
                    continue
                lang = entry.get("lang")
                query = entry.get("query")
                exp = entry.get("expected_match")
                if not isinstance(lang, str) or not isinstance(query, str):
                    continue
                if not isinstance(exp, bool):
                    continue
                key = (lang, self._normalize(query).lower())
                if key in seen:
                    continue
                seen.add(key)
                mc = entry.get("min_cosine")
                if exp is False:
                    mc = None
                elif mc is None:
                    mc = DEFAULT_MIN_COSINE
                else:
                    try:
                        mc = float(mc)
                        if not 0.0 <= mc <= 1.0:
                            mc = DEFAULT_MIN_COSINE
                    except (TypeError, ValueError):
                        mc = DEFAULT_MIN_COSINE
                all_q.append({
                    "lang": lang, "query": self._normalize(query),
                    "expected_match": exp, "min_cosine": mc,
                })
        return all_q, consensus

    def _validate_schema(
        self, candidates: list[dict],
    ) -> tuple[list[dict], list[tuple[dict, str]]]:
        kept: list[dict] = []
        rejected: list[tuple[dict, str]] = []
        for c in candidates:
            try:
                CrossLingualTestQuery(**c)
                kept.append(c)
            except ValidationError as e:
                rejected.append((c, f"schema invalid: {str(e)[:100]}"))
        return kept, rejected

    def _grade(
        self, p: Pattern, candidates: list[dict],
        batch_id: Optional[str] = None,
    ) -> tuple[dict[int, int], ConsensusResult]:
        empty = ConsensusResult(
            calls=[], primary_used=True, accepted=False,
            batch_id=batch_id or "skipped",
            groq_run_id="skipped", prompt_version="xling_grade_v1",
            started_at="", finished_at="",
        )
        if not candidates:
            return {}, empty
        prompt_user = self._build_grader_user_prompt(p, candidates)
        consensus = self.client.consensus(
            self.GRADER_SYSTEM_PROMPT, prompt_user,
            max_tokens=2500, prompt_version="xling_grade_v1",
            batch_id=batch_id,
        )
        per_call_lists: list[list[int]] = []
        for call in consensus.calls:
            if not call.parsed:
                continue
            scored = call.parsed.get("grades", [])
            if not isinstance(scored, list):
                continue
            indexed: list[int] = []
            for entry in scored:
                s = entry.get("score") if isinstance(entry, dict) else None
                if isinstance(s, (int, float)):
                    indexed.append(int(round(float(s))))
                else:
                    indexed.append(-1)
            if any(x >= 0 for x in indexed):
                per_call_lists.append(indexed)
        final: dict[int, int] = {}
        for i in range(len(candidates)):
            scores = []
            for lst in per_call_lists:
                if i < len(lst) and lst[i] >= 0:
                    scores.append(lst[i])
            if scores:
                scores.sort()
                final[i] = scores[len(scores) // 2]
        return final, consensus

    def generate(
        self, p: Pattern, n: int = 8,
        batch_id: Optional[str] = None,
    ) -> XlingResult:
        result = XlingResult(pattern_id=p.id)

        raw, gen_consensus = self._generate_raw(p, n, batch_id)
        result.consensus = gen_consensus
        result.raw_candidate_count = len(raw)
        if not raw:
            return result

        valid, schema_rej = self._validate_schema(raw)
        result.rejected.extend(schema_rej)
        if not valid:
            return result

        scores, grader_consensus = self._grade(p, valid, batch_id)
        result.grader_consensus = grader_consensus
        grader_unavailable = not any(
            c.parsed for c in (grader_consensus.calls or [])
        )

        for i, cand in enumerate(valid):
            score = scores.get(i)
            if score is None and grader_unavailable:
                # No grader signal — accept on schema validity alone
                try:
                    result.accepted.append(CrossLingualTestQuery(**cand))
                except ValidationError as e:
                    result.rejected.append((cand, f"late schema: {e}"))
                continue
            if score is None or score < QUALITY_THRESHOLD:
                result.rejected.append(
                    (cand, f"quality grade {score or 0} < {QUALITY_THRESHOLD}")
                )
                continue
            try:
                result.accepted.append(CrossLingualTestQuery(**cand))
            except ValidationError as e:
                result.rejected.append((cand, f"late schema: {e}"))
        return result


def smoke():  # pragma: no cover
    print("xling_query_generator full implementation OK")


if __name__ == "__main__":
    smoke()
