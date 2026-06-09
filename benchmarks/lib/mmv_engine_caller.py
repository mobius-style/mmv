"""Bridge that runs a prompt through the MMV RoutingEngine.

Used by model_client when a profile has backend=mobius_engine. The bridge:
  1. Constructs a RoutingEngine with the appropriate InferenceAdapter
     (OllamaAdapter for 9B, GroqInferenceAdapter for 120B).
  2. Calls engine.evaluate(prompt) for a single-turn evaluation.
  3. Returns text + latency + metadata in a model_client.CallResult.

A single engine instance is cached per (target_backend, model_id) so that
repeated calls across one benchmark run amortise construction cost (the
RoutingEngine pulls in Box B, audit, memory_indexer, etc.).

Web search / RAG / Box X are LEFT OFF for this bridge — the comparison is
"does MMV's routing + governance layer help on top of the bare model,
without retrieval augmentation". Adding retrieval would conflate routing
and retrieval benefits.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.lib.model_client import CallResult  # noqa: E402

_engine_cache: dict[tuple[str, str], Any] = {}


def _build_engine(target_backend: str, model_id: str, endpoint: str,
                  timeout_s: int):
    """Construct a RoutingEngine wired to the requested backend."""
    if target_backend == "ollama":
        from src.adapters.ollama_adapter import OllamaAdapter
        adapter = OllamaAdapter(
            endpoint=endpoint,
            model_name=model_id,
            timeout=timeout_s,
        )
    elif target_backend == "groq":
        from benchmarks.lib.groq_inference_adapter import GroqInferenceAdapter
        adapter = GroqInferenceAdapter(
            endpoint=endpoint,
            model_name=model_id,
            timeout=timeout_s,
        )
    else:
        raise ValueError(f"unsupported target_backend for MMV engine: "
                         f"{target_backend!r}")

    from src.kernel.routing_engine import RoutingEngine
    # No retrieval augmentation — see module docstring.
    return RoutingEngine(adapter=adapter)


def _get_engine(target_backend: str, model_id: str, endpoint: str,
                timeout_s: int):
    key = (target_backend, model_id)
    if key not in _engine_cache:
        _engine_cache[key] = _build_engine(target_backend, model_id, endpoint,
                                           timeout_s)
    return _engine_cache[key]


def call_via_engine(prompt: str, profile: dict[str, Any]) -> CallResult:
    """Run prompt through a (cached) RoutingEngine and shape a CallResult.

    The profile must declare:
      backend: mobius_engine
      target_backend: ollama | groq
      target_endpoint: str
      model_id: str
      timeout_s: int (optional)
    """
    target_backend = profile.get("target_backend")
    target_endpoint = (profile.get("target_endpoint") or "").rstrip("/")
    model_id = profile.get("model_id")
    timeout_s = int(profile.get("timeout_s", 120))

    if not target_backend or not target_endpoint or not model_id:
        return CallResult(
            text="", latency_ms=0,
            error="profile missing target_backend/target_endpoint/model_id",
            backend="mobius_engine", endpoint=target_endpoint or "n/a",
        )

    try:
        engine = _get_engine(target_backend, model_id, target_endpoint,
                             timeout_s)
    except Exception as e:
        return CallResult(
            text="", latency_ms=0,
            error=f"engine construction failed: {type(e).__name__}: {e}",
            backend="mobius_engine", endpoint=target_endpoint,
        )

    t0 = time.time()
    try:
        # SessionState is created lazily inside evaluate() when state=None.
        result = engine.evaluate(prompt)
    except Exception as e:
        return CallResult(
            text="", latency_ms=int((time.time() - t0) * 1000),
            error=f"engine evaluate failed: {type(e).__name__}: {e}",
            backend="mobius_engine", endpoint=target_endpoint,
        )

    latency_ms = int((time.time() - t0) * 1000)
    text = (getattr(result, "response_text", None) or "").strip()
    decision = getattr(result, "decision", None)
    route = getattr(decision, "route", None) if decision else None
    reason_code = getattr(decision, "reason_code", None) if decision else None
    if callable(reason_code):
        try:
            reason_code = reason_code()
        except Exception:
            reason_code = None

    # Token counts are not uniformly available; approximate from words.
    tokens_in = len(prompt.split())
    tokens_out = len(text.split())

    result = CallResult(
        text=text,
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        error=None,
        backend="mobius_engine",
        endpoint=target_endpoint,
        reported_model=f"mmv:{model_id}",
        raw={
            "route": route,
            "reason_code": reason_code,
            "target_backend": target_backend,
        },
    )

    # Opt-in post-processor: contextual clarify + verify fallback.
    if profile.get("post_process"):
        from .mmv_post_processor import post_process
        result = post_process(prompt, result, profile)

    return result
