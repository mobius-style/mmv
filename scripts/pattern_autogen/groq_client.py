"""scripts/pattern_autogen/groq_client.py — Pattern Library auto-gen Groq adapter.

Wraps eval/rl_bench/groq_client.GroqClient with:
    - Multi-judge consensus (N=3 calls at configurable temperatures)
    - Primary → fallback model degradation
    - Origin metadata stamping (batch_id / groq_run_id / prompt_version)
    - JSON parsing with graceful fallback for non-JSON responses

Auth: GROQ_API_KEY loaded via eval.rl_bench.env_loader.load_groq_key()
(reads .env at the repo root) — no key is hardcoded here.

Spec reference: docs/PATTERN_LIBRARY_SPEC_v1_3.md Section 4.2 (quality
assurance per stage) + Section 5.3 (Phase 2 task list).
"""
from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

PRIMARY_MODEL = "openai/gpt-oss-120b"
FALLBACK_MODEL = "llama-3.3-70b-versatile"

DEFAULT_TEMPERATURES = (0.3, 0.7, 1.0)


@dataclass
class JudgeCall:
    """Single Groq call result."""
    temperature: float
    text: str
    parsed: Optional[dict]
    model: str
    latency_ms: int
    error: Optional[str]
    usage: Optional[dict]


@dataclass
class ConsensusResult:
    """N-call consensus + the origin metadata to stamp on autogen artifacts."""
    calls: list[JudgeCall]
    primary_used: bool
    accepted: bool   # True iff at least 2/N calls returned parseable content
    batch_id: str
    groq_run_id: str
    prompt_version: str
    started_at: str
    finished_at: str
    metadata: dict = field(default_factory=dict)

    def origin_dict(self) -> dict:
        """Stamp for Pattern.origin (type='autogen')."""
        return {
            "type": "autogen",
            "date": self.started_at,
            "batch_id": self.batch_id,
            "groq_run_id": self.groq_run_id,
            "prompt_version": self.prompt_version,
        }


def _gen_batch_id(now: datetime) -> str:
    """Format: bat_YYYYMMDD_HHMMSS_<hex2>"""
    return ("bat_" + now.strftime("%Y%m%d_%H%M%S")
            + "_" + secrets.token_hex(2))


def _gen_run_id(now: datetime) -> str:
    """Format: run_YYYYMMDD_HHMMSS_<hex3>"""
    return ("run_" + now.strftime("%Y%m%d_%H%M%S")
            + "_" + secrets.token_hex(3))


def _try_parse_json(text: str) -> Optional[dict]:
    """Attempt to parse a JSON object out of an LLM response. Tolerates
    leading/trailing whitespace and ```json fences."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        # Trim fence
        s = s.split("```", 2)[1] if "```" in s else s
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        # Try to find a {…} substring
        i = s.find("{")
        j = s.rfind("}")
        if i >= 0 and j > i:
            try:
                v = json.loads(s[i:j + 1])
                return v if isinstance(v, dict) else None
            except json.JSONDecodeError:
                return None
        return None


class AutogenGroqClient:
    """Thin compositional layer over eval.rl_bench.groq_client.GroqClient."""

    def __init__(
        self,
        primary_model: str = PRIMARY_MODEL,
        fallback_model: str = FALLBACK_MODEL,
        temperatures: tuple[float, ...] = DEFAULT_TEMPERATURES,
        prompt_version: str = "p1",
        max_tokens: int = 800,
        retries_per_call: int = 2,
        backoff: float = 2.0,
        _client=None,           # injectable for tests
    ) -> None:
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.temperatures = tuple(temperatures)
        self.prompt_version = prompt_version
        self.max_tokens = max_tokens
        self.retries_per_call = retries_per_call
        self.backoff = backoff
        self._client = _client  # if None, lazy-construct on first call

    def _ensure_client(self):
        if self._client is None:
            from eval.rl_bench.groq_client import GroqClient
            self._client = GroqClient()
        return self._client

    def consensus(
        self, system_prompt: str, user_prompt: str,
        *, max_tokens: Optional[int] = None,
        prompt_version: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> ConsensusResult:
        """Make N=len(temperatures) Groq calls, parse each, return all
        results plus origin metadata. Falls back to FALLBACK_MODEL if
        ANY of the N primary calls failed (errored or returned empty)."""
        client = self._ensure_client()
        max_tokens = max_tokens or self.max_tokens
        prompt_version = prompt_version or self.prompt_version
        now = datetime.now(timezone.utc)
        batch_id = batch_id or _gen_batch_id(now)
        groq_run_id = _gen_run_id(now)
        started_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]

        calls: list[JudgeCall] = []
        primary_used = True
        for t in self.temperatures:
            r = client.chat(
                model=self.primary_model, messages=messages,
                temperature=t, max_tokens=max_tokens,
                retries=self.retries_per_call, backoff=self.backoff,
            )
            calls.append(JudgeCall(
                temperature=t, text=r.get("text", ""),
                parsed=_try_parse_json(r.get("text", "")),
                model=r.get("model", self.primary_model),
                latency_ms=int(r.get("latency_ms", 0)),
                error=r.get("error"),
                usage=r.get("usage"),
            ))

        any_failed = any(c.error or not c.text for c in calls)
        if any_failed:
            # One pass on fallback for the failed slots only
            primary_used = False
            for idx, c in enumerate(calls):
                if c.error or not c.text:
                    r = client.chat(
                        model=self.fallback_model, messages=messages,
                        temperature=c.temperature, max_tokens=max_tokens,
                        retries=self.retries_per_call,
                        backoff=self.backoff,
                    )
                    calls[idx] = JudgeCall(
                        temperature=c.temperature,
                        text=r.get("text", ""),
                        parsed=_try_parse_json(r.get("text", "")),
                        model=r.get("model", self.fallback_model),
                        latency_ms=int(r.get("latency_ms", 0)),
                        error=r.get("error"),
                        usage=r.get("usage"),
                    )

        finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        accepted = sum(1 for c in calls if c.parsed is not None) >= 2

        return ConsensusResult(
            calls=calls, primary_used=primary_used, accepted=accepted,
            batch_id=batch_id, groq_run_id=groq_run_id,
            prompt_version=prompt_version,
            started_at=started_at, finished_at=finished_at,
        )


def smoke_test() -> None:  # pragma: no cover (network)
    """Minimal token-cost smoke: ask for {"ok": true}."""
    c = AutogenGroqClient()
    r = c.consensus(
        system_prompt='Reply with strict JSON {"ok": true}.',
        user_prompt="ping",
        max_tokens=20,
    )
    print("primary_used:", r.primary_used)
    print("accepted:", r.accepted)
    for call in r.calls:
        print(f"  t={call.temperature}  parsed={call.parsed} err={call.error}")
    print("origin:", r.origin_dict())


if __name__ == "__main__":
    smoke_test()
