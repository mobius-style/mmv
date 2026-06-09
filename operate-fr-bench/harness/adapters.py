"""Model adapter façade for OPERATE-FR.

For OPERATE-FR v0.1 the official supported backends are:
  - `dummy`              : deterministic stub (no network) used by dry-run.
  - `openai_compatible`  : any /v1/chat/completions endpoint (Ollama's
                           /v1 surface, Groq, vLLM, etc.).
  - `ollama_generate`    : direct Ollama /api/generate (think:false), for
                           local 9B-class baselines without OpenAI wrapper.

Where possible we reuse the parent project's `benchmarks/lib/model_client`
so we don't duplicate HTTP handling. The OPERATE-FR adapter only
translates profiles + adds a tool-mode envelope.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class AdapterResult:
    text: str
    tool_calls: list[dict]
    latency_ms: int
    tokens_in: int | None
    tokens_out: int | None
    error: str | None
    model_id: str


# ─── dummy backend ───────────────────────────────────────────────────


def _call_dummy(prompt: str, profile: dict[str, Any]) -> AdapterResult:
    """Deterministic stub.

    Branches on a small bag of keywords so the dry-run exercises more than
    one classifier route:

      - stable arithmetic / language / geography / capital → direct answer
      - everything else → cutoff-bounded response that should classify
        as `date_bound_answer`

    Phrasing is chosen to avoid the explicit refusal lexicon
    (`I cannot`, `I won't`, …) so the classifier sees the intended route.
    """
    low = prompt.lower()
    stable_markers = (
        "7 multiplied by 8", "square root", "what is 15 percent",
        "boiling point", "chemical symbol", "capital city",
        "longest river", "translate the english word", "wrote the play",
        "world war ii end", "first person to walk", "binary search",
        "lifo", "http stand", "hamlet", "animal farm",
        "12 と 13", "日本で一番高い山", "原子番号",
        "what does 'au revoir'", "past tense of",
        "third angle", "solve for x", "mount everest", "speed of light",
        "recursive function", "apollo 11", "gdpr stand",
        "本能寺の変",
    )
    if any(m in low for m in stable_markers):
        text = (
            "[DUMMY-RESPONSE] Stable factual control: returning a direct "
            "templated answer. The expected route for a stable item is "
            "`answer`; this stub is here so the harness pipeline exercises "
            "that path."
        )
    else:
        text = (
            "[DUMMY-RESPONSE] As of my training cutoff in early 2025, the "
            "most reliable thing this stub can share is that the answer "
            "is time-sensitive and may have changed since then. An up-to-"
            "date source would be needed to confirm the present value."
        )
    return AdapterResult(
        text=text,
        tool_calls=[],
        latency_ms=1,
        tokens_in=len(prompt.split()),
        tokens_out=len(text.split()),
        error=None,
        model_id=profile.get("model_id", "dummy-route-test"),
    )


# ─── OpenAI-compatible / Ollama / Groq via parent model_client ───────


def _resolve_prefix(profile: dict[str, Any]) -> str:
    """Resolve a `prefix` or `prefix_file` field in the profile to plain text.

    Used by RC3.2-style profiles: the doctrine text is prepended to the user
    prompt before dispatch. The prefix file path is resolved relative to the
    parent repo root so paths in YAML can be 'eval/rc3_2/prefixes/<x>.txt'.
    """
    text = profile.get("prefix")
    if text:
        return str(text).rstrip()
    path = profile.get("prefix_file")
    if path:
        full = (REPO_ROOT / path).resolve()
        if not full.exists():
            raise FileNotFoundError(f"prefix_file not found: {full}")
        return full.read_text(encoding="utf-8").rstrip()
    return ""


def _maybe_prepend_prefix(prompt: str, profile: dict[str, Any]) -> str:
    pre = _resolve_prefix(profile)
    if not pre:
        return prompt
    return f"{pre}\n\n{prompt}"


def _maybe_apply_route_transformer(
    prompt: str, profile: dict[str, Any]
) -> tuple[str, str | None, bool]:
    """120B-only pre-generation route transformer.

    When the profile sets `route_transformer: true`, prepend a family-aware
    micro-instruction in place of (or in addition to) any prefix_file. The
    transformer is mutually compatible with prefix_file (it runs first),
    but ablation profiles typically use one or the other, not both.

    Returns (final_prompt, detected_family, did_inject).
    """
    if not profile.get("route_transformer"):
        return prompt, None, False
    # local import to keep adapter import cheap and avoid cycles
    from .route_transformer import prepare
    out = prepare(prompt)
    return out.transformed_prompt, out.detected_family, out.injected


def _make_parent_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Translate an OPERATE-FR profile into the parent harness's profile."""
    backend = profile["backend"]
    if backend == "mobius_engine":
        # Pass through the mobius_engine fields directly — the parent
        # model_client knows how to handle them via mmv_engine_caller.
        out = {
            "backend": "mobius_engine",
            "target_backend": profile["target_backend"],
            "target_endpoint": profile["target_endpoint"],
            "model_id": profile["model_id"],
            "api_kind": "mobius_engine",
            "temperature": float(profile.get("temperature", 0.0)),
            "max_tokens": int(profile.get("max_tokens", 1024)),
            "timeout_s": int(profile.get("timeout_s", 180)),
            "retry": int(profile.get("retry", 0)),
            "post_process": bool(profile.get("post_process", False)),
            "purity_guard": profile.get("purity_guard") or {
                "require_backend": "mobius_engine",
            },
        }
        if "api_key_env" in profile:
            out["api_key_env"] = profile["api_key_env"]
        return out
    if backend == "openai_compatible":
        return {
            "backend": "openai_compatible",
            "endpoint": profile.get("base_url") or profile.get("endpoint"),
            "model_id": profile["model_id"],
            "api_kind": "openai_chat",
            "temperature": float(profile.get("temperature", 0.0)),
            "max_tokens": int(profile.get("max_tokens", 1024)),
            "timeout_s": int(profile.get("timeout_s", 60)),
            "retry": int(profile.get("retry", 1)),
            "api_key_env": profile.get("api_key_env"),
            "purity_guard": profile.get("purity_guard") or {
                "require_backend": "openai_compatible",
            },
        }
    if backend == "groq":
        return {
            "backend": "groq",
            "endpoint": profile.get("base_url",
                                    "https://api.groq.com/openai/v1"),
            "model_id": profile["model_id"],
            "api_kind": "openai_chat",
            "temperature": float(profile.get("temperature", 0.0)),
            "max_tokens": int(profile.get("max_tokens", 1024)),
            "timeout_s": int(profile.get("timeout_s", 60)),
            "retry": int(profile.get("retry", 1)),
            "api_key_env": profile.get("api_key_env", "GROQ_API_KEY"),
            "purity_guard": profile.get("purity_guard") or {
                "require_backend": "groq",
            },
        }
    if backend == "ollama":
        return {
            "backend": "ollama",
            "endpoint": profile.get("endpoint", "http://localhost:11434"),
            "model_id": profile["model_id"],
            "api_kind": "ollama_generate",
            "temperature": float(profile.get("temperature", 0.0)),
            "max_tokens": int(profile.get("max_tokens", 1024)),
            "timeout_s": int(profile.get("timeout_s", 120)),
            "retry": int(profile.get("retry", 1)),
            "extra": profile.get("extra") or {"think": False},
            "purity_guard": profile.get("purity_guard") or {
                "require_backend": "ollama",
            },
        }
    raise ValueError(f"unsupported backend for OPERATE-FR: {backend!r}")


def _maybe_apply_post_validator(
    prompt: str, response: str, profile: dict[str, Any],
    family_hint: str | None,
) -> tuple[str, list[str], bool]:
    """120B-only post-route validator.

    When the profile sets `post_validator: true`, run
    route_transformer.post_validate over the model's response and apply
    deterministic rewrites for family contract violations
    (volatile_current direct claim, stale_premise accepted, ambiguous
    silent timeframe, freshness-only refusal).

    Returns (final_text, notes, rewritten).
    """
    if not profile.get("post_validator"):
        return response, [], False
    from .route_transformer import post_validate
    vr = post_validate(prompt, response, family=family_hint)
    return vr.text, vr.notes, vr.rewritten


def _call_via_parent(prompt: str, profile: dict[str, Any]) -> AdapterResult:
    from benchmarks.lib.model_client import call_model  # type: ignore
    parent_profile = _make_parent_profile(profile)
    # 1. route-transformer (family-aware micro-prefix), if enabled
    rt_prompt, detected_family, rt_injected = _maybe_apply_route_transformer(
        prompt, profile,
    )
    # 2. doctrine prefix_file, if any (mutually compatible)
    final_prompt = _maybe_prepend_prefix(rt_prompt, profile)
    cr = call_model(final_prompt, parent_profile)

    text = cr.text or ""

    # 3. Post-validator (rewrites on family contract violation), if enabled.
    #    Family hint: prefer transformer detection; otherwise post_validate
    #    will rerun detection on the original prompt internally.
    post_text, post_notes, post_rewrote = _maybe_apply_post_validator(
        prompt, text, profile, detected_family,
    )

    res = AdapterResult(
        text=post_text,
        tool_calls=[],  # OPERATE-FR v0.1 dry baselines run in no_tool mode
        latency_ms=cr.latency_ms,
        tokens_in=cr.tokens_in,
        tokens_out=cr.tokens_out,
        error=cr.error,
        model_id=cr.reported_model or profile["model_id"],
    )
    # Surface transformer / validator audit info so run_eval can record it
    if rt_injected or detected_family is not None:
        res.__dict__["route_transformer_family"] = detected_family
        res.__dict__["route_transformer_injected"] = rt_injected
    if post_rewrote or post_notes:
        res.__dict__["post_validator_rewritten"] = post_rewrote
        res.__dict__["post_validator_notes"] = post_notes
    return res


# ─── dispatch ────────────────────────────────────────────────────────


def call_adapter(prompt: str, profile: dict[str, Any]) -> AdapterResult:
    """Single entry. Errors are returned as AdapterResult.error, not raised.

    Per the spec: a single failing task must not crash the run.
    """
    backend = profile.get("backend")
    t0 = time.time()
    try:
        if backend == "dummy":
            return _call_dummy(prompt, profile)
        if backend in ("openai_compatible", "groq", "ollama", "mobius_engine"):
            return _call_via_parent(prompt, profile)
        return AdapterResult(
            text="", tool_calls=[],
            latency_ms=int((time.time() - t0) * 1000),
            tokens_in=None, tokens_out=None,
            error=f"unknown backend: {backend!r}",
            model_id=profile.get("model_id", "?"),
        )
    except Exception as e:
        return AdapterResult(
            text="", tool_calls=[],
            latency_ms=int((time.time() - t0) * 1000),
            tokens_in=None, tokens_out=None,
            error=f"adapter exception: {type(e).__name__}: {e}",
            model_id=profile.get("model_id", "?"),
        )
