"""
context_processor.py — Background context processing for Box M Layer 1/2.

Daemon thread that periodically:
  1. Picks up unprocessed Layer 0 turns
  2. Filters noise (greetings, acknowledgments)
  3. Embeds with ME5 (CPU, "passage: " prefix)
  4. Promotes to Layer 1 in SQLite
  5. Maintains Layer 2 (active context, most recent N)

The ME5 model instance is shared from Box A (no double-load).
FAISS context index is separate from the capsule FAISS index.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import atexit
import logging
import re
import threading
import time
from pathlib import Path
from typing import Optional

import faiss
import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
ME5_DIM = 1024
CONTEXT_FAISS_FILE = "data/memory/context_index_me5.faiss"
PROCESS_INTERVAL_S = 30
ACTIVE_CONTEXT_N = 5
CONTEXT_SEARCH_THRESHOLD = 0.35

# Noise patterns — short greetings, acknowledgments, errors
# Pure regex, no LLM.
NOISE_PATTERN = re.compile(
    # English
    r"^(hi|hello|hey|ok|okay|sure|yes|no|yep|nope|bye|goodbye"
    r"|thanks|thank you|thx|ty|cool|nice|great|good|fine"
    r"|got it|i see|understood|right|alright|sounds good"
    r"|lol|haha|hm+|oh|ah|uh|wow|oops|sorry|please"
    r"|ERROR:.*)$"
    # Japanese
    r"|^(はい|うん|ええ|いいえ|いや|ありがとう|ありがとうございます"
    r"|了解|了解です|わかりました|分かりました|なるほど"
    r"|おはよう|こんにちは|こんばんは|さようなら|お疲れ様"
    r"|すみません|ごめんなさい|大丈夫|OK|おっけー)$",
    re.IGNORECASE,
)


class ContextProcessor:
    """Background daemon for Box M context vectorization.

    Shares the ME5 SentenceTransformer instance from Box A or Box W
    to avoid double-loading ~1.2 GB into RAM.
    """

    def __init__(
        self,
        memory_indexer,
        me5_model=None,
        faiss_path: str = CONTEXT_FAISS_FILE,
    ):
        self._indexer = memory_indexer
        self._me5 = me5_model  # Shared SentenceTransformer instance
        self._faiss_path = Path(faiss_path)
        self._context_index: Optional[faiss.Index] = None
        self._id_map: list[str] = []  # FAISS row → capsule_id
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._started = False

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background processing daemon."""
        if self._started:
            return
        self._faiss_path.parent.mkdir(parents=True, exist_ok=True)
        self._context_index = self._load_or_create_faiss()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ContextProcessor",
        )
        self._started = True
        self._thread.start()
        atexit.register(self.stop)
        logger.info("[ContextProcessor] Started (daemon thread)")

    def stop(self) -> None:
        """Stop the background daemon and save index."""
        if not self._started:
            return
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._save_faiss()
        self._started = False
        logger.info("[ContextProcessor] Stopped")

    # ── Public search API ────────────────────────────────────────────────

    def search_context(
        self, query: str, top_k: int = 3, threshold: float = CONTEXT_SEARCH_THRESHOLD,
    ) -> list[dict]:
        """Search Layer 1+2 context by semantic similarity.

        Args:
            query: Search query (will be prefixed with "query: " for ME5)
            top_k: Max results
            threshold: Minimum cosine similarity

        Returns:
            List of {"capsule_id", "text", "score", "layer"} dicts
        """
        if self._me5 is None or self._context_index is None:
            return []
        with self._lock:
            if self._context_index.ntotal == 0:
                return []
            vec = self._embed_query(query)
            scores, indices = self._context_index.search(
                vec.reshape(1, -1),
                min(top_k * 2, self._context_index.ntotal),
            )
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or score < threshold:
                continue
            if idx >= len(self._id_map):
                continue
            capsule_id = self._id_map[idx]
            # Fetch text from SQLite
            row = self._indexer._db_conn.execute(
                "SELECT memory_text, layer FROM capsules WHERE capsule_id=?",
                (capsule_id,),
            ).fetchone()
            if row:
                results.append({
                    "capsule_id": capsule_id,
                    "text": row[0],
                    "score": float(score),
                    "layer": row[1],
                })
            if len(results) >= top_k:
                break
        return results

    @staticmethod
    def is_noise(text: str) -> bool:
        """Check if text is noise (greeting, acknowledgment, error)."""
        stripped = text.strip()
        if len(stripped) == 0:
            return True
        # Word count: very short English or very short CJK
        words = stripped.split()
        cjk_chars = sum(1 for c in stripped if '\u3000' <= c <= '\u9fff')
        effective_len = len(words) + cjk_chars if cjk_chars else len(words)
        if effective_len <= 2 and bool(NOISE_PATTERN.match(stripped)):
            return True
        if bool(NOISE_PATTERN.match(stripped)):
            return True
        return False

    # ── Background loop ──────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Main daemon loop: process Layer 0 → Layer 1, maintain Layer 2."""
        while not self._stop_event.is_set():
            try:
                self._process_batch()
            except Exception as e:
                logger.warning(f"[ContextProcessor] Error: {e}")
            self._stop_event.wait(PROCESS_INTERVAL_S)

    def _process_batch(self) -> None:
        """Process unprocessed Layer 0 turns."""
        if self._me5 is None or self._indexer is None:
            return
        if not self._indexer._open:
            return

        unprocessed = self._indexer.get_unprocessed_turns(limit=20)
        if not unprocessed:
            return

        promoted = []
        for turn in unprocessed:
            text = turn["memory_text"]
            if self.is_noise(text):
                # Mark as processed (layer -1 = noise, skip)
                with self._lock:
                    self._indexer._db_conn.execute(
                        "UPDATE capsules SET layer=-1 WHERE capsule_id=?",
                        (turn["capsule_id"],),
                    )
                continue

            # Embed with ME5 (passage prefix for stored content)
            vec = self._embed_passage(text)

            # Add to context FAISS index
            with self._lock:
                self._context_index.add(vec.reshape(1, -1))
                self._id_map.append(turn["capsule_id"])

            # Promote in SQLite
            self._indexer.promote_to_layer1(turn["capsule_id"], vec)
            promoted.append(turn["capsule_id"])

        if promoted:
            self._indexer._db_conn.commit()
            logger.debug(f"[ContextProcessor] Promoted {len(promoted)} turns to Layer 1")

        # Update active context (most recent N from Layer 1+2)
        rows = self._indexer._db_conn.execute(
            "SELECT capsule_id FROM capsules WHERE layer IN (1,2) "
            "ORDER BY created_at DESC LIMIT ?",
            (ACTIVE_CONTEXT_N,),
        ).fetchall()
        if rows:
            active_ids = [r[0] for r in rows]
            self._indexer.set_active_context(active_ids)

    # ── Embedding helpers ────────────────────────────────────────────────

    def _embed_query(self, text: str) -> np.ndarray:
        """Embed with ME5 query prefix."""
        return self._me5.encode(
            "query: " + text,
            normalize_embeddings=True,
        ).astype("float32")

    def _embed_passage(self, text: str) -> np.ndarray:
        """Embed with ME5 passage prefix."""
        return self._me5.encode(
            "passage: " + text,
            normalize_embeddings=True,
        ).astype("float32")

    # ── FAISS management ─────────────────────────────────────────────────

    def _load_or_create_faiss(self) -> faiss.Index:
        if self._faiss_path.exists():
            idx = faiss.read_index(str(self._faiss_path))
            # Rebuild id_map from SQLite
            if self._indexer._open:
                rows = self._indexer._db_conn.execute(
                    "SELECT capsule_id FROM capsules WHERE layer IN (1,2) "
                    "ORDER BY rowid ASC"
                ).fetchall()
                self._id_map = [r[0] for r in rows]
            logger.info(f"[ContextProcessor] Context FAISS loaded: {idx.ntotal} vectors")
        else:
            idx = faiss.IndexFlatIP(ME5_DIM)
            logger.info("[ContextProcessor] Context FAISS created (new)")
        return idx

    def _save_faiss(self) -> None:
        if self._context_index is not None:
            self._faiss_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._context_index, str(self._faiss_path))
            logger.debug(f"[ContextProcessor] Context FAISS saved")
