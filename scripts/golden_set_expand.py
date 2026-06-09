#!/usr/bin/env python3
"""golden_set_expand.py — Phase 4 ST2 long-tail golden set generator.

Generates long-tail golden set entries via Groq + ME5/FAISS auto-annotation.
Each entry pairs a long-tail query with either an `expected_pattern_id`
(when ME5+FAISS top-1 score ≥ STRICT_THRESHOLD) or `expected_no_match=true`
(when top-1 < NO_MATCH_THRESHOLD). Ambiguous middle-band scores are
dropped to keep label-desync risk minimal.

Spec ref:
    docs/PHASE_4_LONG_TAIL_DESIGN.md (8 LT categories, distribution targets)
    Phase 4 v2.1 prompt §STEP 4 (Sub-thread 2)

Output: tests/golden_set/long_tail_v1.jsonl (one entry per line, schema
compatible with golden_set_eval.py).

Usage:
    python3 scripts/golden_set_expand.py \\
        --category LT-1 --topic conceptual_explain --count 20

    python3 scripts/golden_set_expand.py \\
        --category LT-3 --topic factual_inquiry --count 15 \\
        --output tests/golden_set/long_tail_v1.jsonl
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.pattern_autogen.groq_client import AutogenGroqClient  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "tests" / "golden_set" / "long_tail_v1.jsonl"
INDEX_PATH = REPO_ROOT / "data" / "pattern_library" / "index.faiss"
META_PATH = REPO_ROOT / "data" / "pattern_library" / "index_metadata.jsonl"

# Annotation thresholds (label-desync prevention).
# A query is auto-labeled with expected_pattern_id only if the FAISS
# top-1 score (max-pooled by pattern_id) is ≥ STRICT_THRESHOLD. Below
# NO_MATCH_THRESHOLD, the query is labeled expected_no_match=true. The
# in-between band is dropped to avoid wrong-label entries.
STRICT_THRESHOLD = 0.85
NO_MATCH_THRESHOLD = 0.50
TOP_K = 20

VALID_TOPICS = {
    "self_reference", "conceptual_explain", "factual_inquiry",
    "correction", "casual_engagement", "casual_greeting",
}

# ─────────────────────────────────────────────────────────────────
# Long-tail category prompts
# ─────────────────────────────────────────────────────────────────

CATEGORY_PROMPTS = {
    "LT-1": (
        "Generate queries that mix everyday phrasing with domain-specific "
        "or specialized terminology (especially MOBIUS-internal terms like "
        "Box A/B/C/W, FAISS, ME5, Pattern Library, RoutingEngine, "
        "Constitutional Invariants, ISM, Phase markers). Each query should "
        "feel like a real user check-in or seek-confirmation, not a clean "
        "definitional question."
    ),
    "LT-2": (
        "Generate multi-paragraph queries (3+ sentences of context-setting "
        "before the actual question). The question should be embedded "
        "in or follow extensive narrative or technical setup. The "
        "appraiser must extract intent from a late-position interrogative."
    ),
    "LT-3": (
        "Generate intra-sentence code-switching queries that mix two or "
        "more of Japanese / Chinese / English in a single utterance. The "
        "non-trivial mix is REQUIRED — a single English noun in a "
        "Japanese sentence is too shallow. Mix verbs, modifiers, and "
        "discourse markers across languages."
    ),
    "LT-4": (
        "Generate pragmatically ambiguous queries where literal "
        "interpretation differs from speaker intent (rhetorical "
        "questions, indirect requests, conventionalized politeness, "
        "phatic communication). The challenge is intent extraction "
        "beyond surface form."
    ),
    "LT-5": (
        "Generate queries whose meaning is context-dependent on a prior "
        "turn — anaphora, ellipsis, vague continuation ('もっと教えて', "
        "'and what about X', 'the other one'). Mark each query with a "
        "'context_required' field describing what prior turn would be "
        "needed."
    ),
    "LT-6": (
        "Generate queries that span the boundary between formal types: "
        "math notation, code snippets, structured lists, JSON/YAML "
        "fragments. Each query should pose a real question about the "
        "formal content."
    ),
    "LT-7": (
        "Generate queries about MOBIUS-internal deep content: Reflective "
        "Economics three-layer structure, Code of Conscience seven "
        "axioms, L1-L8 hierarchy theory, Codex v1 sustained reflection, "
        "Box Σ existence, governance layering, super_supervisor doctrine. "
        "These are deeper than the standard ce_mobius_components level."
    ),
    "LT-8": (
        "Generate queries expressing the SAME intent across different "
        "linguistic registers: 敬語 (very formal Japanese), 普通体 "
        "(neutral Japanese), タメ口 (casual Japanese), 関西弁 (Kansai "
        "dialect), 古語 (old-formal Japanese), Internet/SNS (casual "
        "with abbreviation/emoticons), formal Chinese (请告知), casual "
        "Chinese (告诉我), and archaic English (Pray tell, Wherefore)."
    ),
}


# ─────────────────────────────────────────────────────────────────
# Generation
# ─────────────────────────────────────────────────────────────────

GEN_SYSTEM_PROMPT = (
    "You generate test queries for the MOBIUS Pattern Library long-tail "
    "evaluation. Output STRICT JSON only, no preface, with this shape: "
    '{"queries": [{"lang": "en|ja|zh", "query": "..."}, ...]}. '
    "Generate diverse, realistic queries — vary surface phrasing, "
    "language, length. Each query should be self-contained (or, for "
    "LT-5, marked with context_required)."
)


def build_user_prompt(category: str, topic: str, count: int) -> str:
    cat_prompt = CATEGORY_PROMPTS[category]
    topic_hint = (
        f"Target topic: {topic}. The queries should be the kind of "
        f"input a real user would write that the routing engine "
        f"should classify into this topic (or correctly REJECT as "
        f"out-of-domain)."
    )
    return (
        f"Category: {category}\n"
        f"{cat_prompt}\n\n"
        f"{topic_hint}\n\n"
        f"Generate {count} diverse queries. Mix languages "
        f"(JA/ZH/EN, with target ~33% each unless category dictates "
        f"otherwise). STRICT JSON only."
    )


def generate_queries(
    category: str, topic: str, count: int, batch_id: str,
) -> list[dict]:
    """Use Groq consensus (3 calls × N queries each) to get diverse output.
    Returns a flat list of {lang, query} dicts; deduped by query text."""
    client = AutogenGroqClient()
    # Per-call ask for ⌈count / 3⌉ + small overhead since we get 3 calls
    per_call = max(5, (count + 2) // 3 + 2)
    consensus = client.consensus(
        GEN_SYSTEM_PROMPT,
        build_user_prompt(category, topic, per_call),
        max_tokens=2500,
        prompt_version="goldenset_lt_v1",
        batch_id=batch_id,
    )
    seen: set[str] = set()
    pool: list[dict] = []
    for call in consensus.calls:
        if not isinstance(call.parsed, dict):
            continue
        qs = call.parsed.get("queries")
        if not isinstance(qs, list):
            continue
        for q in qs:
            if not isinstance(q, dict):
                continue
            text = (q.get("query") or "").strip()
            lang = (q.get("lang") or "").strip()
            if not text or not lang or lang not in {"en", "ja", "zh"}:
                continue
            if text in seen:
                continue
            seen.add(text)
            entry = {"lang": lang, "query": text}
            if "context_required" in q and q["context_required"]:
                entry["context_required"] = q["context_required"]
            pool.append(entry)
    return pool


# ─────────────────────────────────────────────────────────────────
# Annotation (ME5 + FAISS top-1 lookup)
# ─────────────────────────────────────────────────────────────────

def annotate_batch(
    candidates: list[dict], topic_filter: str,
) -> list[dict]:
    """Run ME5 + FAISS top-1 lookup on each query. Returns the subset
    that can be confidently labeled (strict positive or strict negative);
    drops ambiguous middle-band entries."""
    if not candidates:
        return []
    import faiss  # type: ignore
    import numpy as np
    from src.services.me5_singleton import get_me5_singleton

    if not INDEX_PATH.exists():
        raise FileNotFoundError(
            f"FAISS index not found at {INDEX_PATH} — run "
            f"scripts/build_pattern_index.py first."
        )
    if not META_PATH.exists():
        raise FileNotFoundError(f"index metadata not found at {META_PATH}")

    metadata = []
    with META_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                metadata.append(json.loads(line))

    index = faiss.read_index(str(INDEX_PATH))
    me5 = get_me5_singleton()
    queries = [c["query"] for c in candidates]
    qvecs = me5.encode_batch(queries, prefix="query: ", batch_size=32)
    D, I = index.search(np.asarray(qvecs, dtype="float32"), TOP_K)

    annotated: list[dict] = []
    for c, scores, indices in zip(candidates, D.tolist(), I.tolist()):
        # max-pool by pattern_id
        by_pat: dict[str, tuple[float, str]] = {}
        for s, vec_id in zip(scores, indices):
            if vec_id < 0 or vec_id >= len(metadata):
                continue
            md = metadata[vec_id]
            pid = md["pattern_id"]
            ptopic = md.get("topic", "")
            if pid not in by_pat or s > by_pat[pid][0]:
                by_pat[pid] = (s, ptopic)
        if not by_pat:
            top_pid, top_score, top_topic = None, 0.0, ""
        else:
            top_pid, (top_score, top_topic) = max(
                by_pat.items(), key=lambda kv: kv[1][0],
            )

        entry = {
            "lang": c["lang"],
            "query": c["query"],
        }
        if "context_required" in c:
            entry["context_required"] = c["context_required"]

        if top_score >= STRICT_THRESHOLD and top_pid:
            # Strict positive: ME5+FAISS top-1 confidently matches
            entry["expected_pattern_id"] = top_pid
            entry["topic"] = top_topic or topic_filter
            entry["_meta_top_score"] = float(top_score)
            annotated.append(entry)
        elif top_score < NO_MATCH_THRESHOLD:
            # Strict negative: out-of-library by a clear margin
            entry["expected_no_match"] = True
            entry["topic"] = topic_filter
            entry["_meta_top_score"] = float(top_score)
            annotated.append(entry)
        # else: ambiguous middle band — drop
    return annotated


# ─────────────────────────────────────────────────────────────────
# I/O + orchestration
# ─────────────────────────────────────────────────────────────────

def existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if "id" in obj:
                out.add(obj["id"])
        except json.JSONDecodeError:
            continue
    return out


def existing_queries(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            q = obj.get("query")
            if q:
                out.add(q.strip())
        except json.JSONDecodeError:
            continue
    return out


def next_id(category: str, used: set[str]) -> str:
    """ID format: lt_<cat-lower>_<NNNNN>. Counts existing entries with the
    same category prefix to allocate the next index."""
    prefix = f"lt_{category.lower().replace('-', '')}_"
    existing_idx = [
        int(uid[len(prefix):])
        for uid in used
        if uid.startswith(prefix) and uid[len(prefix):].isdigit()
    ]
    n = max(existing_idx) + 1 if existing_idx else 1
    while f"{prefix}{n:05d}" in used:
        n += 1
    return f"{prefix}{n:05d}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Long-tail golden set expansion (Phase 4 ST2)",
    )
    parser.add_argument(
        "--category", required=True,
        choices=sorted(CATEGORY_PROMPTS.keys()),
        help="Long-tail category (LT-1 ... LT-8)",
    )
    parser.add_argument(
        "--topic", required=True,
        choices=sorted(VALID_TOPICS),
        help="Target topic — used for OOD-negative labeling",
    )
    parser.add_argument(
        "--count", type=int, default=20,
        help="Target candidate count to generate (post-Groq); accepted "
             "subset is typically smaller after annotation filtering",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="Output JSONL (appended; default tests/golden_set/long_tail_v1.jsonl)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate + annotate but do NOT write JSONL",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    batch_id = ("bat_lt_" + now.strftime("%Y%m%d_%H%M%S")
                + "_" + secrets.token_hex(2))
    print(f"batch_id={batch_id} category={args.category} "
          f"topic={args.topic} count={args.count}")

    # Stage 1: Groq generation
    pool = generate_queries(
        args.category, args.topic, args.count, batch_id,
    )
    print(f"  stage1 generated: {len(pool)} unique queries (target {args.count})")
    if not pool:
        print("  ✗ no queries generated — abort")
        return 1

    # Stage 2: dedupe against existing
    used_q = existing_queries(args.output)
    pool = [c for c in pool if c["query"] not in used_q]
    print(f"  stage2 deduped: {len(pool)} new queries (vs existing set)")
    if not pool:
        print("  ✗ all queries already in golden set — abort")
        return 1

    # Stage 3: ME5+FAISS auto-annotation (drops ambiguous middle band)
    annotated = annotate_batch(pool, args.topic)
    n_dropped = len(pool) - len(annotated)
    n_pos = sum(1 for a in annotated if "expected_pattern_id" in a)
    n_neg = sum(1 for a in annotated if a.get("expected_no_match"))
    print(f"  stage3 annotated: {len(annotated)} kept, "
          f"{n_dropped} dropped (ambiguous band)")
    print(f"            positives: {n_pos} | negatives: {n_neg}")

    if not annotated:
        print("  ✗ all candidates fell into ambiguous band — abort")
        return 1

    # Stage 4: assign IDs + write
    used_ids = existing_ids(args.output)
    final: list[dict] = []
    for entry in annotated:
        eid = next_id(args.category, used_ids)
        used_ids.add(eid)
        out = {
            "id": eid,
            "lang": entry["lang"],
            "query": entry["query"],
            "topic": entry["topic"],
            "source": f"autogen_{args.category}_{batch_id}",
        }
        if "expected_pattern_id" in entry:
            out["expected_pattern_id"] = entry["expected_pattern_id"]
        if entry.get("expected_no_match"):
            out["expected_no_match"] = True
        if "context_required" in entry:
            out["context_required"] = entry["context_required"]
        if "_meta_top_score" in entry:
            out["_meta_top_score"] = entry["_meta_top_score"]
        final.append(out)

    if args.dry_run:
        print(f"  dry-run: would append {len(final)} entries — not writing")
        for e in final[:3]:
            print(f"    sample: {json.dumps(e, ensure_ascii=False)}")
        return 0

    with args.output.open("a", encoding="utf-8") as fh:
        for e in final:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"  ✓ appended {len(final)} entries to {args.output}")
    print(f"    yield: {len(final)}/{len(pool)} = "
          f"{len(final) / len(pool) * 100:.1f}% post-annotation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
