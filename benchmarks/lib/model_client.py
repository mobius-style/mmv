"""Backend-agnostic model client.

Routes a (prompt, profile) pair to one of:
  - ollama         : api/generate (with think:false), single-prompt
  - groq           : OpenAI-compat chat/completions
  - openai_compat  : any OpenAI-compatible /v1/chat/completions endpoint
  - dummy          : deterministic stub (no network)

Every call returns a CallResult and runs through purity_guard.enforce_purity().
API keys are read from process env or, for Groq, from .env / .env.groq.
Keys are NEVER returned, logged, or echoed back in CallResult.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # the dummy backend still works

from .purity_guard import CallEvidence, declared_endpoint, enforce_purity

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def _resolve_api_key(env_name: str) -> str | None:
    """Look up an API key. Order: process env > .env > .env.groq (groq only)."""
    val = os.environ.get(env_name)
    if val:
        return val
    for fname in (".env", ".env.groq"):
        kv = _read_env_file(REPO_ROOT / fname)
        if env_name in kv and kv[env_name]:
            return kv[env_name]
    return None


@dataclass
class CallResult:
    text: str
    latency_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    error: str | None = None
    backend: str = ""
    endpoint: str = ""
    reported_model: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


# ─── backends ──────────────────────────────────────────────────────────


def _call_ollama(prompt: str, profile: dict[str, Any]) -> CallResult:
    if requests is None:
        return CallResult("", 0, error="requests library not available")
    endpoint = declared_endpoint(profile)
    url = f"{endpoint}/api/generate"
    payload = {
        "model": profile["model_id"],
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": float(profile.get("temperature", 0.0)),
            "num_predict": int(profile.get("max_tokens", 1024)),
        },
    }
    # CRITICAL: see CLAUDE.md — qwen3.5 on Ollama needs think:false on api/generate.
    extra = profile.get("extra") or {}
    if "think" in extra:
        payload["think"] = bool(extra["think"])

    t0 = time.time()
    try:
        r = requests.post(url, json=payload, timeout=float(profile.get("timeout_s", 120)))
        latency_ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            return CallResult(
                "", latency_ms,
                error=f"ollama http {r.status_code}: {r.text[:200]}",
                backend="ollama", endpoint=endpoint,
            )
        data = r.json()
        text = (data.get("response") or "").strip()
        return CallResult(
            text=text,
            latency_ms=latency_ms,
            tokens_in=data.get("prompt_eval_count"),
            tokens_out=data.get("eval_count"),
            backend="ollama",
            endpoint=endpoint,
            reported_model=data.get("model"),
            raw={"done_reason": data.get("done_reason")},
        )
    except Exception as e:
        return CallResult("", int((time.time() - t0) * 1000), error=f"ollama exc: {e}",
                          backend="ollama", endpoint=endpoint)


def _call_openai_chat(prompt: str, profile: dict[str, Any], backend_label: str) -> CallResult:
    if requests is None:
        return CallResult("", 0, error="requests library not available")
    endpoint = declared_endpoint(profile)
    url = f"{endpoint}/chat/completions"
    api_key_env = profile.get("api_key_env")
    api_key = _resolve_api_key(api_key_env) if api_key_env else None

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": profile["model_id"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(profile.get("temperature", 0.0)),
        "max_tokens": int(profile.get("max_tokens", 1024)),
    }
    t0 = time.time()
    try:
        r = requests.post(url, json=payload, headers=headers,
                          timeout=float(profile.get("timeout_s", 60)))
        latency_ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            return CallResult(
                "", latency_ms,
                error=f"{backend_label} http {r.status_code}: {r.text[:200]}",
                backend=backend_label, endpoint=endpoint,
            )
        data = r.json()
        choices = data.get("choices") or []
        text = ""
        if choices:
            msg = choices[0].get("message") or {}
            text = (msg.get("content") or "").strip()
        usage = data.get("usage") or {}
        return CallResult(
            text=text,
            latency_ms=latency_ms,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            backend=backend_label,
            endpoint=endpoint,
            reported_model=data.get("model"),
            raw={"finish_reason": (choices[0] or {}).get("finish_reason") if choices else None},
        )
    except Exception as e:
        return CallResult("", int((time.time() - t0) * 1000), error=f"{backend_label} exc: {e}",
                          backend=backend_label, endpoint=endpoint)


def _call_dummy(prompt: str, profile: dict[str, Any]) -> CallResult:
    """Deterministic stub. Echoes a short reply so smoke tests can grade structure."""
    text = (
        "[DUMMY-RESPONSE] I am a stub. "
        f"Got prompt of length {len(prompt)}. "
        "Refusing to claim factual knowledge. "
        "Would you like to clarify the question?"
    )
    return CallResult(
        text=text,
        latency_ms=1,
        tokens_in=len(prompt.split()),
        tokens_out=len(text.split()),
        backend="dummy",
        endpoint="none",
        reported_model="dummy-echo-v1",
    )


# ─── public API ────────────────────────────────────────────────────────

def _call_mobius_engine(prompt: str, profile: dict[str, Any]) -> CallResult:
    """Dispatch to the in-process RoutingEngine via mmv_engine_caller.

    Imported lazily so the bench harness can still operate when src/ is
    unimportable (e.g. in CI without the full runtime dependencies).
    """
    try:
        from .mmv_engine_caller import call_via_engine
    except Exception as e:
        return CallResult(
            text="", latency_ms=0,
            error=f"mobius_engine import failed: {type(e).__name__}: {e}",
            backend="mobius_engine",
        )
    return call_via_engine(prompt, profile)


_BACKENDS = {
    "ollama": _call_ollama,
    "groq": lambda p, prof: _call_openai_chat(p, prof, "groq"),
    "openai_compatible": lambda p, prof: _call_openai_chat(p, prof, "openai_compatible"),
    "mobius_engine": _call_mobius_engine,
    "dummy": _call_dummy,
}


def call_model(prompt: str, profile: dict[str, Any]) -> CallResult:
    """Single-shot call routed by profile['backend'].

    Retries once on transient error if profile['retry'] >= 1. Always runs the
    purity guard on success; the guard raises PurityViolation on mismatch
    rather than returning a soft error.
    """
    backend = profile.get("backend")
    if backend not in _BACKENDS:
        return CallResult("", 0, error=f"unknown backend: {backend}")

    fn = _BACKENDS[backend]
    retries = int(profile.get("retry", 0))
    last: CallResult | None = None
    for attempt in range(retries + 1):
        result = fn(prompt, profile)
        last = result
        if result.error is None and result.text:
            break
        if attempt < retries:
            time.sleep(0.5 * (attempt + 1))

    assert last is not None
    if last.error is None:
        enforce_purity(
            profile,
            CallEvidence(
                backend=last.backend or (backend or ""),
                endpoint=last.endpoint or declared_endpoint(profile),
                reported_model=last.reported_model,
            ),
        )
    return last


def probe_profile(profile: dict[str, Any]) -> CallResult:
    """Tiny ping to confirm the endpoint is alive. Used by scripts."""
    return call_model("ping", profile)
