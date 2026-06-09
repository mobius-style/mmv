"""
domain_corpus.py — Bounded, curated supplementary corpus for Box W.

This module loads a small, hand-curated supplementary corpus of
domain-focused reference documents (e.g. category theory glossary
entries) from a filesystem directory, encodes them into the same
embedding space used by the Box W Wikipedia index, and exposes a
`search(query, top_k)` entry point that WikiAdapter can consult
during retrieval.

Design principles:
  - Bounded. Not a web crawler. Each document is a curated markdown
    file with explicit frontmatter that the author vetted.
  - Provenance-aware. Every record preserves source_family, domain,
    title, aliases, source_uri, file_hash, and added_at so the origin
    of any returned match is inspectable.
  - Reuses Box W's embedding model when one is injected, so vectors
    are directly comparable to FAISS Wikipedia hits and no parallel
    retrieval subsystem is introduced. When no encoder is injected,
    the loader still reads documents and exposes coverage metadata —
    useful for audit paths that do not need to embed.
  - Query-safe. When a search request arrives but the corpus is
    empty, the search returns an empty list cleanly instead of
    crashing.
  - No runtime logic changes. This module is pure data + retrieval
    plumbing.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# The ME5 "query: " prefix is required for multilingual-e5-large.
# For "passage" embeddings the recommended prefix is "passage: ".
# Passing the wrong-prefixed vector still produces usable cosine
# similarity, but using the conventional pair improves separation.
_QUERY_PREFIX = "query: "
_PASSAGE_PREFIX = "passage: "


# Provenance source family identifier. Kept constant so that all
# documents ingested through this module share one inspectable label.
SOURCE_FAMILY_CURATED = "curated_domain_pack"


# Supported file extensions for curated seed documents.
_SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}


# Extremely small YAML-like frontmatter parser. We intentionally do
# not pull in PyYAML here — curated documents carry trivial key:value
# metadata only, and a dependency on PyYAML would be disproportionate.
_FRONTMATTER_FENCE = "---"


@dataclass
class DomainDocument:
    """A single curated domain-pack record.

    Attributes:
        title         : Human-readable title (used as Source.label).
        domain        : Domain label (e.g. "category theory").
        aliases       : Alternative surface forms (Japanese, etc.).
        source_family : Provenance family (see SOURCE_FAMILY_CURATED).
        source_uri    : Stable inspectable URI (e.g. domain://...).
        source_path   : Relative path under the corpus root.
        file_hash     : SHA-256 of the raw file bytes.
        added_at      : ISO 8601 UTC string for when the doc was last
                        ingested (rebuilt when file_hash changes).
        text          : The body text of the document (after frontmatter).
    """
    title:         str
    domain:        str
    aliases:       List[str]
    source_family: str
    source_uri:    str
    source_path:   str
    file_hash:     str
    added_at:      str
    text:          str

    def provenance(self) -> Dict[str, Any]:
        """Inspectable provenance record for audit paths."""
        return {
            "title":         self.title,
            "domain":        self.domain,
            "aliases":       list(self.aliases),
            "source_family": self.source_family,
            "source_uri":    self.source_uri,
            "source_path":   self.source_path,
            "file_hash":     self.file_hash,
            "added_at":      self.added_at,
        }


@dataclass
class DomainSearchHit:
    """A single scored search hit from the domain corpus."""
    document: DomainDocument
    score:    float


@dataclass
class DomainCorpusStats:
    """Inspectable summary of what the corpus currently knows."""
    document_count:    int
    source_families:   List[str]
    domains:           Dict[str, int]    # domain → doc count
    index_built:       bool
    encoder_available: bool


def _file_hash(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _parse_frontmatter(raw: str) -> Tuple[Dict[str, Any], str]:
    """Parse a tiny frontmatter block of the form:

        ---
        key: value
        list_key: [a, b, c]
        ---

        Body text...

    Returns ``(meta, body)``. If no frontmatter fence is present,
    returns an empty meta dict and the full raw string as body.
    Only string and flat list-of-string values are supported.
    """
    if not raw.startswith(_FRONTMATTER_FENCE):
        return {}, raw

    lines = raw.splitlines()
    if len(lines) < 2:
        return {}, raw

    # Locate the closing fence.
    try:
        close = next(
            i for i in range(1, len(lines)) if lines[i].strip() == _FRONTMATTER_FENCE
        )
    except StopIteration:
        return {}, raw

    meta: Dict[str, Any] = {}
    for line in lines[1:close]:
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # List of strings: [a, b, c]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            items = [
                item.strip().strip('"').strip("'")
                for item in inner.split(",")
                if item.strip()
            ]
            meta[key] = items
        else:
            # Strip surrounding quotes if present.
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            meta[key] = value

    body = "\n".join(lines[close + 1:]).lstrip("\n")
    return meta, body


class DomainCorpus:
    """Bounded, curated supplementary corpus for Box W.

    Typical usage:
        corpus = DomainCorpus("data/box_w_domain", encoder=wiki_model)
        corpus.load()
        hits = corpus.search("what is a counit", top_k=3)

    Notes:
        - When `encoder` is None, load() still reads and parses all
          documents, but search() returns an empty list because no
          embeddings are available. This keeps the audit path useful
          even when the heavy embedding model is not loaded.
        - Embeddings are computed with the ``passage: `` prefix so
          they align with E5's recommended passage encoding.
        - IDs are stable across a single process; they are the
          position in the sorted document list.
    """

    def __init__(
        self,
        corpus_dir: str | Path,
        encoder:    Any = None,
        *,
        source_family: str = SOURCE_FAMILY_CURATED,
    ):
        self.corpus_dir = Path(corpus_dir)
        self._encoder = encoder
        self._source_family = source_family

        self._documents: List[DomainDocument] = []
        self._passage_vectors: Optional[np.ndarray] = None
        self._built_at: Optional[str] = None

    # -- Public surface ------------------------------------------------------

    def load(self) -> None:
        """Scan the corpus directory, parse documents, build passage
        embeddings. Safe to call repeatedly; a second call is a full
        reload (cheap because curated corpora are small).
        """
        self._documents = self._scan_documents()
        if not self._documents:
            self._passage_vectors = None
            self._built_at = datetime.now(timezone.utc).isoformat()
            logger.info(
                "[DomainCorpus] %s: 0 documents loaded", self.corpus_dir,
            )
            return

        if self._encoder is not None:
            try:
                texts = [_PASSAGE_PREFIX + d.text for d in self._documents]
                vecs = self._encoder.encode(
                    texts,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                arr = np.asarray(vecs, dtype=np.float32)
                # Defensive shape check — encoders can return (N, d).
                if arr.ndim == 2 and arr.shape[0] == len(self._documents):
                    self._passage_vectors = arr
                else:
                    logger.warning(
                        "[DomainCorpus] unexpected encoder output shape %s — "
                        "skipping embedding",
                        getattr(arr, "shape", None),
                    )
                    self._passage_vectors = None
            except Exception as exc:
                logger.warning(
                    "[DomainCorpus] passage embedding failed (non-fatal): %s",
                    exc,
                )
                self._passage_vectors = None
        else:
            self._passage_vectors = None

        self._built_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "[DomainCorpus] %s: %d documents loaded (index_built=%s)",
            self.corpus_dir, len(self._documents),
            self._passage_vectors is not None,
        )

    def search(self, query: str, top_k: int = 5) -> List[DomainSearchHit]:
        """Return up to ``top_k`` scored hits for ``query``.

        Produces an empty list when:
            - no documents were loaded
            - no encoder was injected
            - embeddings could not be built
            - ``query`` is an empty string

        Cosine similarities are clipped to the ``[0.0, 1.0]`` range so
        they are directly comparable to WikiAdapter scores.
        """
        if not query or not query.strip():
            return []
        if self._passage_vectors is None or not self._documents:
            return []
        if self._encoder is None:
            return []
        if top_k <= 0:
            return []

        try:
            qvec = self._encoder.encode(
                [_QUERY_PREFIX + query],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            qarr = np.asarray(qvec, dtype=np.float32)
        except Exception as exc:
            logger.debug("[DomainCorpus] query encode failed: %s", exc)
            return []

        if qarr.ndim != 2 or qarr.shape[0] != 1:
            return []
        # Safety: ensure dimensions match.
        if qarr.shape[1] != self._passage_vectors.shape[1]:
            logger.debug(
                "[DomainCorpus] query/passage dim mismatch: %s vs %s",
                qarr.shape[1], self._passage_vectors.shape[1],
            )
            return []

        scores = (self._passage_vectors @ qarr[0]).astype(np.float32)
        # Normalized inner product == cosine similarity. Clip for safety.
        scores = np.clip(scores, 0.0, 1.0)

        k = min(top_k, len(self._documents))
        # argpartition for speed; fully sort the top-k slice.
        if k <= 0:
            return []
        top_idx = np.argpartition(-scores, k - 1)[:k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]

        out: List[DomainSearchHit] = []
        for idx in top_idx:
            i = int(idx)
            out.append(DomainSearchHit(
                document=self._documents[i],
                score=float(scores[i]),
            ))
        return out

    def stats(self) -> DomainCorpusStats:
        """Return an inspectable summary of the loaded corpus."""
        domains: Dict[str, int] = {}
        families: set[str] = set()
        for d in self._documents:
            domains[d.domain] = domains.get(d.domain, 0) + 1
            families.add(d.source_family)
        return DomainCorpusStats(
            document_count=len(self._documents),
            source_families=sorted(families),
            domains=domains,
            index_built=self._passage_vectors is not None,
            encoder_available=self._encoder is not None,
        )

    def manifest(self) -> Dict[str, Any]:
        """Machine-readable manifest (inspectable externally)."""
        return {
            "corpus_dir":       str(self.corpus_dir),
            "built_at":         self._built_at,
            "document_count":   len(self._documents),
            "source_families":  self.stats().source_families,
            "domains":          self.stats().domains,
            "index_built":      self._passage_vectors is not None,
            "documents":        [d.provenance() for d in self._documents],
        }

    @property
    def documents(self) -> List[DomainDocument]:
        """Read-only list of loaded documents."""
        return list(self._documents)

    def is_ready(self) -> bool:
        """True when embeddings are built and documents are loaded."""
        return (
            self._passage_vectors is not None
            and bool(self._documents)
        )

    # -- Internal helpers ----------------------------------------------------

    def _scan_documents(self) -> List[DomainDocument]:
        """Scan the corpus directory and parse all supported files.

        Files that fail to parse are skipped with a warning; a corrupt
        curated entry must never take the whole corpus down.
        """
        if not self.corpus_dir.exists():
            return []

        out: List[DomainDocument] = []
        # Sort for deterministic ordering, which in turn stabilizes
        # document IDs across load calls.
        paths = sorted(
            p for p in self.corpus_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in _SUPPORTED_SUFFIXES
        )
        for path in paths:
            try:
                raw = path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning(
                    "[DomainCorpus] read failed %s: %s", path, exc,
                )
                continue
            meta, body = _parse_frontmatter(raw)
            body_text = body.strip()
            if not body_text:
                logger.warning(
                    "[DomainCorpus] empty body (skipped): %s", path,
                )
                continue

            title = str(meta.get("title") or path.stem)
            domain = str(meta.get("domain") or "uncategorized")
            aliases_raw = meta.get("aliases") or []
            aliases: List[str]
            if isinstance(aliases_raw, list):
                aliases = [str(a) for a in aliases_raw if str(a).strip()]
            elif isinstance(aliases_raw, str) and aliases_raw.strip():
                aliases = [aliases_raw.strip()]
            else:
                aliases = []
            source_uri = str(
                meta.get("source_uri")
                or f"domain://{domain.replace(' ', '_').lower()}/{path.stem.lower()}"
            )
            rel = path.relative_to(self.corpus_dir).as_posix()
            try:
                fhash = _file_hash(path)
            except Exception as exc:
                logger.warning(
                    "[DomainCorpus] hash failed %s: %s", path, exc,
                )
                fhash = ""
            added_at = datetime.now(timezone.utc).isoformat()

            out.append(DomainDocument(
                title=title,
                domain=domain,
                aliases=aliases,
                source_family=self._source_family,
                source_uri=source_uri,
                source_path=rel,
                file_hash=fhash,
                added_at=added_at,
                text=body_text,
            ))
        return out


# -- Coverage audit helpers --------------------------------------------------

# Diagnosis categories used by the Box W coverage audit path. These
# intentionally mirror the categories required by the corpus
# expansion spec so that downstream readers can filter on them.
DIAGNOSIS_CORPUS_MISSING              = "corpus_missing"
DIAGNOSIS_CORPUS_PRESENT_UNINDEXED    = "corpus_present_but_unindexed"
DIAGNOSIS_INDEXED_NOT_RETRIEVED       = "indexed_but_not_retrieved"
DIAGNOSIS_RETRIEVED_LOW_RANK          = "retrieved_but_ranked_too_low"
DIAGNOSIS_RETRIEVED_POOR_CHUNK        = "retrieved_but_chunk_quality_poor"
DIAGNOSIS_OTHER                       = "other"


_VALID_DIAGNOSES = {
    DIAGNOSIS_CORPUS_MISSING,
    DIAGNOSIS_CORPUS_PRESENT_UNINDEXED,
    DIAGNOSIS_INDEXED_NOT_RETRIEVED,
    DIAGNOSIS_RETRIEVED_LOW_RANK,
    DIAGNOSIS_RETRIEVED_POOR_CHUNK,
    DIAGNOSIS_OTHER,
}


@dataclass
class HardCaseAudit:
    """One row of a Box W coverage audit."""
    query:             str
    expected_title:    str
    diagnosis:         str
    in_domain_corpus:  bool
    top_wiki_title:    Optional[str] = None
    top_wiki_score:    Optional[float] = None
    notes:             List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.diagnosis not in _VALID_DIAGNOSES:
            raise ValueError(
                f"invalid diagnosis '{self.diagnosis}'. "
                f"valid: {sorted(_VALID_DIAGNOSES)}"
            )


def classify_hard_case(
    *,
    query:          str,
    expected_title: str,
    wiki_retriever: Any = None,
    domain_corpus:  Optional[DomainCorpus] = None,
    top_k:          int = 5,
    rank_threshold: int = 3,
) -> HardCaseAudit:
    """Classify a hard-case query against the current Box W stack.

    Args:
        query            : The user query string.
        expected_title   : The ground-truth article title we believe
                           should be returned.
        wiki_retriever   : Any object with a ``retrieve(query, top_k)``
                           method returning a RetrievalResult-like
                           object. May be None if we are auditing
                           corpus presence only.
        domain_corpus    : Optional DomainCorpus to check for a
                           curated seed record.
        top_k            : How many wiki hits to look at.
        rank_threshold   : "Ranked too low" means rank > this.

    Returns:
        A HardCaseAudit row.
    """
    notes: List[str] = []
    in_domain = False
    if domain_corpus is not None:
        in_domain = any(
            expected_title.strip().lower() == d.title.strip().lower()
            or expected_title.strip().lower() in (a.strip().lower() for a in d.aliases)
            for d in domain_corpus.documents
        )
        if in_domain:
            notes.append("domain_corpus_has_entry")

    top_wiki_title: Optional[str] = None
    top_wiki_score: Optional[float] = None
    top_titles: List[Tuple[int, str, float]] = []

    if wiki_retriever is not None:
        try:
            result = wiki_retriever.retrieve(query, top_k=top_k)
            for rank, src in enumerate(getattr(result, "sources", []) or [], 1):
                label = getattr(src, "label", "") or ""
                score = float(getattr(src, "relevance_score", 0.0) or 0.0)
                top_titles.append((rank, label, score))
                if rank == 1:
                    top_wiki_title = label
                    top_wiki_score = score
        except Exception as exc:
            notes.append(f"wiki_retriever_error:{exc}")

    # Classification.
    #
    # 1. If the expected title is directly the top hit, nothing is
    #    wrong — we still emit "other" so callers can filter.
    # 2. If the expected title appears in the top-k but beyond the
    #    rank threshold → ranked_too_low.
    # 3. If the expected title does not appear in the top-k but is in
    #    the domain corpus → corpus_present_but_unindexed (from the
    #    point of view of the main Wiki FAISS index).
    # 4. If the expected title does not appear anywhere and is not in
    #    the domain corpus → corpus_missing.
    # 5. If the wiki retriever was not provided → corpus_missing when
    #    domain corpus also lacks it, otherwise corpus_present_but_unindexed.
    if wiki_retriever is None:
        diagnosis = (
            DIAGNOSIS_CORPUS_PRESENT_UNINDEXED if in_domain
            else DIAGNOSIS_CORPUS_MISSING
        )
        notes.append("wiki_retriever_not_provided")
        return HardCaseAudit(
            query=query,
            expected_title=expected_title,
            diagnosis=diagnosis,
            in_domain_corpus=in_domain,
            top_wiki_title=None,
            top_wiki_score=None,
            notes=notes,
        )

    expected_norm = expected_title.strip().lower()
    match_rank: Optional[int] = None
    for rank, label, _score in top_titles:
        if label.strip().lower() == expected_norm or expected_norm in label.lower():
            match_rank = rank
            break

    if match_rank is None:
        if in_domain:
            diagnosis = DIAGNOSIS_CORPUS_PRESENT_UNINDEXED
            notes.append("expected_title_not_in_wiki_top_k")
        else:
            diagnosis = DIAGNOSIS_CORPUS_MISSING
            notes.append("expected_title_not_in_wiki_top_k_and_absent_from_domain_pack")
    elif match_rank == 1:
        diagnosis = DIAGNOSIS_OTHER
        notes.append("expected_title_already_top_hit")
    elif match_rank <= rank_threshold:
        diagnosis = DIAGNOSIS_RETRIEVED_LOW_RANK
        notes.append(f"expected_title_found_at_rank={match_rank}")
    else:
        diagnosis = DIAGNOSIS_RETRIEVED_LOW_RANK
        notes.append(
            f"expected_title_found_at_rank={match_rank} "
            f"(below threshold {rank_threshold})"
        )

    return HardCaseAudit(
        query=query,
        expected_title=expected_title,
        diagnosis=diagnosis,
        in_domain_corpus=in_domain,
        top_wiki_title=top_wiki_title,
        top_wiki_score=top_wiki_score,
        notes=notes,
    )


# -- Merge helper for WikiAdapter consumption --------------------------------

def merge_domain_hits_into_sources(
    *,
    sources:      list,
    texts:        list,
    domain_hits:  List[DomainSearchHit],
    source_cls:   Any,
    top_k:        int,
    now_iso:      Optional[str] = None,
) -> Tuple[list, list, List[Dict[str, Any]]]:
    """Merge curated domain hits into a Box W result set.

    Strategy:
      - Both groups are scored on normalized cosine similarity in the
        same embedding space, so their scores are comparable.
      - Domain hits are converted to Source objects with
        source_type="local_rag" (Frozen v1.0 preserved).
      - Dedup: a domain hit whose title matches a wiki source title
        (case-insensitive) is skipped — the wiki source wins because
        it has broader context.
      - We keep the top-``top_k`` combined hits, sorted by score
        descending, original order preserved on ties.

    Returns the new (sources, texts, applied_notes) triple. ``applied_notes``
    is a list of inspectable dicts describing each promotion/skip.
    """
    if not domain_hits:
        return list(sources), list(texts), []

    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    applied_notes: List[Dict[str, Any]] = []

    existing_titles = {
        (getattr(s, "label", "") or "").strip().lower() for s in sources
    }

    # Convert domain hits to Source objects, skip dedup matches.
    domain_entries: List[Tuple[Any, str, float, Dict[str, Any]]] = []
    for hit in domain_hits:
        d = hit.document
        title_key = d.title.strip().lower()
        if title_key in existing_titles:
            applied_notes.append({
                "event":       "domain_hit_skipped_duplicate",
                "title":       d.title,
                "source_uri":  d.source_uri,
                "score":       round(hit.score, 4),
            })
            continue
        src = source_cls(
            source_type     = "local_rag",
            label           = d.title,
            uri             = d.source_uri,
            chunk_index     = 0,
            retrieved_at    = now_iso,
            relevance_score = round(float(hit.score), 4),
        )
        domain_entries.append((src, d.text, float(hit.score), {
            "event":          "domain_hit_candidate",
            "title":          d.title,
            "domain":         d.domain,
            "source_family":  d.source_family,
            "score":          round(float(hit.score), 4),
        }))

    # Merge by score. Wiki sources keep their relevance_score; treat
    # missing scores as 0.0 to preserve ordering robustness.
    merged: List[Tuple[Any, str, float, str]] = []
    for i, s in enumerate(sources):
        score = float(getattr(s, "relevance_score", 0.0) or 0.0)
        body = texts[i] if i < len(texts) else ""
        merged.append((s, body, score, "wiki"))
    for (src, body, score, note) in domain_entries:
        merged.append((src, body, score, "domain"))
        applied_notes.append(note)

    # Stable sort by descending score.
    merged.sort(key=lambda t: -t[2])
    final = merged[:max(top_k, 0)] if top_k > 0 else merged

    final_sources = [t[0] for t in final]
    final_texts = [t[1] for t in final]

    # Record which entries survived the merge.
    kept_domain = sum(1 for t in final if t[3] == "domain")
    if kept_domain > 0:
        applied_notes.append({
            "event":           "domain_hits_promoted",
            "promoted_count":  kept_domain,
            "final_top_k":     len(final_sources),
        })

    return final_sources, final_texts, applied_notes
