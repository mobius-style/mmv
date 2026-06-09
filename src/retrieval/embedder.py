from __future__ import annotations

from abc import ABC, abstractmethod
import os
from typing import List


class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class SentenceTransformerEmbedder(Embedder):
    """Lightweight embedding using sentence-transformers.

    Uses intfloat/multilingual-e5-large by default so MMV-owned vector
    surfaces share one multilingual embedding space.
    """

    DEFAULT_MODEL = "intfloat/multilingual-e5-large"

    @staticmethod
    def _select_device() -> str:
        requested = os.environ.get("MMV_EMBEDDING_DEVICE", "auto").strip().lower()
        if requested == "cpu":
            return "cpu"
        if requested.startswith("cuda"):
            try:
                import torch
                return requested if torch.cuda.is_available() else "cpu"
            except Exception:
                return "cpu"
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def __init__(self, model_name: str = DEFAULT_MODEL, device: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required. Run: pip install sentence-transformers"
            ) from e
        self._model = SentenceTransformer(model_name, device=device or self._select_device())

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vectors]
