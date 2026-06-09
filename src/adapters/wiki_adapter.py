#!/usr/bin/env python3
"""
wiki_adapter.py — MOBIUS MMV Phase C: Box W Retrieval Adapter
src/adapters/wiki_adapter.py

Wikipedia FAISS (IndexIVFPQ) search adapter.

Design principles (phase_c_spec_v2_2.docx §1):
  Principle F  Index file scheme: wiki_index_ivfpq_me5.faiss is the source of truth
  Principle G  CPU/GPU separation: FAISS search is CPU. Query embedding uses
               MMV_EMBEDDING_DEVICE (auto/cpu/cuda), defaulting to CUDA when
               available.

Technical specifications:
  Index             : Wiki/wiki_index_ivfpq_me5.faiss (IndexIVFPQ, nlist=4096, m=64, nbits=8, INNER_PRODUCT)
  Chunk access      : indexed_gzip + line offset array
  Offset array      : Wiki/line_offsets.npy (~44 MB, built once on first run)
  Manifest          : Wiki/wiki_manifest.json
  Embedding model   : intfloat/multilingual-e5-large (DIM=1024, cross-lingual)
  Vectors           : 5,458,524
  RAM resident      : ~0.4 GB (index) + ~1.2 GB (model) + ~44 MB (offsets) ≈ 1.6 GB
  nprobe            : 32 (0.8% of nlist=4096)
  Query prefix      : "query: " (required by E5 architecture)

Chunk access method (indexed_gzip):
  Hold uncompressed byte offsets in a numpy array -> seek with indexed_gzip -> readline.
  Dependency: pip install indexed-gzip

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later (code) | CC BY-SA 4.0 (wiki_chunks derivatives)
Spec   : phase_c_spec_v2_2.docx §3, §7, §11
"""

from __future__ import annotations

import gzip
import html
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# -- Constants ---------------------------------------------------------------
MODEL_NAME    = "intfloat/multilingual-e5-large"
DIM           = 1024
NPROBE        = 32      # 0.8% of nlist=4096
QUERY_PREFIX  = "query: "  # Required by E5 architecture
DEFAULT_TOP_K = 5
MAX_TOP_K     = 20
# indexed_gzip seek point spacing (uncompressed bytes)
# Smaller = faster seek but larger .gzidx. 64 MB is a practical middle ground.
IGZIP_SPACING = 64 << 20  # 64 MB


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

# -- Type definitions (per 08_api_types.docx §9) ----------------------------

@dataclass
class Source:
    """08_api_types.docx §9 Source type"""
    source_type:     str           # "local_rag" | "web_search"
    label:           str           # Wikipedia article title
    uri:             str           # Wikipedia article URL (CC BY-SA 4.0 attribution)
    chunk_index:     Optional[int] = None
    retrieved_at:    str           = ""
    relevance_score: Optional[float] = None

    def __post_init__(self):
        if not self.retrieved_at:
            self.retrieved_at = datetime.now(timezone.utc).isoformat()


@dataclass
class RetrievalResult:
    """08_api_types.docx §9 RetrievalResult type"""
    sources:   List[Source]
    outcome:   str           # "success" | "partial" | "failed"
    synthesis: str           # Raw concatenation of chunk texts (EAL handles synthesis)


# -- Base class --------------------------------------------------------------

class RetrievalAdapter:
    """
    RetrievalAdapter base class (inline definition from src/adapters/base.py).
    In production, replace with: from mobius.retrieval.base import RetrievalAdapter
    """
    def retrieve(self, query: str, top_k: int = DEFAULT_TOP_K) -> RetrievalResult:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError

    def get_sufficiency_score(self, result: RetrievalResult) -> float:
        raise NotImplementedError


# -- Chunk store (indexed_gzip + numpy offset array) -------------------------

class _GzChunkStore:
    """
    Chunk store providing random access to wiki_chunks_clean.jsonl.gz.

    Approach:
      1. line_offsets.npy: uncompressed byte offset for each line (5.5M x 8B ~ 44 MB)
      2. indexed_gzip.IndexedGzipFile: random seek into uncompressed stream
      3. .gzidx: internal igzip seek points (~several MB, auto-managed)

    Complexity of get(rowids):
      - Offset lookup: O(1) per rowid (numpy array indexing)
      - igzip seek: O(1) amortized (seek point spacing <= 64 MB)
      - readline: O(chunk_size)

    Building (build_offsets):
      Scans gz from the beginning once, recording the uncompressed offset for each line.
      Time required: ~1-2 min (5.5M lines). Disk consumption: ~44 MB.
    """

    def __init__(self, chunks_gz_path: Path, offsets_path: Path):
        self.chunks_gz_path = chunks_gz_path
        self.offsets_path   = offsets_path
        self._offsets: Optional[np.ndarray] = None  # int64, shape (N,)
        self._igzip_path: Path = offsets_path.with_suffix(".gzidx")

    # -- Building -------------------------------------------------------------

    def is_ready(self) -> bool:
        """Returns True if the offset array exists and is loadable"""
        return self.offsets_path.exists() and self.offsets_path.stat().st_size > 0

    def build_offsets(self) -> int:
        """
        Scan gz from the beginning, record the uncompressed byte offset for each line,
        and save as line_offsets.npy.

        Returns:
            Number of lines recorded (should match FAISS total vector count)
        """
        if not self.chunks_gz_path.exists():
            raise FileNotFoundError(f"chunk gz not found: {self.chunks_gz_path}")

        logger.info(
            "[GzChunkStore] Building line_offsets.npy from gz. "
            "This takes ~5 min (~176 MB)..."
        )
        t0 = time.time()

        offsets: list[int] = []
        pos = 0  # Current position in the uncompressed stream (bytes)

        with gzip.open(self.chunks_gz_path, "rb") as f:
            while True:
                offsets.append(pos)
                line = f.readline()
                if not line:
                    offsets.pop()   # Exclude EOF marker
                    break
                pos += len(line)
                if len(offsets) % 1_000_000 == 0:
                    elapsed = time.time() - t0
                    logger.info(f"  {len(offsets):,} lines ... {elapsed:.0f}s")

        arr = np.array(offsets, dtype=np.int64)
        np.save(self.offsets_path, arr)

        elapsed = time.time() - t0
        logger.info(
            f"[GzChunkStore] Done. {len(arr):,} lines in {elapsed:.0f}s "
            f"→ {self.offsets_path} ({arr.nbytes / 1e6:.0f} MB)"
        )
        return len(arr)

    # -- Startup --------------------------------------------------------------

    def open(self):
        """
        Load the offset array into RAM.
        If not yet built, automatically runs build_offsets().
        """
        if not self.is_ready():
            logger.warning(
                "[GzChunkStore] line_offsets.npy not found. "
                "Building (one-time, ~5 min)..."
            )
            self.build_offsets()

        logger.info(f"  Loading offsets: {self.offsets_path} ...")
        self._offsets = np.load(self.offsets_path)
        logger.info(f"  Offsets loaded: {len(self._offsets):,} lines, "
                    f"{self._offsets.nbytes / 1e6:.0f} MB in RAM")

    def close(self):
        self._offsets = None

    # -- Retrieval ------------------------------------------------------------

    def get(self, rowids: list[int]) -> list[dict]:
        """
        Retrieve chunks from FAISS vector IDs (= gz line numbers).

        Multiple rowids are sorted by offset in ascending order to minimize
        seek operations.

        Args:
            rowids: List of index values returned by FAISS search() (negative values already excluded)
        Returns:
            List of chunk dictionaries
        """
        if self._offsets is None:
            raise RuntimeError("GzChunkStore not opened. Call open() first.")

        n_total = len(self._offsets)
        # Keep only valid rowids (warn and skip out-of-range ones)
        valid = []
        for rid in rowids:
            if 0 <= rid < n_total:
                valid.append(rid)
            else:
                logger.warning(f"[GzChunkStore] rowid={rid} out of range "
                               f"(max={n_total-1}). Skipping.")
        if not valid:
            return []

        # Sort by offset in ascending order (minimize seeks)
        sorted_rids = sorted(valid, key=lambda r: self._offsets[r])

        try:
            import indexed_gzip as igzip
        except ImportError:
            raise ImportError(
                "indexed_gzip not found.\n"
                "pip install indexed-gzip --break-system-packages"
            )

        results: dict[int, dict] = {}
        idx_file = str(self._igzip_path) if self._igzip_path.exists() else None

        with igzip.IndexedGzipFile(
            str(self.chunks_gz_path),
            index_file=idx_file,
            spacing=IGZIP_SPACING,
        ) as f:
            for rid in sorted_rids:
                offset = int(self._offsets[rid])
                f.seek(offset)
                raw = f.readline()
                if not raw:
                    logger.warning(f"[GzChunkStore] rowid={rid} readline empty. Skipping.")
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8", errors="ignore"))
                except json.JSONDecodeError as e:
                    logger.warning(f"[GzChunkStore] rowid={rid} JSON error: {e}. Skipping.")
                    continue
                results[rid] = {
                    "rowid":       rid,
                    "title":       obj.get("title", ""),
                    "url":         obj.get("url", ""),
                    "text":        obj.get("text", ""),
                    "chunk_index": obj.get("chunk_index", 0),
                    "license":     obj.get("license", "CC BY-SA 4.0"),
                }

            # Save seek point index after first run (speeds up subsequent seeks)
            if not self._igzip_path.exists():
                try:
                    f.export_index(str(self._igzip_path))
                    logger.info(f"  igzip index saved: {self._igzip_path}")
                except Exception as e:
                    logger.warning(f"  igzip index save failed (non-fatal): {e}")

        # Return in original rowid order
        return [results[r] for r in valid if r in results]


# -- WikiAdapter -------------------------------------------------------------

class WikiAdapter(RetrievalAdapter):
    """
    MOBIUS MMV Phase C: Box W Wikipedia FAISS search adapter.

    Uses intfloat/multilingual-e5-large for cross-lingual embedding.
    No query translation needed — ME5 handles Japanese, English, Chinese, etc. natively.

    Usage:
        adapter = WikiAdapter(
            index_path  = "Wiki/wiki_index_ivfpq_me5.faiss",
            chunks_path = "Wiki/wiki_chunks_clean.jsonl.gz",
        )
        adapter.load()
        result = adapter.retrieve("量子コンピュータとは何か")
        if adapter.get_sufficiency_score(result) >= adapter.threshold:
            # Pass result.sources to EAL
            ...

    Notes:
        - Call load() once at startup. ~1.6 GB will remain resident in RAM.
        - FAISS index is searched on CPU (faiss-cpu).
        - Query embedding device follows MMV_EMBEDDING_DEVICE.
        - sufficiency_threshold is read from wiki_manifest.json.
          If null, warns and uses 0.0 until Phase C.5 calibration.
    """

    def __init__(
        self,
        index_path:    str,
        chunks_path:   str,
        manifest_path: Optional[str] = None,
        offsets_path:  Optional[str] = None,
        nprobe: int = NPROBE,
        domain_corpus_dir: Optional[str] = None,
    ):
        self.index_path   = Path(index_path)
        self.chunks_path  = Path(chunks_path)
        self.manifest_path = (
            Path(manifest_path)
            if manifest_path
            else self.index_path.parent / "wiki_manifest.json"
        )
        self.offsets_path = (
            Path(offsets_path)
            if offsets_path
            else self.index_path.parent / "line_offsets.npy"
        )
        self.nprobe = nprobe
        # Box W curated domain pack. When provided, documents from this
        # directory are loaded at `load()` time, encoded with the same
        # SentenceTransformer instance as the main Wiki index, and
        # merged into `retrieve()` results. When None/missing, this is
        # a no-op and the adapter behaves exactly as before.
        self.domain_corpus_dir: Optional[Path] = (
            Path(domain_corpus_dir) if domain_corpus_dir else None
        )

        self._index:    Optional[faiss.Index]        = None
        self._model:    Optional[SentenceTransformer] = None
        self._store:    Optional[_GzChunkStore]       = None
        self._manifest: dict                          = {}
        self._loaded:   bool                          = False
        self.threshold: Optional[float]               = None  # Calibrated in Phase C.5
        self._domain_corpus = None
        self._last_retrieve_notes: List[str] = []

    # -- Public API -----------------------------------------------------------

    def load(self) -> None:
        """
        Load FAISS index, embedding model, and chunk store.
        Call once at startup.

        Raises:
            FileNotFoundError: index or chunks_gz does not exist
            ImportError      : indexed_gzip not installed
        """
        if self._loaded:
            return

        t0 = time.time()
        logger.info("[WikiAdapter] Loading...")

        # 1. Manifest
        self._manifest = self._load_manifest()
        self.threshold = self._manifest.get("sufficiency_threshold")
        if self.threshold is None:
            logger.warning(
                "[WikiAdapter] sufficiency_threshold is null in manifest. "
                "Using 0.0 (always sufficient) until Phase C.5 calibration."
            )
            self.threshold = 0.0

        # 2. FAISS index
        if not self.index_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {self.index_path}")
        logger.info(f"  Loading FAISS index: {self.index_path} ...")
        self._index = faiss.read_index(str(self.index_path))
        self._index.nprobe = self.nprobe
        logger.info(
            f"  FAISS: {self._index.ntotal:,} vectors, nprobe={self.nprobe}"
        )

        # 3. Embedding model (device auto-select. Principle G)
        device = self._select_device()
        logger.info(f"  Loading embedding model: {MODEL_NAME} (device={device})")
        try:
            self._model = SentenceTransformer(MODEL_NAME, device=device)
        except RuntimeError as e:
            # CUDA OOM / device contention (e.g. Ollama holding the GPU):
            # degrade to CPU rather than crash the runtime.
            if device != "cpu":
                logger.warning(
                    f"  embedding model load on {device} failed "
                    f"({type(e).__name__}: {e}); falling back to CPU."
                )
                self._model = SentenceTransformer(MODEL_NAME, device="cpu")
            else:
                raise

        # 4. Chunk store (indexed_gzip + numpy offsets)
        self._store = _GzChunkStore(self.chunks_path, self.offsets_path)
        self._store.open()

        # 5. Box W curated domain pack (optional supplementary corpus).
        # Reuses self._model so passage embeddings land in the same
        # space as FAISS vectors. Any load failure is non-fatal: we
        # silently degrade to wiki-only retrieval, with a note logged.
        self._domain_corpus = self._try_load_domain_corpus()

        self._loaded = True
        elapsed = time.time() - t0
        logger.info(f"[WikiAdapter] Ready. ({elapsed:.1f}s)")

    def retrieve(self, query: str, top_k: int = DEFAULT_TOP_K) -> RetrievalResult:
        """
        Search Wikipedia chunks for a given query.

        Accepts any language — multilingual-e5-large handles cross-lingual
        retrieval natively (no translation step needed).

        Args:
            query : Search query in any language
            top_k : Number of top chunks to retrieve (1 <= top_k <= MAX_TOP_K)

        Returns:
            RetrievalResult (sources, outcome, synthesis)
            - outcome: "success" (top_k items retrieved) | "partial" (< top_k) | "failed" (0 items)
            - synthesis: Raw newline-joined chunk text string (EAL is responsible for synthesis)

        Notes:
            - Maintain separation from Answer Entitlement.
              Even if search scores are high, the "right to answer" decision
              is made by the L0 control layer.
              (phase_c_spec_v2_2.docx §7 / handover §5.3)
        """
        if not self._loaded:
            raise RuntimeError("WikiAdapter not loaded. Call load() first.")

        top_k = max(1, min(top_k, MAX_TOP_K))
        now   = datetime.now(timezone.utc).isoformat()

        # -- 1. Query embedding (with E5 "query: " prefix) -------------------
        query_vec = self._model.encode(
            [QUERY_PREFIX + query],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)  # shape: (1, DIM)

        # -- 2. FAISS search (CPU) --------------------------------------------
        distances, indices = self._index.search(query_vec, top_k)
        # distances: (1, top_k) — inner product (= cosine similarity for normalized vectors)
        # indices  : (1, top_k) — chunk line number (= gz line number)

        valid_ids = [int(idx) for idx in indices[0] if idx >= 0]

        if not valid_ids:
            # Main FAISS index had no valid ids, but a curated domain
            # pack may still have a strong match. Try merging from an
            # empty base before declaring failure.
            sources, texts, _ = self._merge_domain_hits(
                [], [], query, top_k, now,
            )
            if not sources:
                return RetrievalResult(sources=[], outcome="failed", synthesis="")
            return RetrievalResult(
                sources   = sources,
                outcome   = "success" if len(sources) >= top_k else "partial",
                synthesis = "\n\n".join(texts),
            )

        # -- 3. Inner product scores are already cosine similarity (0 to 1) ---
        raw_scores = distances[0][: len(valid_ids)]
        cos_scores = np.clip(raw_scores, 0.0, 1.0)

        # -- 4. Retrieve chunk text (indexed_gzip) ----------------------------
        chunks = self._store.get(valid_ids)
        chunk_map = {c["rowid"]: c for c in chunks}

        sources: list[Source] = []
        texts:   list[str]    = []

        for i, rowid in enumerate(valid_ids):
            chunk = chunk_map.get(rowid)
            if chunk is None:
                continue
            score = float(cos_scores[i])
            sources.append(Source(
                source_type     = "local_rag",
                label           = chunk["title"],
                uri             = chunk["url"],
                chunk_index     = chunk["chunk_index"],
                retrieved_at    = now,
                relevance_score = round(score, 4),
            ))
            texts.append(html.unescape(chunk["text"]))

        if not sources:
            return RetrievalResult(sources=[], outcome="failed", synthesis="")

        # Box W domain-pack merge. When the optional curated corpus is
        # loaded, domain hits that score higher than the weakest wiki
        # hit are promoted into the result set. When disabled this is
        # a no-op.
        sources, texts, _ = self._merge_domain_hits(
            sources, texts, query, top_k, now,
        )

        outcome = "success" if len(sources) == top_k else "partial"

        return RetrievalResult(
            sources   = sources,
            outcome   = outcome,
            synthesis = "\n\n".join(texts),  # EAL is responsible for synthesis (§7)
        )

    def is_available(self) -> bool:
        """
        Returns whether the adapter is in a usable state.

        Returns:
            True: loaded and both FAISS index and store are valid
        """
        if not self._loaded:
            return False
        if self._index is None or self._store is None:
            return False
        return True

    def get_sufficiency_score(self, result: RetrievalResult) -> float:
        """
        Returns the sufficiency score of a RetrievalResult (0.0 to 1.0).

        Compare with the threshold calibrated in Phase C.5 to determine
        whether Box W is sufficient:
            if adapter.get_sufficiency_score(result) >= adapter.threshold:
                # Box W sufficient -> proceed to EAL
            else:
                # Proceed to Box S (Brave Search)

        Returns:
            Maximum relevance_score among retrieved chunks. 0.0 if no chunks.

        Note:
            threshold is read from wiki_manifest.json. Before Phase C.5 calibration, it is 0.0.
            The score distribution of IndexIVFPQ differs from IndexFlatIP,
            so do not directly apply 0.72; use empirically measured values instead
            (phase_c_spec_v2_2.docx §3.1).
        """
        if not result.sources:
            return 0.0
        scores = [
            s.relevance_score
            for s in result.sources
            if s.relevance_score is not None
        ]
        return max(scores) if scores else 0.0

    def update_threshold(self, threshold: float) -> None:
        """
        Update sufficiency_threshold after Phase C.5 calibration and write to manifest.

        Args:
            threshold: Empirically determined threshold value (0.0 to 1.0)
        """
        self.threshold = threshold
        self._manifest["sufficiency_threshold"] = threshold
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self._manifest, f, indent=2, ensure_ascii=False)
        logger.info(
            f"[WikiAdapter] sufficiency_threshold updated: "
            f"{threshold} → {self.manifest_path}"
        )

    def close(self) -> None:
        """Release resources."""
        if self._store:
            self._store.close()
        self._index = None
        self._model = None
        self._loaded = False

    # -- Box W domain pack ----------------------------------------------------

    def _try_load_domain_corpus(self):
        """Attempt to load the optional curated domain corpus.

        Returns the loaded DomainCorpus when successful, else None.
        A missing directory is a normal, non-error condition — it just
        means no curated pack has been provisioned for this deploy.
        """
        if self.domain_corpus_dir is None:
            return None
        if not self.domain_corpus_dir.exists():
            logger.info(
                "[WikiAdapter] domain_corpus_dir missing (skipped): %s",
                self.domain_corpus_dir,
            )
            return None
        try:
            # Late import to avoid a circular dependency at module load.
            from src.retrieval.domain_corpus import DomainCorpus
        except Exception as exc:
            logger.warning(
                "[WikiAdapter] domain_corpus import failed (non-fatal): %s", exc,
            )
            return None
        try:
            dc = DomainCorpus(self.domain_corpus_dir, encoder=self._model)
            dc.load()
            stats = dc.stats()
            if stats.document_count == 0:
                logger.info("[WikiAdapter] domain_corpus empty")
                return None
            logger.info(
                "[WikiAdapter] domain_corpus loaded: %d docs (domains=%s, index_built=%s)",
                stats.document_count, sorted(stats.domains.keys()), stats.index_built,
            )
            return dc
        except Exception as exc:
            logger.warning(
                "[WikiAdapter] domain_corpus load failed (non-fatal): %s", exc,
            )
            return None

    def _merge_domain_hits(
        self,
        sources: list,
        texts:   list,
        query:   str,
        top_k:   int,
        now_iso: str,
    ) -> tuple[list, list, List[dict]]:
        """Merge curated domain-pack hits into the current result set.

        Pure pass-through when the domain pack is absent or has no
        matching hit. Domain hits that duplicate a wiki title are
        skipped; the remainder compete on score against the wiki
        sources for the final top_k slots.
        """
        notes: List[str] = []
        self._last_retrieve_notes = notes
        if self._domain_corpus is None or not self._domain_corpus.is_ready():
            return sources, texts, []
        try:
            hits = self._domain_corpus.search(query, top_k=top_k)
        except Exception as exc:
            logger.debug("[WikiAdapter] domain_corpus.search failed: %s", exc)
            return sources, texts, []
        if not hits:
            notes.append("box_w_domain_pack_no_match")
            return sources, texts, []
        from src.retrieval.domain_corpus import (
            merge_domain_hits_into_sources,
        )
        merged_sources, merged_texts, applied_notes = merge_domain_hits_into_sources(
            sources=sources,
            texts=texts,
            domain_hits=hits,
            source_cls=Source,
            top_k=top_k,
            now_iso=now_iso,
        )
        if any(n.get("event") == "domain_hits_promoted" for n in applied_notes):
            notes.append("box_w_domain_pack_contributed")
        else:
            notes.append("box_w_domain_pack_candidate_only")
        return merged_sources, merged_texts, applied_notes

    def domain_pack_stats(self) -> Optional[dict]:
        """Return inspectable stats about the loaded curated pack, or
        None when no pack is configured or loaded.
        """
        if self._domain_corpus is None:
            return None
        stats = self._domain_corpus.stats()
        return {
            "document_count":    stats.document_count,
            "source_families":   stats.source_families,
            "domains":           stats.domains,
            "index_built":       stats.index_built,
        }

    def last_retrieve_notes(self) -> List[str]:
        """Inspectable notes from the last retrieve() call."""
        return list(self._last_retrieve_notes)

    # -- Internal methods -----------------------------------------------------

    def _load_manifest(self) -> dict:
        if not self.manifest_path.exists():
            logger.warning(f"[WikiAdapter] manifest not found: {self.manifest_path}")
            return {}
        with open(self.manifest_path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _select_device() -> str:
        """
        Select the query embedding device.

        Principle G keeps FAISS search on CPU, while ME5 embedding uses
        MMV_EMBEDDING_DEVICE=auto/cpu/cuda. auto uses CUDA when available.
        """
        return _select_embedding_device()

    def __repr__(self) -> str:
        status = "loaded" if self._loaded else "not loaded"
        return (
            f"WikiAdapter({status}, "
            f"index={self.index_path.name}, "
            f"threshold={self.threshold}, "
            f"nprobe={self.nprobe})"
        )


# -- CLI (for debugging and verification) ------------------------------------

def _cli():
    import argparse

    parser = argparse.ArgumentParser(
        description="WikiAdapter CLI — Box W search test / offset building"
    )
    parser.add_argument("--index",   default="Wiki/wiki_index_ivfpq_me5.faiss")
    parser.add_argument("--chunks",  default="Wiki/wiki_chunks_clean.jsonl.gz")
    parser.add_argument("--offsets", default="Wiki/line_offsets.npy")
    parser.add_argument("--top-k",   type=int, default=5)
    parser.add_argument("--nprobe",  type=int, default=NPROBE)
    parser.add_argument(
        "--build-offsets", action="store_true",
        help="Force rebuild of line_offsets.npy and exit"
    )
    parser.add_argument("query", nargs="?", default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.build_offsets:
        store = _GzChunkStore(
            chunks_gz_path = Path(args.chunks),
            offsets_path   = Path(args.offsets),
        )
        n = store.build_offsets()
        print(f"Built: {n:,} lines → {args.offsets}")
        return

    adapter = WikiAdapter(
        index_path   = args.index,
        chunks_path  = args.chunks,
        offsets_path = args.offsets,
        nprobe       = args.nprobe,
    )
    adapter.load()

    query = args.query or "What is the speed of light?"
    print(f"\nQuery: {query}")
    print(f"Adapter: {adapter}")

    t0 = time.time()
    result = adapter.retrieve(query, top_k=args.top_k)
    elapsed = (time.time() - t0) * 1000

    score      = adapter.get_sufficiency_score(result)
    sufficient = score >= adapter.threshold

    print(f"\nOutcome  : {result.outcome}")
    print(f"Score    : {score:.4f}  (threshold={adapter.threshold}, sufficient={sufficient})")
    print(f"Latency  : {elapsed:.1f} ms")
    print(f"Sources  : {len(result.sources)}")
    blocks = result.synthesis.split("\n\n")
    for i, src in enumerate(result.sources, 1):
        snippet = blocks[i - 1][:120] if i - 1 < len(blocks) else ""
        print(f"  [{i}] score={src.relevance_score:.4f}  {src.label}")
        print(f"       {src.uri}")
        print(f"       {snippet}...")


if __name__ == "__main__":
    _cli()
