from __future__ import annotations

from dataclasses import dataclass
from typing import List
import math


@dataclass
class IndexedChunk:
    text: str
    source: str
    embedding: List[float]


class InMemoryVectorIndex:
    def __init__(self) -> None:
        self.items: List[IndexedChunk] = []

    def add(self, item: IndexedChunk) -> None:
        self.items.append(item)

    def search(self, query_embedding: List[float], top_k: int = 4) -> List[IndexedChunk]:
        def cosine(a: List[float], b: List[float]) -> float:
            dot = sum(x*y for x, y in zip(a, b))
            na = math.sqrt(sum(x*x for x in a)) or 1.0
            nb = math.sqrt(sum(x*x for x in b)) or 1.0
            return dot / (na * nb)
        ranked = sorted(self.items, key=lambda item: cosine(query_embedding, item.embedding), reverse=True)
        return ranked[:top_k]
