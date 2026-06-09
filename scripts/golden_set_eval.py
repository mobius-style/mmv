#!/usr/bin/env python3
"""
golden_set_eval.py — Evaluate Pattern Library against the golden set.

Spec reference: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 3.2.

Reads:
    tests/golden_set/pattern_library_golden_set_v1.jsonl
    data/pattern_library/index.faiss
    data/pattern_library/index_metadata.jsonl

Per query:
    - ME5-encode with "query: " prefix
    - FAISS top-K (k=20)
    - Aggregate by pattern_id (max-pooling over duplicate examples)
    - Apply NEG_MARGIN gate (Pattern Library spec 3.3 Phase B placeholder)
    - Determine hit_pattern_id at threshold T

Outputs:
    - Per-topic confusion matrix
    - Threshold sweep across [0.50, 0.55, ..., 0.85] with optimal accuracy
    - Optional: write evaluation summary JSON to file

Usage:
    python scripts/golden_set_eval.py
    python scripts/golden_set_eval.py --dry-run
    python scripts/golden_set_eval.py \\
        --golden-set tests/golden_set/pattern_library_golden_set_v1.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLDEN = REPO_ROOT / "tests" / "golden_set" / "pattern_library_golden_set_v1.jsonl"
DEFAULT_INDEX = REPO_ROOT / "data" / "pattern_library" / "index.faiss"
DEFAULT_META = REPO_ROOT / "data" / "pattern_library" / "index_metadata.jsonl"

ME5_MODEL = "intfloat/multilingual-e5-large"
ME5_QUERY_PREFIX = "query: "
THRESHOLD_SWEEP = [0.50, 0.55, 0.60, 0.65, 0.70, 0.72, 0.75, 0.78, 0.80, 0.85]
TOP_K = 20

sys.path.insert(0, str(REPO_ROOT))


def load_golden(path: Path) -> list[dict]:
    """Load golden set entries; validate minimal required fields."""
    if not path.exists():
        raise FileNotFoundError(f"golden set not found: {path}")
    entries = []
    with path.open("r", encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"{path.name} line {ln}: malformed JSON ({e})"
                )
            for required in ("id", "lang", "query", "topic"):
                if required not in obj:
                    raise ValueError(
                        f"{path.name} line {ln}: missing field '{required}'"
                    )
            if not (obj.get("expected_pattern_id")
                    or obj.get("expected_no_match")):
                raise ValueError(
                    f"{path.name} line {ln}: must set either "
                    f"expected_pattern_id or expected_no_match=true"
                )
            entries.append(obj)
    return entries


def load_metadata(path: Path) -> list[dict]:
    if not path.exists():
        return []
    units = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                units.append(json.loads(line))
    return units


def aggregate_by_pattern(
    scores: list[float], indices: list[int], metadata: list[dict],
) -> list[tuple[str, float]]:
    """Max-pool scores by pattern_id. Returns list sorted high → low."""
    by_pat: dict[str, float] = {}
    for s, vec_id in zip(scores, indices):
        if vec_id < 0 or vec_id >= len(metadata):
            continue
        pid = metadata[vec_id]["pattern_id"]
        if pid not in by_pat or s > by_pat[pid]:
            by_pat[pid] = s
    return sorted(by_pat.items(), key=lambda kv: kv[1], reverse=True)


def evaluate(
    golden: list[dict], metadata: list[dict], encoder, index,
) -> dict:
    """Run the full sweep. Returns per-topic and overall accuracy at each
    threshold, and the optimal threshold per topic."""
    import numpy as np

    queries = [ME5_QUERY_PREFIX + g["query"] for g in golden]
    qvecs = encoder.encode(
        queries,
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    D, I = index.search(np.asarray(qvecs, dtype="float32"), TOP_K)

    per_query: list[dict] = []
    for g, scores, indices in zip(golden, D.tolist(), I.tolist()):
        ranked = aggregate_by_pattern(scores, indices, metadata)
        top_pid, top_score = (ranked[0] if ranked else (None, 0.0))
        per_query.append({
            "id": g["id"],
            "lang": g["lang"],
            "topic": g["topic"],
            "expected_pattern_id": g.get("expected_pattern_id"),
            "expected_no_match": bool(g.get("expected_no_match")),
            "top_pattern_id": top_pid,
            "top_score": float(top_score),
            "ranked_top5": ranked[:5],
        })

    by_topic: dict[str, list[dict]] = defaultdict(list)
    for q in per_query:
        by_topic[q["topic"]].append(q)

    sweep: dict[float, dict] = {}
    for threshold in THRESHOLD_SWEEP:
        topic_acc: dict[str, dict] = {}
        all_correct = 0
        all_n = 0
        for topic, qs in by_topic.items():
            correct = 0
            for q in qs:
                hit = q["top_score"] >= threshold and q["top_pattern_id"]
                expected_match = not q["expected_no_match"]
                if expected_match:
                    if hit and q["top_pattern_id"] == q["expected_pattern_id"]:
                        correct += 1
                else:
                    if not hit:
                        correct += 1
            topic_acc[topic] = {
                "correct": correct,
                "n": len(qs),
                "accuracy": correct / len(qs) if qs else 0.0,
            }
            all_correct += correct
            all_n += len(qs)
        sweep[threshold] = {
            "topic_acc": topic_acc,
            "overall": {
                "correct": all_correct,
                "n": all_n,
                "accuracy": all_correct / all_n if all_n else 0.0,
            },
        }

    optimal: dict[str, dict] = {}
    for topic in by_topic:
        best_t = max(THRESHOLD_SWEEP,
                     key=lambda t: sweep[t]["topic_acc"][topic]["accuracy"])
        optimal[topic] = {
            "threshold": best_t,
            "accuracy": sweep[best_t]["topic_acc"][topic]["accuracy"],
        }

    return {
        "n_queries": len(golden),
        "n_topics": len(by_topic),
        "sweep": sweep,
        "optimal_threshold_per_topic": optimal,
        "per_query": per_query,
    }


def print_summary(report: dict) -> None:
    print(f"Golden set: {report['n_queries']} queries, "
          f"{report['n_topics']} topics")
    print()
    print("Threshold sweep — overall accuracy:")
    for t, row in report["sweep"].items():
        print(f"  {t:.2f}: {row['overall']['accuracy']:.3f} "
              f"({row['overall']['correct']}/{row['overall']['n']})")
    print()
    print("Optimal threshold per topic:")
    for topic, info in report["optimal_threshold_per_topic"].items():
        print(f"  {topic:24s} t={info['threshold']:.2f} "
              f"acc={info['accuracy']:.3f}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Pattern Library against golden set"
    )
    parser.add_argument("--golden-set", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_META)
    parser.add_argument("--output", type=Path,
                        help="Write JSON evaluation report to file")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Schema-validate inputs without invoking ME5 / FAISS",
    )
    args = parser.parse_args()

    # Schema validation phase
    if not args.golden_set.exists():
        if args.dry_run:
            print(
                f"dry-run: golden set not found at {args.golden_set} — "
                "this is expected before Commit 5 lands. Skipping."
            )
            return 0
        print(f"ERROR: golden set not found: {args.golden_set}",
              file=sys.stderr)
        return 1

    try:
        golden = load_golden(args.golden_set)
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: golden set load failed: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"dry-run: golden set loaded {len(golden)} entries, "
              "schema valid")
        return 0

    if not args.index.exists():
        print(f"ERROR: FAISS index not found: {args.index}", file=sys.stderr)
        return 1

    metadata = load_metadata(args.metadata)
    if not metadata:
        print(f"ERROR: metadata empty or missing: {args.metadata}",
              file=sys.stderr)
        return 1

    try:
        import faiss
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        print(f"ERROR: missing dependency: {e}", file=sys.stderr)
        return 2

    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
    encoder = SentenceTransformer(ME5_MODEL)
    index = faiss.read_index(str(args.index))

    report = evaluate(golden, metadata, encoder, index)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2)
        )

    print_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
