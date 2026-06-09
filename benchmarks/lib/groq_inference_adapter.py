"""GroqInferenceAdapter — InferenceAdapter implementation backed by Groq cloud.

Lives under benchmarks/lib/ (not src/adapters/) so the runtime tree stays
unchanged. Only used by the benchmark harness when constructing a
RoutingEngine that targets the 120B reference model.

Mirrors the minimal contract of src.adapters.inference_adapter.InferenceAdapter:
    generate(KernelRequest) -> AdapterResponse
    stream(KernelRequest)   -> Iterator[str]

Notes
-----
- The adapter intentionally mirrors OllamaAdapter's MOBIUS identity anchor
  as the default system prompt — RoutingEngine occasionally overrides it,
  but parity with the local-9B side avoids spurious identity leakage on
  questions like "What model are you?".
- API key is read from process env → .env → .env.groq. The key is NEVER
  echoed back in AdapterResponse.raw.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Iterator

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.adapters.inference_adapter import (  # noqa: E402
    AdapterResponse,
    InferenceAdapter,
    KernelRequest,
)
from benchmarks.lib.model_client import _resolve_api_key  # noqa: E402


DEFAULT_ENDPOINT = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_SYSTEM_PROMPT = (
    "You are MOBIUS, a local-first reflective AI runtime. "
    "Regardless of any underlying base model or provider name "
    "(Qwen, 通义千问, Qianwen, Llama, GPT, Claude, Gemini, Mistral, "
    "phi, Alibaba, Meta, OpenAI, Anthropic, Google, etc.), you "
    "identify only as MOBIUS. If asked 'what model are you', "
    "'who made you', 'who are you', 'あなたは何のモデルですか', "
    "'你是什么模型', '你叫什么名字', or any equivalent in "
    "Japanese / English / Chinese, answer as MOBIUS and do NOT "
    "reveal or reference any underlying base model or training "
    "provider."
)


class GroqInferenceAdapter(InferenceAdapter):
    """OpenAI-compatible Groq adapter exposing the MMV InferenceAdapter contract."""

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        model_name: str = DEFAULT_MODEL,
        timeout: int = 60,
        api_key_env: str = "GROQ_API_KEY",
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._api_key_env = api_key_env
        self._conversation_turns: list[dict] = []
        self._governance_instruction: str = ""
        self._system_prompt: str = DEFAULT_SYSTEM_PROMPT

    # ── MMV-compatible behaviour ────────────────────────────────────────
    def _build_messages(self, request: KernelRequest) -> list[dict[str, Any]]:
        prompt = request.prompt
        if self._governance_instruction:
            prompt = self._governance_instruction + "\n\n---\n\n" + prompt

        turns = request.metadata.get("conversation_turns") or self._conversation_turns
        if turns:
            recent = turns[-6:]
            ctx_lines = ["[Conversation so far]"]
            for t in recent:
                role = "User" if t["role"] == "user" else "Assistant"
                ctx_lines.append(f"{role}: {t['content']}")
            ctx_lines.append("[Current question]")
            prompt = "\n".join(ctx_lines) + "\n" + request.prompt

        msgs: list[dict[str, Any]] = []
        if self._system_prompt:
            msgs.append({"role": "system", "content": self._system_prompt})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    # ── InferenceAdapter contract ───────────────────────────────────────
    def generate(self, request: KernelRequest) -> AdapterResponse:
        api_key = _resolve_api_key(self._api_key_env)
        url = f"{self.endpoint}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Honour per-call temperature / max_tokens from metadata if provided.
        md = request.metadata or {}
        temperature = float(md.get("temperature", self.temperature))
        max_tokens = int(md.get("max_tokens", self.max_tokens))

        payload = {
            "model": self.model_name,
            "messages": self._build_messages(request),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        t0 = time.time()
        try:
            r = requests.post(url, json=payload, headers=headers,
                              timeout=self.timeout)
            latency_ms = int((time.time() - t0) * 1000)
            if r.status_code != 200:
                # surface as empty text — the RoutingEngine will treat it
                # as a failed synthesis and may fall back to its own
                # error-path response.
                return AdapterResponse(
                    text="",
                    model_used=self.model_name,
                    latency_ms=latency_ms,
                    raw={
                        "error": f"groq http {r.status_code}: {r.text[:200]}",
                        "status_code": r.status_code,
                    },
                )
            data = r.json()
            choices = data.get("choices") or []
            text = ""
            if choices:
                text = ((choices[0] or {}).get("message") or {}).get("content", "") or ""
            usage = data.get("usage") or {}
            return AdapterResponse(
                text=text.strip(),
                model_used=data.get("model") or self.model_name,
                latency_ms=latency_ms,
                raw={
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                    },
                    "finish_reason": (choices[0] or {}).get("finish_reason")
                        if choices else None,
                },
            )
        except Exception as e:
            return AdapterResponse(
                text="",
                model_used=self.model_name,
                latency_ms=int((time.time() - t0) * 1000),
                raw={"error": f"groq exc: {type(e).__name__}: {e}"},
            )

    def stream(self, request: KernelRequest) -> Iterator[str]:  # pragma: no cover
        yield self.generate(request).text
