"""routes/verify.py — Verify (cross-lingual test runner) page (`/verify/<id>`).

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.4.5.

GET /verify/<id>      Render the form (read-only summary of stored xling queries)
POST /verify/<id>     Run the test live: ME5-encode each query, FAISS top-K,
                      max-pool to pattern_id, compare to expected_match.
                      Lazy-loads ME5 + FAISS on first invocation.
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, current_app, render_template, request

bp = Blueprint("verify", __name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
INDEX_PATH = REPO_ROOT / "data" / "pattern_library" / "index.faiss"
META_PATH = REPO_ROOT / "data" / "pattern_library" / "index_metadata.jsonl"
CONFIG_DIR = REPO_ROOT / "config" / "pattern_library"


_LIB = None


def _get_lib():
    global _LIB
    if _LIB is None:
        from src.retrieval.pattern_lookup import PatternLibrary
        if not (INDEX_PATH.exists() and META_PATH.exists()):
            return None
        _LIB = PatternLibrary.from_disk(CONFIG_DIR, INDEX_PATH, META_PATH)
    return _LIB


@bp.route("/verify/<pattern_id>", methods=["GET", "POST"])
def verify(pattern_id: str):
    reader = current_app.config["LIBRARY_READER"]
    p = reader.get(pattern_id)
    if p is None:
        abort(404)

    results: list[dict] = []
    pass_rate: float | None = None

    if request.method == "POST":
        lib = _get_lib()
        if lib is None:
            return render_template(
                "verify_runner.html", p=p, results=[],
                pass_rate=None,
                error="Index missing — run scripts/build_pattern_index.py",
            )
        if lib.encoder is None:
            from sentence_transformers import SentenceTransformer
            lib.encoder = SentenceTransformer(
                "intfloat/multilingual-e5-large"
            )
        import numpy as np
        for q in p.cross_lingual_test_queries:
            try:
                qvec = lib.encoder.encode(
                    ["query: " + q.query],
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                D, I = lib.index.search(
                    np.asarray(qvec, dtype="float32"), 20,
                )
                top_pat: str | None = None
                top_score: float = 0.0
                seen: dict[str, float] = {}
                for s, vid in zip(D[0].tolist(), I[0].tolist()):
                    if vid < 0 or vid >= len(lib.metadata):
                        continue
                    pid = lib.metadata[vid]["pattern_id"]
                    if pid not in seen or s > seen[pid]:
                        seen[pid] = float(s)
                if seen:
                    top_pat, top_score = max(
                        seen.items(), key=lambda kv: kv[1]
                    )
                # actual match = top hit IS this pattern
                actual_match = top_pat == p.id
                # expected_match=True → require this_pattern at top with min_cosine
                # expected_match=False → require this_pattern NOT at top
                # (basic interpretation; spec leaves room for richer logic)
                if q.expected_match:
                    passed = actual_match and (
                        q.min_cosine is None
                        or seen.get(p.id, 0.0) >= q.min_cosine
                    )
                else:
                    passed = not actual_match
                results.append({
                    "lang": q.lang, "query": q.query,
                    "expected_match": q.expected_match,
                    "min_cosine": q.min_cosine,
                    "actual_top_pattern": top_pat,
                    "actual_top_score": top_score,
                    "this_pattern_score": seen.get(p.id, 0.0),
                    "passed": bool(passed),
                })
            except Exception as e:
                results.append({
                    "lang": q.lang, "query": q.query,
                    "expected_match": q.expected_match,
                    "min_cosine": q.min_cosine,
                    "actual_top_pattern": None,
                    "actual_top_score": 0.0,
                    "this_pattern_score": 0.0,
                    "passed": False,
                    "error": str(e)[:200],
                })
        if results:
            pass_rate = sum(1 for r in results if r["passed"]) / len(results)

    return render_template(
        "verify_runner.html", p=p, results=results, pass_rate=pass_rate,
        error=None,
    )
