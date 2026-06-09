#!/usr/bin/env python3
"""intent_variants_generator.py — ISM corpus Op-1 (intent rebalance).

Phase 4 v2.1 Commit 7. Generates intent-class paraphrase variants
for under-represented ISM intents (correction, meta_question,
game_move, clarification, creative_request, translation_request).

Each generated chunk follows the ISM corpus shape:
    {
      "id": "<uuid>",
      "intent_type": "<target_intent>",
      "formal_type": "<inferred>",
      "response_type": "direct_answer",
      "wiki_lookup": <bool>,
      "qk_entitlement": "answerable",
      "qk_tvs_estimate": "<low|medium|high>",
      "qk_halfstep_type": "none",
      "language": "<en|ja|zh>",
      "query": "<query text>",
      "_origin": {
        "type": "ism_autogen",
        "batch_id": "<batch>",
        "groq_run_id": "<run>",
        "prompt_version": "intent_variants_v1",
        "seed_chunk_id": "<seed>"
      }
    }

Reuses scripts/pattern_autogen/groq_client.py multi-judge consensus.

CRITICAL: this generator does NOT touch src/adapters/raf/profile.py.
Output JSONL is written to data/raf/ism_chunks_pending.jsonl;
explicit human review + index rebuild step apply changes.

Usage:
    python3 scripts/ism_corpus/intent_variants_generator.py \\
        --target-intent meta_question --variants-per-seed 5 \\
        --max-seeds 50
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# teacher_data_raw.jsonl is the source-of-truth corpus that retains the
# `query` field needed for paraphrase seeding. ism_chunks.jsonl drops it
# during FAISS index build, so it cannot serve as a seed source.
ISM_CORPUS = REPO_ROOT / "data" / "raf" / "teacher_data_raw.jsonl"
PENDING_PATH = REPO_ROOT / "data" / "raf" / "ism_chunks_pending.jsonl"
AUDIT_DIR = REPO_ROOT / "data" / "pattern_library" / "audit_log"

sys.path.insert(0, str(REPO_ROOT))

from scripts.pattern_autogen.groq_client import (  # noqa: E402
    AutogenGroqClient,
)


SUPPORTED_TARGETS = (
    "correction", "meta_question", "game_move",
    "clarification", "creative_request", "translation_request",
)

SYSTEM_PROMPT = (
    "You generate paraphrase variants of a query while preserving its "
    "intent_type, formal_type, language, and qk_* metadata. Output "
    "STRICT JSON only, no preface, with this exact shape: "
    '{"variants": ["v1", "v2", ...]}. '
    "Variants must use diverse word choice, sentence structure, and "
    "register but stay within the target intent_type. Do not change "
    "the language. Do not add new entities."
)


def _user_prompt(seed: dict, n_variants: int) -> str:
    return (
        f"Target intent_type: {seed['intent_type']}\n"
        f"Target formal_type: {seed['formal_type']}\n"
        f"Language: {seed['language']}\n"
        f"Seed query: {seed.get('query', '')}\n"
        f"Generate exactly {n_variants} paraphrase variants. "
        f'Return STRICT JSON: {{"variants": [...]}}.'
    )


def load_seeds_for_intent(intent: str, max_seeds: int) -> list[dict]:
    """Pick up to `max_seeds` highest-confidence chunks of `intent`
    from the existing corpus. Confidence proxy: any chunk that has a
    `query` field populated and isn't a duplicate of another chunk by
    raw text. (Existing corpus chunks lack a query field in some
    cases; those are skipped.)"""
    seeds = []
    seen_queries = set()
    with ISM_CORPUS.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("intent_type") != intent:
                continue
            q = obj.get("query", "")
            if not q or q in seen_queries:
                continue
            seen_queries.add(q)
            seeds.append(obj)
            if len(seeds) >= max_seeds:
                break
    return seeds


def assemble_chunk(seed: dict, variant_text: str, batch_id: str,
                    groq_run_id: str) -> dict:
    """Build a new ISM chunk preserving seed metadata + new query."""
    return {
        "id": str(uuid.uuid4()),
        "intent_type": seed["intent_type"],
        "formal_type": seed.get("formal_type", "what"),
        "response_type": seed.get("response_type", "direct_answer"),
        "wiki_lookup": bool(seed.get("wiki_lookup", True)),
        "qk_entitlement": seed.get("qk_entitlement", "answerable"),
        "qk_tvs_estimate": seed.get("qk_tvs_estimate", "medium"),
        "qk_halfstep_type": seed.get("qk_halfstep_type", "none"),
        "language": seed.get("language", "en"),
        "query": variant_text,
        "_origin": {
            "type": "ism_autogen",
            "batch_id": batch_id,
            "groq_run_id": groq_run_id,
            "prompt_version": "intent_variants_v1",
            "seed_chunk_id": seed.get("id"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-intent", required=True,
                        choices=SUPPORTED_TARGETS)
    parser.add_argument("--variants-per-seed", type=int, default=5)
    parser.add_argument("--max-seeds", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print pending output to stdout, do not write")
    args = parser.parse_args()

    seeds = load_seeds_for_intent(args.target_intent, args.max_seeds)
    if not seeds:
        print(f"No seeds found for intent={args.target_intent} "
              f"(corpus chunks may lack query field)", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    batch_id = (
        f"bat_ism_{args.target_intent}_"
        + now.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(2)
    )
    print(f"Generating intent={args.target_intent} variants: "
          f"{len(seeds)} seeds × {args.variants_per_seed} = "
          f"{len(seeds) * args.variants_per_seed} candidates")
    print(f"batch_id={batch_id}")

    client = AutogenGroqClient()
    accepted: list[dict] = []
    seed_results: dict[str, int] = defaultdict(int)

    for seed in seeds:
        consensus = client.consensus(
            SYSTEM_PROMPT,
            _user_prompt(seed, args.variants_per_seed),
            max_tokens=600,
            prompt_version="intent_variants_v1",
            batch_id=batch_id,
        )
        # Take the first parseable call's content. groq_client returns
        # parsed dicts only, so we unwrap the {"variants": [...]} shape.
        variants_list = None
        for call in consensus.calls:
            if not (call.parsed and isinstance(call.parsed, dict)):
                continue
            raw = call.parsed.get("variants")
            if not isinstance(raw, list):
                continue
            variants_list = [v for v in raw
                              if isinstance(v, str) and v.strip()]
            if variants_list:
                break
        if not variants_list:
            print(f"  ✗ {seed.get('id', '?')[:8]}: no parseable variants")
            continue
        for v in variants_list[:args.variants_per_seed]:
            chunk = assemble_chunk(seed, v, batch_id,
                                    consensus.groq_run_id)
            accepted.append(chunk)
            seed_results[seed["id"]] += 1
        print(f"  ✓ seed {seed.get('id', '?')[:8]}: "
              f"+{seed_results[seed['id']]} variants "
              f"(query='{seed.get('query', '')[:40]}')")

    if args.dry_run:
        for c in accepted[:10]:
            print(json.dumps(c, ensure_ascii=False))
        print(f"\\n[dry-run] would write {len(accepted)} chunks")
        return 0

    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PENDING_PATH.open("a", encoding="utf-8") as fh:
        for c in accepted:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = AUDIT_DIR / f"ism_autogen_{batch_id}.jsonl"
    with audit_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "batch_id": batch_id,
            "target_intent": args.target_intent,
            "n_seeds": len(seeds),
            "n_accepted": len(accepted),
            "acceptance_rate": (len(accepted) /
                                  (len(seeds) * args.variants_per_seed)
                                  if seeds else 0.0),
        }, ensure_ascii=False) + "\n")
        for c in accepted:
            fh.write(json.dumps({
                "chunk_id": c["id"], "seed_chunk_id": c["_origin"]["seed_chunk_id"],
                "query": c["query"][:100],
            }, ensure_ascii=False) + "\n")

    expected = len(seeds) * args.variants_per_seed
    print(f"\\n✓ Appended {len(accepted)} chunks to {PENDING_PATH}")
    print(f"  Acceptance rate: {len(accepted) / expected * 100:.1f}% "
          f"({len(accepted)}/{expected})")
    print(f"  Audit: {audit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
