"""routes/search.py — Search page (`/search`).

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.4.3.

Two modes (selected by `mode` query param):
    - text   (default; cheap)  — substring scan over id / intent /
                                  topic / examples / negatives / tags
    - semantic                  — ME5 query encoding + FAISS top-K over
                                  the live index, max-pooled to patterns.
                                  Lazy-loads ME5 (~5 s first call).
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, render_template, request

bp = Blueprint("search", __name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
INDEX_PATH = REPO_ROOT / "data" / "pattern_library" / "index.faiss"
META_PATH = REPO_ROOT / "data" / "pattern_library" / "index_metadata.jsonl"


_SEMANTIC_LIB = None


def _semantic_search(query: str, k: int = 10) -> list[dict]:
    """Lazy-load ME5 + FAISS once per process."""
    global _SEMANTIC_LIB
    if _SEMANTIC_LIB is None:
        from src.retrieval.pattern_lookup import PatternLibrary
        if not (INDEX_PATH.exists() and META_PATH.exists()):
            return []
        _SEMANTIC_LIB = PatternLibrary.from_disk(
            REPO_ROOT / "config" / "pattern_library", INDEX_PATH, META_PATH,
        )
    lib = _SEMANTIC_LIB
    if lib.encoder is None:
        from sentence_transformers import SentenceTransformer
        lib.encoder = SentenceTransformer("intfloat/multilingual-e5-large")
    import numpy as np
    qvec = lib.encoder.encode(
        ["query: " + query],
        convert_to_numpy=True, normalize_embeddings=True,
        show_progress_bar=False,
    )
    qvec = np.asarray(qvec, dtype="float32")
    D, I = lib.index.search(qvec, k * 4)  # over-fetch then max-pool
    by_pat: dict[str, dict] = {}
    for s, vec_id in zip(D[0].tolist(), I[0].tolist()):
        if vec_id < 0 or vec_id >= len(lib.metadata):
            continue
        pid = lib.metadata[vec_id]["pattern_id"]
        if pid not in by_pat or s > by_pat[pid]["score"]:
            by_pat[pid] = {
                "pattern_id": pid,
                "score": float(s),
                "example": lib.metadata[vec_id].get("example_text", ""),
            }
    out = sorted(by_pat.values(), key=lambda x: x["score"], reverse=True)
    return out[:k]


@bp.route("/search", methods=["GET"])
def search():
    q = (request.args.get("q") or "").strip()
    mode = (request.args.get("mode") or "text").lower()
    if mode not in ("text", "semantic"):
        mode = "text"

    text_hits: list = []
    semantic_hits: list = []
    if q:
        if mode == "text":
            reader = current_app.config["LIBRARY_READER"]
            text_hits = reader.text_search(q)
        else:
            try:
                semantic_hits = _semantic_search(q)
            except Exception as e:
                semantic_hits = []
                current_app.logger.warning("semantic search failed: %s", e)

    return render_template(
        "search_results.html",
        q=q, mode=mode,
        text_hits=text_hits,
        semantic_hits=semantic_hits,
    )
