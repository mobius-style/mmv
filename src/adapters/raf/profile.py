"""
profile.py — ISM profile retrieval via FAISS KNN search.

Uses the ISM index (data/raf/ism_index.faiss) built by
build_ism_index.py to estimate intent_type and QK parameters
for incoming queries.

Embedding: intfloat/multilingual-e5-large (device=cuda:0, Principle G解除（壁打き完走済み）)
Search: KNN with K=3, majority vote on intent_type

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Optional

from .schema import ISMState

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent.parent


class ISMProfile:
    DEFAULT_INDEX  = str(ROOT / "data" / "raf" / "ism_index.faiss")
    DEFAULT_CHUNKS = str(ROOT / "data" / "raf" / "ism_chunks.jsonl")
    MODEL_NAME     = "intfloat/multilingual-e5-large"
    KNN_K          = 3
    CONFIDENCE_THRESHOLD = 0.72

    def __init__(
        self,
        index_path:  str = "",
        chunks_path: str = "",
    ):
        self._index_path  = index_path or self.DEFAULT_INDEX
        self._chunks_path = chunks_path or self.DEFAULT_CHUNKS
        self._index  = None
        self._chunks = []
        self._model  = None
        self._loaded = False

    def load(self) -> bool:
        try:
            import faiss
            import numpy as np
            from sentence_transformers import SentenceTransformer

            if not Path(self._index_path).exists():
                logger.warning(f"[ISMProfile] Index not found: {self._index_path}")
                return False

            self._index = faiss.read_index(self._index_path)
            self._chunks = []
            with open(self._chunks_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._chunks.append(json.loads(line))

            self._model = SentenceTransformer(self.MODEL_NAME, device="cuda:0")
            self._loaded = True
            logger.info(f"[ISMProfile] Loaded: {self._index.ntotal} vectors, "
                        f"{len(self._chunks)} chunks")
            return True
        except Exception as e:
            logger.warning(f"[ISMProfile] Load failed: {e}")
            return False

    def is_available(self) -> bool:
        return self._loaded and self._index is not None and len(self._chunks) > 0

    def retrieve(self, query: str, context: str = "") -> ISMState:
        """
        KNN search for intent_type estimation.
        Uses "query: " prefix for multilingual-e5-large.
        Returns ISMState with majority-voted fields.
        """
        if not self.is_available():
            return ISMState()

        import numpy as np

        text = f"query: {query}"
        vec = self._model.encode(
            [text], convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False,
        ).astype(np.float32)

        k = min(self.KNN_K, self._index.ntotal)
        scores, indices = self._index.search(vec, k)

        neighbors = []
        for i, idx in enumerate(indices[0]):
            if 0 <= idx < len(self._chunks):
                chunk = self._chunks[idx]
                chunk["_score"] = float(scores[0][i])
                neighbors.append(chunk)

        if not neighbors:
            return ISMState()

        # Majority vote
        def _vote(field: str, default: str) -> str:
            vals = [n.get(field, default) for n in neighbors]
            c = Counter(vals)
            return c.most_common(1)[0][0]

        avg_score = sum(n["_score"] for n in neighbors) / len(neighbors)
        top_score = neighbors[0]["_score"]

        intent = _vote("intent_type", "factual_query")
        formal = _vote("formal_type", "what")
        qk_ent = _vote("qk_entitlement", "answerable")
        qk_tvs = _vote("qk_tvs_estimate", "low")
        qk_mkr = _vote("qk_mkr_risk", "low")
        halfstep = _vote("qk_halfstep_type", "none")
        wiki = sum(1 for n in neighbors if n.get("wiki_lookup", True)) > len(neighbors) // 2
        conv = sum(1 for n in neighbors if n.get("conv_override", False)) > len(neighbors) // 2

        return ISMState(
            intent_type=intent,
            formal_type=formal,
            response_type="direct_answer",
            halfstep_type=halfstep if halfstep != "none" else None,
            wiki_lookup=wiki,
            explanation_needed=True,
            conv_override=conv,
            qk_entitlement=qk_ent,
            qk_tvs_estimate=qk_tvs,
            confidence=round(top_score, 4),
            source="ism_knn",
            neighbor_count=len(neighbors),
        )
