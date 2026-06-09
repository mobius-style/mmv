"""Tests for scripts/pattern_autogen/groq_client.py — mock-based, no
network calls. Covers consensus logic and origin tagging structure."""
from __future__ import annotations

import re

from scripts.pattern_autogen.groq_client import (
    AutogenGroqClient, _gen_batch_id, _gen_run_id, _try_parse_json,
)


# ─── Fake GroqClient ──────────────────────────────────────────────────

class _FakeClient:
    """Stub for eval.rl_bench.groq_client.GroqClient.

    Configure per-temperature responses via .responses dict
    (key=temperature, value=list of (text, error) tuples popped FIFO)."""

    def __init__(self) -> None:
        self.responses: dict[float, list[tuple[str, str | None]]] = {}
        self.calls: list[dict] = []

    def chat(self, model, messages, temperature, max_tokens,
             retries=2, backoff=2.0):
        self.calls.append({
            "model": model, "temperature": temperature,
            "max_tokens": max_tokens,
        })
        bucket = self.responses.get(temperature)
        if not bucket:
            return {
                "text": "", "latency_ms": 1, "model": model,
                "error": "no fake response queued", "usage": None,
            }
        text, err = bucket.pop(0)
        return {
            "text": text, "latency_ms": 5, "model": model,
            "error": err, "usage": {"total_tokens": 10},
        }


# ─── _try_parse_json ─────────────────────────────────────────────────

def test_try_parse_json_plain_dict() -> None:
    assert _try_parse_json('{"a": 1, "b": "c"}') == {"a": 1, "b": "c"}


def test_try_parse_json_with_fences() -> None:
    s = '```json\n{"x": [1, 2, 3]}\n```'
    assert _try_parse_json(s) == {"x": [1, 2, 3]}


def test_try_parse_json_embedded() -> None:
    s = 'Here is the result: {"ok": true}\nThanks!'
    assert _try_parse_json(s) == {"ok": True}


def test_try_parse_json_non_object_returns_none() -> None:
    assert _try_parse_json('[1, 2, 3]') is None
    assert _try_parse_json('"plain string"') is None
    assert _try_parse_json('') is None
    assert _try_parse_json('not json') is None


# ─── ID generators ────────────────────────────────────────────────────

def test_gen_batch_id_format() -> None:
    from datetime import datetime, timezone
    bid = _gen_batch_id(datetime(2026, 4, 26, 11, 22, 33, tzinfo=timezone.utc))
    assert re.fullmatch(r"bat_20260426_112233_[0-9a-f]{4}", bid)


def test_gen_run_id_format() -> None:
    from datetime import datetime, timezone
    rid = _gen_run_id(datetime(2026, 4, 26, 11, 22, 33, tzinfo=timezone.utc))
    assert re.fullmatch(r"run_20260426_112233_[0-9a-f]{6}", rid)


# ─── Consensus happy path ────────────────────────────────────────────

def test_consensus_all_primary_succeed() -> None:
    fake = _FakeClient()
    fake.responses[0.3] = [('{"ok": true, "n": 1}', None)]
    fake.responses[0.7] = [('{"ok": true, "n": 2}', None)]
    fake.responses[1.0] = [('{"ok": true, "n": 3}', None)]
    cli = AutogenGroqClient(_client=fake, prompt_version="t1")
    r = cli.consensus("system", "user", max_tokens=20)
    assert r.primary_used is True
    assert r.accepted is True
    assert len(r.calls) == 3
    assert all(c.parsed and c.parsed["ok"] for c in r.calls)
    # All used PRIMARY model
    assert all(c.model == "openai/gpt-oss-120b" for c in r.calls)
    # Only 3 chat calls (no fallback retries)
    assert len(fake.calls) == 3


def test_consensus_origin_dict_structure() -> None:
    fake = _FakeClient()
    for t in (0.3, 0.7, 1.0):
        fake.responses[t] = [('{"x": 1}', None)]
    cli = AutogenGroqClient(_client=fake, prompt_version="p2")
    r = cli.consensus("s", "u")
    o = r.origin_dict()
    assert o["type"] == "autogen"
    assert o["prompt_version"] == "p2"
    assert o["batch_id"].startswith("bat_")
    assert o["groq_run_id"].startswith("run_")
    assert "date" in o


# ─── Fallback path ────────────────────────────────────────────────────

def test_consensus_fallback_when_one_primary_fails() -> None:
    fake = _FakeClient()
    fake.responses[0.3] = [
        ("", "rate_limit"),                  # primary fails
        ('{"ok": "fb"}', None),               # fallback succeeds
    ]
    fake.responses[0.7] = [('{"ok": 1}', None)]   # primary succeeds
    fake.responses[1.0] = [('{"ok": 2}', None)]   # primary succeeds
    cli = AutogenGroqClient(_client=fake)
    r = cli.consensus("s", "u")
    assert r.primary_used is False  # any failure flips this flag
    assert r.accepted is True
    # The 0.3 slot used fallback model, the others stayed on primary
    by_t = {c.temperature: c for c in r.calls}
    assert by_t[0.3].model == "llama-3.3-70b-versatile"
    assert by_t[0.7].model == "openai/gpt-oss-120b"
    assert by_t[1.0].model == "openai/gpt-oss-120b"


def test_consensus_accepted_false_when_majority_unparseable() -> None:
    fake = _FakeClient()
    # All 3 primary calls succeed but content is unparseable
    fake.responses[0.3] = [("not json", None)]
    fake.responses[0.7] = [("also bad", None)]
    fake.responses[1.0] = [('{"ok": true}', None)]
    cli = AutogenGroqClient(_client=fake)
    r = cli.consensus("s", "u")
    assert r.primary_used is True   # no errors so fallback not invoked
    # Only 1 of 3 parsed → accepted requires ≥2
    assert r.accepted is False


# ─── Generator stub smoke ─────────────────────────────────────────────

def test_all_generator_stubs_importable() -> None:
    from scripts.pattern_autogen import (
        variants_generator, negatives_generator, xling_query_generator,
        quality_grader, conflict_checker,
    )
    assert hasattr(variants_generator, "VariantsGenerator")
    assert hasattr(negatives_generator, "NegativesGenerator")
    assert hasattr(xling_query_generator, "XlingGenerator")
    assert hasattr(quality_grader, "QualityGrader")
    assert hasattr(conflict_checker, "ConflictChecker")
