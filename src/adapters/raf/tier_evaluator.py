"""
tier_evaluator.py — 3-tier evaluation (AIOS 2.6.3 lineage)

Tier-1 Lint  : CPU, zero cost
Tier-2 Mirror: Ollama self-scoring
Tier-3 Judge : Groq GPT-OSS labeling

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations
import json
import os
import time
from typing import Optional

MIRROR_THRESHOLD  = 0.45
JUDGE_SAMPLE_RATE = 0.60
MAX_RECENT        = 10

JUDGE_SYSTEM_PROMPT = """You are a teacher model for an AI response system.
Evaluate the following query and respond ONLY with JSON (no preamble).

Fields:
1. formal_type: "yesno"|"what"|"how"|"why"|"selection"|"comparison"|"other"
2. intent_type: "factual_query"|"game_move"|"topic_continuation"|"translation_request"|"correction"|"meta_question"|"casual_greeting"|"creative_request"|"instruction_request"|"clarification"
3. qk_entitlement: "answerable"|"verify"|"abstain"
4. qk_tvs_estimate: "low"|"medium"|"high"
5. qk_mkr_risk: "low"|"medium"|"high"
6. qk_halfstep_type: "hidden_assumption"|"adjacent_contrast"|"missing_constraint"|"teaching_scaffold"|"none"
7. wiki_lookup: true|false
8. conv_override: true|false
9. confidence: 0.0-1.0

Output JSON only."""


class TierEvaluator:

    def lint(self, query: str, recent: list[str]) -> bool:
        """Tier-1: CPU. Returns False to discard."""
        if len(query.strip()) <= 2:
            return False
        if query.startswith("[ERROR"):
            return False
        if query.startswith("Sure,") or query.startswith("Of course"):
            return False
        for prev in recent[-MAX_RECENT:]:
            if self._ngram_sim(query, prev) > 0.85:
                return False
        return True

    def mirror(self, query: str, context: str) -> float:
        """Tier-2: Ollama self-scoring. Returns 0.0-1.0."""
        import requests
        prompt = (
            f"Rate whether this is a natural question (0.0 to 1.0).\n"
            f"Context: {context[:200]}\n"
            f"Query: {query}\n"
            f"Output only a number between 0.0 and 1.0:"
        )
        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "qwen3.5:4b", "prompt": prompt,
                      "stream": False, "think": False,
                      "options": {"num_predict": 10, "temperature": 0.0}},
                timeout=15,
            )
            text = resp.json().get("response", "").strip()
            for token in text.split():
                try:
                    return min(1.0, max(0.0, float(token)))
                except ValueError:
                    continue
            return 0.5
        except Exception:
            return 0.5

    def judge(self, query: str, context: str,
              language: str, groq_key: str) -> Optional[dict]:
        """Tier-3: Groq API labeling."""
        import requests
        user_msg = (
            f"Language: {language}\n"
            f"Context: {context[:300]}\n"
            f"Query: {query}"
        )
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": "openai/gpt-oss-120b",
                    "messages": [
                        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 300,
                },
                timeout=30,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            # Extract JSON from response
            if text.startswith("{"):
                return json.loads(text)
            # Try to find JSON in text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
            return None
        except Exception:
            return None

    def _ngram_sim(self, a: str, b: str, n: int = 3) -> float:
        ag = {a[i:i+n] for i in range(len(a)-n+1)}
        bg = {b[i:i+n] for i in range(len(b)-n+1)}
        if not ag or not bg:
            return 0.0
        return len(ag & bg) / len(ag | bg)
