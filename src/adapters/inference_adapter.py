from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator


@dataclass
class KernelRequest:
    user_input: str
    prompt: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterResponse:
    text: str
    model_used: str
    latency_ms: int
    raw: Dict[str, Any] = field(default_factory=dict)


class InferenceAdapter(ABC):
    @abstractmethod
    def generate(self, request: KernelRequest) -> AdapterResponse:
        raise NotImplementedError

    @abstractmethod
    def stream(self, request: KernelRequest) -> Iterator[str]:
        raise NotImplementedError
