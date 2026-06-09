from __future__ import annotations

import time
from typing import Iterator
import requests

from .inference_adapter import AdapterResponse, InferenceAdapter, KernelRequest
from ..kernel.errors import VllmConnectionError


class VllmAdapter(InferenceAdapter):
    def __init__(self, endpoint: str, model_name: str = "Phi-4-mini-flash-reasoning", timeout: int = 60) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

    def generate(self, request: KernelRequest) -> AdapterResponse:
        url = f"{self.endpoint}/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.metadata.get("temperature", 0.2),
        }
        started = time.time()
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise VllmConnectionError(str(exc)) from exc
        latency_ms = int((time.time() - started) * 1000)
        text = data["choices"][0]["message"]["content"].strip()
        return AdapterResponse(text=text, model_used=self.model_name, latency_ms=latency_ms, raw=data)

    def stream(self, request: KernelRequest) -> Iterator[str]:
        # Minimal scaffold only; production SSE handling can be added later.
        yield self.generate(request).text
