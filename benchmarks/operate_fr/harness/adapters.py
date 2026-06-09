"""Adapter glue for OPERATE-FR.

This is a thin wrapper around the existing benchmarks.lib.model_client so
the operate_fr package speaks the harness vocabulary in the spec:
    profiles: dummy | openai_compatible | (ollama / groq via existing types)

Returned `Response` carries text, latency_ms, error, raw and the (always
empty for now) tool_calls list — OPERATE-FR v0.1 does not run tool-mode
in this initial harness.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.lib.config_loader import get_profile  # noqa: E402
from benchmarks.lib.model_client import call_model  # noqa: E402


@dataclass
class Response:
    text: str
    latency_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    error: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def resolve_profile(name: str) -> dict[str, Any]:
    """Pull a profile by name from benchmarks/configs/model_profiles.yaml."""
    return get_profile(name)


def invoke(prompt: str, profile_name: str) -> Response:
    profile = resolve_profile(profile_name)
    cr = call_model(prompt, profile)
    return Response(
        text=cr.text or "",
        latency_ms=cr.latency_ms,
        tokens_in=cr.tokens_in,
        tokens_out=cr.tokens_out,
        error=cr.error,
        tool_calls=[],   # v0.1: no tool-mode yet
        raw=cr.raw or {},
    )
