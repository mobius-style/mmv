from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .chunker import chunk_text
from .embedder import Embedder
from .vector_index import IndexedChunk, InMemoryVectorIndex

RELEVANCE_THRESHOLD = 0.40   # tunable in Phase 4


@dataclass
class RAGResult:
    chunks: List[IndexedChunk]
    sources: List[str]
    sufficient: bool           # True when at least one chunk clears the threshold


class LocalRAGPipeline:
    """Minimal local RAG pipeline for Möbius MMV.

    Responsibilities (05b_retrieval_policy):
    - Ingest text documents into a vector index at build time.
    - At query time, retrieve top-k chunks and judge sufficiency.
    - Source attribution is mandatory.
    """

    def __init__(self, embedder: Embedder, top_k: int = 5) -> None:
        self._embedder = embedder
        self._index    = InMemoryVectorIndex()
        self._top_k    = top_k

    # ── Ingestion ────────────────────────────────────────────────────────────

    def ingest_text(self, text: str, source: str) -> None:
        """Chunk and embed a raw text string."""
        chunks = chunk_text(text)
        if not chunks:
            return
        embeddings = self._embedder.embed(chunks)
        for chunk, emb in zip(chunks, embeddings):
            self._index.add(IndexedChunk(text=chunk, source=source, embedding=emb))

    def ingest_file(self, path: str | Path) -> None:
        """Read a text file and ingest it."""
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        self.ingest_text(text, source=str(path.name))

    def ingest_directory(self, directory: str | Path, extensions: tuple = (".md", ".txt")) -> None:
        """Ingest all matching files from a directory."""
        directory = Path(directory)
        for ext in extensions:
            for fp in sorted(directory.rglob(f"*{ext}")):
                self.ingest_file(fp)

    @property
    def is_empty(self) -> bool:
        return len(self._index.items) == 0

    # ── Query ────────────────────────────────────────────────────────────────

    def query(self, query_text: str) -> RAGResult:
        """Retrieve top-k chunks for a query and judge sufficiency."""
        if self.is_empty:
            return RAGResult(chunks=[], sources=[], sufficient=False)

        query_emb = self._embedder.embed([query_text])[0]
        hits      = self._index.search(query_emb, top_k=self._top_k)

        # Compute cosine similarity for each hit
        import math
        def cosine(a: List[float], b: List[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na  = math.sqrt(sum(x * x for x in a)) or 1.0
            nb  = math.sqrt(sum(x * x for x in b)) or 1.0
            return dot / (na * nb)

        scored    = [(hit, cosine(query_emb, hit.embedding)) for hit in hits]
        above     = [(hit, score) for hit, score in scored if score >= RELEVANCE_THRESHOLD]
        sources   = list(dict.fromkeys(hit.source for hit, _ in above))

        return RAGResult(
            chunks=    [hit for hit, _ in above],
            sources=   sources,
            sufficient=len(above) > 0,
        )
