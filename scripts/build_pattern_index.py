#!/usr/bin/env python3
"""
build_pattern_index.py — Build FAISS IndexFlatIP over Pattern Library examples.

Spec reference: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 2.5.

Reads:
    config/pattern_library/*.jsonl  (one Pattern per line)

Writes:
    data/pattern_library/index.faiss
    data/pattern_library/index_metadata.jsonl
        (one record per indexed vector: vec_id, pattern_id, example_text, topic)

Properties:
    - Index unit: each example in pattern.examples is a separate vector
      (1 pattern = 5..15 vectors)
    - Embedding: intfloat/multilingual-e5-large, 1024-dim, "passage: " prefix
    - Distance: inner product on L2-normalized vectors (cosine similarity)
    - GPU: CUDA_VISIBLE_DEVICES=0 if available, else CPU

Empty library: graceful exit (no patterns → no index file written, exit 0).

Usage:
    python scripts/build_pattern_index.py
    python scripts/build_pattern_index.py --config-dir config/pattern_library
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "pattern_library"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "pattern_library"
DEFAULT_INDEX_PATH = DEFAULT_OUTPUT_DIR / "index.faiss"
DEFAULT_METADATA_PATH = DEFAULT_OUTPUT_DIR / "index_metadata.jsonl"

ME5_MODEL = "intfloat/multilingual-e5-large"
ME5_DIM = 1024
ME5_PASSAGE_PREFIX = "passage: "

sys.path.insert(0, str(REPO_ROOT))


def iter_pattern_jsonl(config_dir: Path) -> Iterator[tuple[Path, dict]]:
    """Yield (file_path, raw_pattern_dict) for each line of every *.jsonl
    under config_dir. Files starting with '_' are skipped (metadata)."""
    for path in sorted(config_dir.glob("*.jsonl")):
        if path.name.startswith("_"):
            continue
        with path.open("r", encoding="utf-8") as fh:
            for ln, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield path, json.loads(line)
                except json.JSONDecodeError as e:
                    print(
                        f"WARNING: {path.name} line {ln}: skipping malformed JSON ({e})",
                        file=sys.stderr,
                    )


def validate_patterns(records: list[tuple[Path, dict]]) -> list:
    """Validate each record against pattern_schema.Pattern. Drops invalid
    ones with a warning. Returns a list of validated Pattern objects."""
    from src.retrieval.pattern_schema import Pattern
    validated = []
    for path, raw in records:
        try:
            validated.append(Pattern.model_validate(raw))
        except Exception as e:
            print(
                f"WARNING: {path.name} pattern '{raw.get('id', '?')}': "
                f"validation failed, skipping ({type(e).__name__})",
                file=sys.stderr,
            )
    return validated


def build_index(output_index: Path, output_metadata: Path,
                config_dir: Path) -> int:
    output_index.parent.mkdir(parents=True, exist_ok=True)

    records = list(iter_pattern_jsonl(config_dir))
    if not records:
        print(
            f"build_pattern_index: no patterns under {config_dir} — empty "
            "library. Skipping index build."
        )
        # Remove stale index if present so downstream code sees empty state
        if output_index.exists():
            output_index.unlink()
        if output_metadata.exists():
            output_metadata.unlink()
        return 0

    patterns = validate_patterns(records)
    if not patterns:
        print(
            "build_pattern_index: no valid patterns after schema validation. "
            "Skipping index build.",
            file=sys.stderr,
        )
        return 1

    # Phase 4 v2.1 audit remediation: skip patterns whose lifecycle
    # audit_status flags them as deprecation_candidate, deprecated,
    # or under_review. Keeps them in the JSONL for audit trail but
    # excludes from the live FAISS index so route_via_pattern_library
    # cannot match them. Patterns can be reactivated by setting
    # audit_status="active" after re-evaluation.
    INACTIVE_STATUSES = {
        "deprecation_candidate", "deprecated", "under_review",
    }
    skipped_inactive = 0
    active_patterns = []
    for p in patterns:
        status = getattr(p.lifecycle, "audit_status", "active")
        if status in INACTIVE_STATUSES:
            skipped_inactive += 1
            continue
        active_patterns.append(p)
    if skipped_inactive:
        print(
            f"build_pattern_index: skipped {skipped_inactive} inactive "
            f"patterns (audit_status in {sorted(INACTIVE_STATUSES)})",
        )
    patterns = active_patterns
    if not patterns:
        print(
            "build_pattern_index: no active patterns after audit_status "
            "filter. Skipping index build.",
            file=sys.stderr,
        )
        return 1

    # Aggregate (vec_id, pattern_id, example_text, topic, sub_topic)
    # flat list. Phase 4 v2 Commit 3 adds sub_topic to metadata so
    # downstream lookup / audit / coverage analysis can filter by
    # sub-topic without re-loading the full pattern dicts.
    units: list[dict] = []
    texts: list[str] = []
    for p in patterns:
        sub_topic = getattr(p, "sub_topic", "") or ""
        for ex in p.examples:
            units.append({
                "vec_id": len(units),
                "pattern_id": p.id,
                "example_text": ex,
                "topic": p.topic,
                "sub_topic": sub_topic,
            })
            texts.append(ME5_PASSAGE_PREFIX + ex)

    print(
        f"build_pattern_index: {len(patterns)} patterns, "
        f"{len(texts)} example vectors to embed"
    )

    try:
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        print(f"ERROR: missing dependency: {e}", file=sys.stderr)
        return 2

    # Honor GPU constraint per spec: GPU 0 only
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

    model = SentenceTransformer(ME5_MODEL)
    embeddings = model.encode(
        texts,
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True,  # cosine via inner product
        show_progress_bar=False,
    )
    if embeddings.shape[1] != ME5_DIM:
        print(
            f"ERROR: embedding dim {embeddings.shape[1]} != {ME5_DIM}",
            file=sys.stderr,
        )
        return 3

    index = faiss.IndexFlatIP(ME5_DIM)
    index.add(np.asarray(embeddings, dtype="float32"))
    faiss.write_index(index, str(output_index))

    with output_metadata.open("w", encoding="utf-8") as fh:
        for u in units:
            fh.write(json.dumps(u, ensure_ascii=False) + "\n")

    print(
        f"build_pattern_index: wrote {output_index} "
        f"({index.ntotal} vectors) and {output_metadata}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build FAISS index over Pattern Library examples"
    )
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA_PATH)
    args = parser.parse_args()

    if not args.config_dir.exists():
        print(
            f"ERROR: config dir not found: {args.config_dir}",
            file=sys.stderr,
        )
        return 1

    return build_index(args.index, args.metadata, args.config_dir)


if __name__ == "__main__":
    sys.exit(main())
