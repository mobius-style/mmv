from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class RetrievalHit:
    text: str
    source: str
    score: float


class RetrievalAdapter(ABC):
    @abstractmethod
    def search(self, query: str, top_k: int = 4) -> List[RetrievalHit]:
        raise NotImplementedError
