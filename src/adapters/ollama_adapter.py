"""
ollama_adapter.py — Ollama inference adapter with QK dual-pass support.

Pass 1: QK-injected prompt → primary endpoint
Pass 2: Refinement (no QK) → secondary endpoint (or same)

Memory management:
- keep_alive=-1: keep model loaded during active use
- release_model(): free VRAM after heavy operations
"""
from __future__ import annotations

import json
import time
from typing import Iterator

import requests

from .inference_adapter import AdapterResponse, InferenceAdapter, KernelRequest
from ..kernel.errors import VllmConnectionError

DEFAULT_ENDPOINT = "http://localhost:11434"
DEFAULT_MODEL    = "phi4-mini:latest"


class OllamaAdapter(InferenceAdapter):

    def __init__(
        self,
        endpoint:        str = DEFAULT_ENDPOINT,
        model_name:      str = DEFAULT_MODEL,
        timeout:         int = 120,
        keep_alive:      int = 300,
        second_endpoint: str | None = None,
        dual_pass:       bool = False,
    ) -> None:
        self.endpoint        = endpoint.rstrip("/")
        self.model_name      = model_name
        self.timeout         = timeout
        self.keep_alive      = keep_alive
        self.second_endpoint = second_endpoint.rstrip("/") if second_endpoint else None
        self.dual_pass       = dual_pass
        self._conversation_turns: list[dict] = []
        self._governance_instruction: str = ""
        self._system_prompt: str = ""
        # cyc_20260424_zh_residual_cleanup — C-1b:
        # Unconditional MOBIUS identity anchor. Prevents base-model
        # identity leakage ("我叫 Qwen3.5 / 通义千问 / 阿里巴巴 ...",
        # "I am Llama by Meta", etc.) that was observed on ZH identity
        # queries even when the SELF_REF detector misses (C-1a) or when
        # Box 0 consultation context is otherwise absent. The anchor is
        # applied as the default self._system_prompt — callers that set
        # their own system prompt later on override as before
        # (_call_ollama `system` kwarg takes precedence over
        # self._system_prompt via `_sys = system or self._system_prompt`).
        # Language-agnostic (addresses JA / EN / ZH identity questions)
        # and does not alter any runtime prompt, QK block, or
        # conversation-history injection.
        self._system_prompt = (
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

    # ── QK prompt building ───────────────────────────────────────────────────

    def _build_qk_prompt(self, intent_type: str, original_prompt: str) -> str:
        """Inject QK metacognitive block into prompt. Fail-safe."""
        try:
            from .question_kernel import (
                select_kernels, format_kernel_block, get_zone_for_intent
            )
            zone = get_zone_for_intent(intent_type)
            kernels = select_kernels(intent_type, zone, "answer")
            block = format_kernel_block(kernels)
            if block:
                return block + "\n\n" + original_prompt
        except Exception:
            pass
        return original_prompt

    # ── Low-level Ollama call ────────────────────────────────────────────────

    def _call_ollama(self, prompt: str, endpoint: str | None = None,
                     metadata: dict | None = None,
                     system: str | None = None) -> AdapterResponse:
        """Single HTTP call to Ollama /api/generate."""
        ep = endpoint or self.endpoint
        url = f"{ep}/api/generate"
        md = metadata or {}
        payload = {
            "model":      self.model_name,
            "prompt":     prompt,
            "stream":     False,
            "keep_alive": self.keep_alive,
            "think":      False,
            "options": {
                "temperature":    md.get("temperature", 0.2),
                "num_predict":    md.get("max_tokens", 512),
                # cyc_20260425_engine_token_loop_fix:
                # Without explicit repeat_penalty / repeat_last_n /
                # top_k / top_p, qwen3.5:9b at temperature 0.2 entered
                # token-repetition loops ("私は私は…" / "メメメメ…")
                # on ~4/11 33-scenario categories (honest baseline
                # 18/33 on 2026-04-24). These are Ollama recommended
                # defaults; making them explicit breaks the loop while
                # preserving the existing low-temperature trajectory.
                "top_k":          md.get("top_k", 40),
                "top_p":          md.get("top_p", 0.9),
                "repeat_penalty": md.get("repeat_penalty", 1.1),
                "repeat_last_n":  md.get("repeat_last_n", 64),
            },
        }
        _sys = system or self._system_prompt
        if _sys:
            payload["system"] = _sys
        started = time.time()
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise VllmConnectionError(str(exc)) from exc
        latency_ms = int((time.time() - started) * 1000)
        text = (data.get("response") or "").strip()
        return AdapterResponse(
            text=text,
            model_used=self.model_name,
            latency_ms=latency_ms,
            raw=data,
        )

    # ── Main generate ────────────────────────────────────────────────────────

    def generate(self, request: KernelRequest) -> AdapterResponse:
        # Build prompt with existing injections (governance + conversation)
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

        # Extract intent/route from metadata
        intent_type = (request.metadata or {}).get("intent_type", "factual_query")
        route = (request.metadata or {}).get("route", "answer")

        # No QK for abstain/ask
        if route in ("abstain", "ask"):
            return self._call_ollama(prompt, metadata=request.metadata)

        # Pass 1: QK-injected prompt
        pass1_prompt = self._build_qk_prompt(intent_type, prompt)
        pass1_resp = self._call_ollama(pass1_prompt, metadata=request.metadata)

        # Single-pass mode: return immediately
        if not self.dual_pass:
            pass1_resp.raw["qk_meta"] = {
                "qk_mode": "single_pass",
                "intent_type": intent_type,
            }
            return pass1_resp

        # Pass 2: Refine (NO QK injection)
        pass2_endpoint = self.second_endpoint or self.endpoint
        user_input = getattr(request, "user_input", "")
        pass2_prompt = (
            f"Original query: {user_input}\n\n"
            f"Draft response:\n{pass1_resp.text}\n\n"
            f"Refine this response for accuracy and clarity."
        )
        pass2_resp = self._call_ollama(
            pass2_prompt, pass2_endpoint,
            metadata={"max_tokens": 256, "temperature": 0.2},
        )

        pass2_resp.raw["qk_meta"] = {
            "qk_mode": "pipeline" if self.second_endpoint else "single",
            "intent_type":      intent_type,
            "pass1_endpoint":   self.endpoint,
            "pass2_endpoint":   pass2_endpoint,
            "pass1_latency_ms": pass1_resp.latency_ms,
            "pass2_latency_ms": pass2_resp.latency_ms,
        }
        return pass2_resp

    def stream(self, request: KernelRequest) -> Iterator[str]:
        yield self.generate(request).text

    # ── Streaming support ────────────────────────────────────────────────────

    def _call_ollama_stream(
        self,
        prompt: str,
        endpoint: str | None = None,
        metadata: dict | None = None,
    ) -> Iterator[str]:
        """Streaming HTTP call to Ollama. Yields tokens."""
        ep = endpoint or self.endpoint
        url = f"{ep}/api/generate"
        md = metadata or {}
        payload = {
            "model":      self.model_name,
            "prompt":     prompt,
            "stream":     True,
            "keep_alive": self.keep_alive,
            "think":      False,
            "options": {
                "temperature":    md.get("temperature", 0.2),
                "num_predict":    md.get("max_tokens", 512),
                # cyc_20260425_engine_token_loop_fix — see _call_ollama
                "top_k":          md.get("top_k", 40),
                "top_p":          md.get("top_p", 0.9),
                "repeat_penalty": md.get("repeat_penalty", 1.1),
                "repeat_last_n":  md.get("repeat_last_n", 64),
            },
        }
        try:
            response = requests.post(
                url, json=payload, timeout=self.timeout, stream=True,
            )
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done", False):
                        return
        except Exception as e:
            yield f"[ERROR: {e}]"

    def generate_stream(
        self,
        request: KernelRequest,
        _audit: dict | None = None,
    ) -> Iterator[str]:
        """Dual-pass with Pass2 streaming. Pass1 is blocking.

        If _audit dict is provided, it is populated with metadata
        after Pass1 completes (before Pass2 tokens start yielding).
        """
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

        intent_type = (request.metadata or {}).get("intent_type", "factual_query")
        route = (request.metadata or {}).get("route", "answer")

        if route in ("abstain", "ask"):
            if _audit is not None:
                _audit["qk_mode"] = "none"
                _audit["intent_type"] = intent_type
            yield from self._call_ollama_stream(prompt)
            return

        # Pass 1: blocking (need full text for Pass2)
        pass1_prompt = self._build_qk_prompt(intent_type, prompt)
        pass1_resp = self._call_ollama(pass1_prompt, metadata=request.metadata)

        if not self.dual_pass:
            if _audit is not None:
                _audit["qk_mode"] = "single_pass"
                _audit["intent_type"] = intent_type
            _t0 = time.time()
            yield from self._call_ollama_stream(pass1_prompt)
            if _audit is not None:
                _audit["pass1_latency_ms"] = int((time.time() - _t0) * 1000)
            return

        # Populate audit after Pass1, before Pass2 streaming
        pass2_endpoint = self.second_endpoint or self.endpoint
        if _audit is not None:
            _audit["qk_mode"] = "pipeline" if self.second_endpoint else "single"
            _audit["intent_type"] = intent_type
            _audit["pass1_latency_ms"] = pass1_resp.latency_ms
            _audit["pass1_endpoint"] = self.endpoint
            _audit["pass2_endpoint"] = pass2_endpoint

        # Pass 2: streaming with reduced num_predict
        user_input = getattr(request, "user_input", "")
        pass2_prompt = (
            f"Original query: {user_input}\n\n"
            f"Draft response:\n{pass1_resp.text}\n\n"
            f"Refine this response for accuracy and clarity."
        )
        yield from self._call_ollama_stream(
            pass2_prompt, pass2_endpoint,
            metadata={"temperature": 0.2, "max_tokens": 256},
        )

    # ── Low-temp generation (V_regen) ────────────────────────────────────────

    def generate_low_temp(
        self,
        prompt: str,
        temperature: float = 0.05,
        max_tokens: int = 50,
    ) -> str:
        url = f"{self.endpoint}/api/chat"
        payload = {
            "model":      self.model_name,
            "messages":   [{"role": "user", "content": prompt}],
            "stream":     False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature":    temperature,
                "num_predict":    max_tokens,
                # cyc_20260425_engine_token_loop_fix — see _call_ollama.
                # generate_low_temp() runs at temperature 0.05 which is
                # even more degeneracy-prone than the main path's 0.2.
                "top_k":          40,
                "top_p":          0.9,
                "repeat_penalty": 1.1,
                "repeat_last_n":  64,
            },
        }
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except Exception as exc:
            return f"[ERROR] {exc}"

    # ── Memory management ────────────────────────────────────────────────────

    def warmup(self) -> bool:
        try:
            resp = requests.post(
                f"{self.endpoint}/api/chat",
                json={"model": self.model_name,
                      "messages": [{"role": "user", "content": "ping"}],
                      "stream": False, "keep_alive": -1},
                timeout=60,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def release_model(self) -> bool:
        try:
            resp = requests.post(
                f"{self.endpoint}/api/chat",
                json={"model": self.model_name,
                      "messages": [{"role": "user", "content": ""}],
                      "stream": False, "keep_alive": 0},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def reload_model(self) -> bool:
        return self.warmup()

    def get_loaded_models(self) -> list[str]:
        try:
            resp = requests.get(f"{self.endpoint}/api/ps", timeout=5)
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            pass
        return []
