#!/usr/bin/env python3
"""
memory_indexer.py — MOBIUS MMV Phase E: Memory Indexer
src/memory/memory_indexer.py

Embed MemoryCapsule and store in FAISS / SQLite.
Reuses the FAISS interface from Phase C Box A's custom_rag_adapter.py.

Phase E E.1 implementation.

Design principles:
  - embedding: intfloat/multilingual-e5-large (1024 dimensions, device auto-select)
  - FAISS: IndexFlatIP (inner product = cosine similarity)
  - SQLite: persistent capsule metadata storage
  - Interface designed for future replacement with a dedicated Vector DB

Success criteria (spec §8):
  - embedding + FAISS write < 100ms

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : phase_e_memory_spec.docx §6, §8
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
EMBEDDING_MODEL  = "intfloat/multilingual-e5-large"
EMBEDDING_DIM    = 1024
FAISS_INDEX_FILE = "data/memory/capsule_index.faiss"
SQLITE_DB_FILE   = "data/memory/capsules.db"
LATENCY_TARGET_MS = 1500  # ME5-large CPU budget for capsule insertion


def _select_embedding_device() -> str:
    requested = os.environ.get("MMV_EMBEDDING_DEVICE", "auto").strip().lower()
    if requested == "cpu":
        return "cpu"
    if requested.startswith("cuda"):
        try:
            import torch
            if torch.cuda.is_available():
                return requested
            logger.warning(
                "MMV_EMBEDDING_DEVICE=%s requested but CUDA is unavailable; using cpu.",
                requested,
            )
        except Exception as exc:
            logger.warning("Could not inspect CUDA availability: %s; using cpu.", exc)
        return "cpu"
    if requested != "auto":
        logger.warning(
            "Unknown MMV_EMBEDDING_DEVICE=%s; expected auto/cpu/cuda. Using auto.",
            requested,
        )
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


class MemoryIndexer:
    """
    Embed MemoryCapsule and store in FAISS + SQLite.

    Usage:
        indexer = MemoryIndexer()
        indexer.open()

        # Store
        capsule = generate_capsule(audit, ...)
        if capsule:
            indexer.add(capsule)

        # Search
        results = indexer.search("Box B sufficiency threshold", top_k=5)

        indexer.close()
    """

    def __init__(
        self,
        index_path: str = FAISS_INDEX_FILE,
        db_path:    str = SQLITE_DB_FILE,
    ):
        self.index_path = Path(index_path)
        self.db_path    = Path(db_path)
        self._encoder   = None
        self._index     = None
        self._db_conn   = None
        self._open      = False
        self._lock      = threading.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the indexer. Initialize encoder / FAISS / SQLite."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize encoder
        self._encoder = self._load_encoder()

        # FAISS index
        self._index = self._load_or_create_faiss()

        # SQLite
        self._db_conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_db()

        self._open = True
        logger.info(
            f"[MemoryIndexer] Opened. "
            f"index={self.index_path} capsules={self._index.ntotal}"
        )

    def close(self) -> None:
        """Close the indexer. Save FAISS index."""
        if self._index is not None:
            self._save_faiss()
        if self._db_conn is not None:
            self._db_conn.close()
        self._open = False
        logger.info("[MemoryIndexer] Closed.")

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, capsule) -> float:
        """
        Embed a MemoryCapsule and add it to FAISS + SQLite.

        Returns:
            Processing time (milliseconds)

        Raises:
            RuntimeError: If indexer is not open
        """
        if not self._open:
            raise RuntimeError("MemoryIndexer is not open. Call open() first.")

        t0 = time.time()

        # embedding
        vec = self._embed(capsule.memory_text)
        capsule.embedding_vector = vec.tolist()

        with self._lock:
            # Add to FAISS
            self._index.add(vec.reshape(1, -1))
            faiss_id = self._index.ntotal - 1

            # Save to SQLite
            self._db_conn.execute(
                """INSERT OR REPLACE INTO capsules
                   (capsule_id, faiss_id, session_id, memory_type, memory_text,
                    salience_score, ttl, audit_ref, created_at, capsule_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    capsule.capsule_id,
                    faiss_id,
                    capsule.session_id,
                    capsule.memory_type,
                    capsule.memory_text,
                    capsule.salience_score,
                    capsule.ttl,
                    capsule.audit_ref,
                    capsule.created_at,
                    json.dumps(capsule.to_dict(), ensure_ascii=False),
                )
            )
            self._db_conn.commit()

        elapsed_ms = (time.time() - t0) * 1000
        if elapsed_ms > LATENCY_TARGET_MS:
            logger.warning(
                f"[MemoryIndexer] add() latency={elapsed_ms:.1f}ms > {LATENCY_TARGET_MS}ms"
            )
        else:
            logger.debug(f"[MemoryIndexer] add() latency={elapsed_ms:.1f}ms")

        return elapsed_ms

    def search(
        self,
        query:      str,
        top_k:      int = 5,
        memory_type: Optional[str] = None,
        min_salience: float = 0.0,
    ) -> list[dict]:
        """
        Search for MemoryCapsules similar to the query.

        Args:
            query       : Search query string
            top_k       : Number of results to return
            memory_type : Filter (None=all)
            min_salience: Minimum salience_score

        Returns:
            List of Capsule dicts (descending by score)
        """
        if not self._open:
            raise RuntimeError("MemoryIndexer is not open.")
        if self._index.ntotal == 0:
            return []

        vec = self._embed(query).reshape(1, -1)
        scores, indices = self._index.search(vec, min(top_k * 3, self._index.ntotal))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            row = self._db_conn.execute(
                "SELECT capsule_json, salience_score, memory_type, ttl "
                "FROM capsules WHERE faiss_id=?", (int(idx),)
            ).fetchone()
            if row is None:
                continue
            capsule_json, salience, mtype, ttl = row

            # Filter
            if memory_type and mtype != memory_type:
                continue
            if salience < min_salience:
                continue
            # TTL check
            if ttl and datetime.fromisoformat(ttl) < datetime.now(timezone.utc):
                continue

            capsule_dict = json.loads(capsule_json)
            capsule_dict["_search_score"] = float(score)
            results.append(capsule_dict)

            if len(results) >= top_k:
                break

        return results

    def count(self) -> int:
        """Return the number of stored Capsules"""
        if not self._open:
            return 0
        return self._index.ntotal

    def stats(self) -> dict:
        """Return statistics"""
        if not self._open:
            return {"open": False}
        row = self._db_conn.execute(
            "SELECT COUNT(*), AVG(salience_score) FROM capsules"
        ).fetchone()
        by_type = self._db_conn.execute(
            "SELECT memory_type, COUNT(*) FROM capsules GROUP BY memory_type"
        ).fetchall()
        return {
            "open":          True,
            "total_capsules": row[0] or 0,
            "avg_salience":   round(row[1] or 0, 3),
            "by_type":        {t: n for t, n in by_type},
            "faiss_ntotal":  self._index.ntotal,
        }

    # ── Internal methods ──────────────────────────────────────────────────────

    def _load_encoder(self):
        """Load sentence-transformers encoder on the configured device"""
        try:
            from sentence_transformers import SentenceTransformer
            device = _select_embedding_device()
            try:
                encoder = SentenceTransformer(EMBEDDING_MODEL, device=device)
            except RuntimeError as e:
                # CUDA OOM / device contention (e.g. Ollama holding the GPU):
                # degrade to CPU rather than crash the runtime.
                if device != "cpu":
                    logger.warning(
                        f"[MemoryIndexer] encoder load on {device} failed "
                        f"({type(e).__name__}: {e}); falling back to CPU."
                    )
                    encoder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
                else:
                    raise
            logger.info(f"[MemoryIndexer] Encoder loaded: {EMBEDDING_MODEL} (device={device})")
            return encoder
        except ImportError:
            logger.warning("[MemoryIndexer] sentence-transformers not available. Using stub encoder.")
            return None

    def _embed(self, text: str) -> np.ndarray:
        """Convert text to a 1024-dimensional ME5 vector"""
        if self._encoder is None:
            # stub: random vector (for testing)
            vec = np.random.default_rng(abs(hash(text)) % (2**32)).random(EMBEDDING_DIM).astype("float32")
        else:
            vec = self._encoder.encode(text, normalize_embeddings=True)
        return vec.astype("float32")

    def _load_or_create_faiss(self):
        """Load or create a new FAISS index"""
        import faiss
        if self.index_path.exists():
            idx = faiss.read_index(str(self.index_path))
            if idx.d != EMBEDDING_DIM:
                logger.warning(
                    f"[MemoryIndexer] FAISS dim mismatch: d={idx.d}, "
                    f"expected={EMBEDDING_DIM}. Creating empty ME5 index; "
                    f"run scripts/rebuild_faiss.py to rebuild from SQLite."
                )
                idx = faiss.IndexFlatIP(EMBEDDING_DIM)
            else:
                logger.info(f"[MemoryIndexer] FAISS loaded: {idx.ntotal} vectors")
        else:
            idx = faiss.IndexFlatIP(EMBEDDING_DIM)  # Inner product (normalized = cosine similarity)
            logger.info("[MemoryIndexer] FAISS created (new)")
        return idx

    def _save_faiss(self) -> None:
        """Save the FAISS index to file"""
        import faiss
        faiss.write_index(self._index, str(self.index_path))
        logger.debug(f"[MemoryIndexer] FAISS saved: {self.index_path}")

    def _init_db(self) -> None:
        """Initialize SQLite tables and migrate schema if needed."""
        self._db_conn.execute("""
            CREATE TABLE IF NOT EXISTS capsules (
                capsule_id    TEXT PRIMARY KEY,
                faiss_id      INTEGER,
                session_id    TEXT,
                memory_type   TEXT,
                memory_text   TEXT,
                salience_score REAL,
                ttl           TEXT,
                audit_ref     TEXT,
                created_at    TEXT,
                capsule_json  TEXT
            )
        """)
        self._db_conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_type ON capsules(memory_type)"
        )
        self._db_conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session ON capsules(session_id)"
        )
        # ── Layer column migration (Phase M.2) ──────────────────────
        # Layer 0: Raw session turns (legacy capsules)
        # Layer 1: Curated context (ME5-vectorized, searchable)
        # Layer 2: Active context (recent N turns, highest priority)
        try:
            self._db_conn.execute(
                "ALTER TABLE capsules ADD COLUMN layer INTEGER DEFAULT 0"
            )
            self._db_conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_layer ON capsules(layer)"
            )
            logger.info("[MemoryIndexer] Migrated: added 'layer' column")
        except sqlite3.OperationalError:
            pass  # Column already exists
        self._db_conn.commit()

    # ── Layer-aware convenience methods ──────────────────────────────────

    def add_turn(
        self, text: str, role: str, session_id: str = "",
        timestamp: Optional[str] = None,
    ) -> int:
        """Insert a raw session turn as Layer 0.

        Returns the SQLite rowid.
        """
        if not self._open:
            raise RuntimeError("MemoryIndexer is not open.")
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        turn_id = f"turn_{int(time.time()*1000)}"
        with self._lock:
            self._db_conn.execute(
                """INSERT INTO capsules
                   (capsule_id, faiss_id, session_id, memory_type, memory_text,
                    salience_score, ttl, audit_ref, created_at, capsule_json, layer)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (turn_id, -1, session_id, "turn", text,
                 0.0, None, None, ts,
                 json.dumps({"role": role, "text": text}, ensure_ascii=False),
                 0),
            )
            self._db_conn.commit()
        return turn_id

    def promote_to_layer1(
        self, turn_id: str, embedding: np.ndarray,
    ) -> None:
        """Promote a Layer 0 turn to Layer 1 (ME5-vectorized).

        The embedding is added to the context FAISS index managed by
        ContextProcessor (not the capsule FAISS index).  Here we only
        update the SQLite layer flag.
        """
        if not self._open:
            return
        with self._lock:
            self._db_conn.execute(
                "UPDATE capsules SET layer=1 WHERE capsule_id=?", (turn_id,)
            )
            self._db_conn.commit()

    def set_active_context(self, turn_ids: list[str]) -> None:
        """Set turns as Layer 2 (active context, most recent N)."""
        if not self._open:
            return
        with self._lock:
            # Demote previous Layer 2 back to Layer 1
            self._db_conn.execute(
                "UPDATE capsules SET layer=1 WHERE layer=2"
            )
            if turn_ids:
                placeholders = ",".join("?" * len(turn_ids))
                self._db_conn.execute(
                    f"UPDATE capsules SET layer=2 WHERE capsule_id IN ({placeholders})",
                    turn_ids,
                )
            self._db_conn.commit()

    def get_active_context(self, n: int = 5) -> list[dict]:
        """Return the most recent N Layer 2 (active context) capsules."""
        if not self._open:
            return []
        rows = self._db_conn.execute(
            "SELECT capsule_id, memory_text, capsule_json, created_at "
            "FROM capsules WHERE layer=2 ORDER BY created_at DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [
            {"capsule_id": r[0], "memory_text": r[1],
             "data": json.loads(r[2]) if r[2] else {}, "created_at": r[3]}
            for r in rows
        ]

    def get_unprocessed_turns(self, limit: int = 50) -> list[dict]:
        """Return Layer 0 turns that have not been promoted yet."""
        if not self._open:
            return []
        rows = self._db_conn.execute(
            "SELECT capsule_id, memory_text, capsule_json, created_at "
            "FROM capsules WHERE layer=0 AND memory_type='turn' "
            "ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"capsule_id": r[0], "memory_text": r[1],
             "data": json.loads(r[2]) if r[2] else {}, "created_at": r[3]}
            for r in rows
        ]
