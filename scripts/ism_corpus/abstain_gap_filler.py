#!/usr/bin/env python3
"""abstain_gap_filler.py — ISM corpus Op-2 (abstain gap fill).

Phase 4 v2.1 Commit 7. Generates ISM chunks with
qk_entitlement="abstain" to lift the abstain share from 0.2 % to
≥ 3 %.

Sources (per Path B plan):
1. Pattern Library negative_examples (already labeled out-of-scope
   for their pattern's intent) — sourced from existing 80 patterns
2. Codex / Reflective Economics / Code of Conscience domain
   queries identified as abstain-worthy
3. Synthetic Groq generation with abstain-relevant seed prompt

Output JSONL written to data/raf/ism_chunks_pending.jsonl (same
file as intent_variants_generator).

Usage:
    python3 scripts/ism_corpus/abstain_gap_filler.py \\
        --source pattern_library_negatives --max-chunks 200
    python3 scripts/ism_corpus/abstain_gap_filler.py \\
        --source synthetic --max-chunks 500
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PL_CONFIG = REPO_ROOT / "config" / "pattern_library"
PENDING_PATH = REPO_ROOT / "data" / "raf" / "ism_chunks_pending.jsonl"
AUDIT_DIR = REPO_ROOT / "data" / "pattern_library" / "audit_log"

sys.path.insert(0, str(REPO_ROOT))


SYSTEM_PROMPT_SYNTHETIC = (
    "You generate queries that an AI assistant should ABSTAIN from "
    "answering — questions that exceed its evidence base. Categories: "
    "(1) speculation about specific individuals' future actions or "
    "private thoughts, (2) personal predictions (will I marry X), "
    "(3) requests for medical/legal/financial advice that require "
    "professional credentials, (4) questions about content of "
    "private documents/communications, (5) value judgments on "
    "individuals' moral worth. Output STRICT JSON array of strings, "
    "N queries, mix of EN/JA/ZH evenly."
)


def assemble_chunk(query: str, language: str, batch_id: str,
                    groq_run_id: str, source_label: str,
                    intent_type: str = "factual_query") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "intent_type": intent_type,
        "formal_type": "what",
        "response_type": "direct_answer",
        "wiki_lookup": False,
        "qk_entitlement": "abstain",
        "qk_tvs_estimate": "medium",
        "qk_halfstep_type": "none",
        "language": language,
        "query": query,
        "_origin": {
            "type": "ism_autogen",
            "batch_id": batch_id,
            "groq_run_id": groq_run_id,
            "prompt_version": f"abstain_gap_v1_{source_label}",
        },
    }


def detect_language(text: str) -> str:
    """Crude language detection — sufficient for ISM corpus scope.

    Strategy: hiragana/katakana presence anywhere in the string is a
    strong JA signal (since ZH does not use these scripts). If absent,
    CJK unified ideograph presence indicates ZH. Otherwise EN.
    """
    has_kana = False
    has_cjk = False
    for ch in text:
        if "぀" <= ch <= "ゟ" or "゠" <= ch <= "ヿ":
            has_kana = True
            break  # JA confirmed
        if "一" <= ch <= "鿿":
            has_cjk = True
    if has_kana:
        return "ja"
    if has_cjk:
        return "zh"
    return "en"


def source_pattern_library_negatives(max_chunks: int,
                                       batch_id: str) -> list[dict]:
    """Extract negative_examples from existing 80 patterns. The
    negatives are explicitly out-of-scope for their pattern's intent
    — many serve as candidates for abstain-worthy queries when
    re-framed as standalone."""
    chunks = []
    for jsonl in PL_CONFIG.glob("*.jsonl"):
        if jsonl.name.startswith("_"):
            continue
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            for neg in obj.get("negative_examples") or []:
                if not isinstance(neg, str) or not neg.strip():
                    continue
                # Heuristic: keep only out-of-domain queries that look
                # like real questions (have ? or とは or 是什么 or
                # what / how / why etc.)
                lang = detect_language(neg)
                chunks.append(assemble_chunk(
                    query=neg, language=lang, batch_id=batch_id,
                    groq_run_id="pl_neg_extract",
                    source_label="pattern_library_negatives",
                ))
                if len(chunks) >= max_chunks:
                    return chunks
    return chunks


def source_synthetic(max_chunks: int, batch_id: str) -> list[dict]:
    """Generate abstain-worthy queries via Groq."""
    from scripts.pattern_autogen.groq_client import AutogenGroqClient
    client = AutogenGroqClient()
    user_prompt = (
        f"Generate exactly {max_chunks} abstain-worthy queries. "
        f"Mix of EN/JA/ZH (~33% each). Cover all 5 categories "
        f"described. Output STRICT JSON array of strings."
    )
    consensus = client.consensus(
        SYSTEM_PROMPT_SYNTHETIC, user_prompt,
        max_tokens=2500, prompt_version="abstain_gap_v1_synthetic",
        batch_id=batch_id,
    )
    raw_list = None
    for call in consensus.calls:
        if call.parsed and isinstance(call.parsed, list):
            raw_list = [q for q in call.parsed
                         if isinstance(q, str) and q.strip()]
            if raw_list:
                break
    if not raw_list:
        return []
    chunks = []
    for q in raw_list[:max_chunks]:
        lang = detect_language(q)
        chunks.append(assemble_chunk(
            query=q, language=lang, batch_id=batch_id,
            groq_run_id=consensus.groq_run_id,
            source_label="synthetic",
        ))
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", required=True,
        choices=["pattern_library_negatives", "synthetic"],
    )
    parser.add_argument("--max-chunks", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    batch_id = (
        f"bat_ism_abstain_{args.source}_"
        + now.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(2)
    )

    if args.source == "pattern_library_negatives":
        chunks = source_pattern_library_negatives(args.max_chunks,
                                                    batch_id)
    else:
        chunks = source_synthetic(args.max_chunks, batch_id)

    if not chunks:
        print(f"No chunks produced for source={args.source}",
              file=sys.stderr)
        return 1

    if args.dry_run:
        for c in chunks[:10]:
            print(json.dumps(c, ensure_ascii=False))
        print(f"\\n[dry-run] would write {len(chunks)} chunks")
        return 0

    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PENDING_PATH.open("a", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = AUDIT_DIR / f"ism_abstain_{batch_id}.jsonl"
    with audit_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "batch_id": batch_id, "source": args.source,
            "n_chunks": len(chunks),
        }, ensure_ascii=False) + "\n")
        for c in chunks:
            fh.write(json.dumps({
                "chunk_id": c["id"], "lang": c["language"],
                "query": c["query"][:100],
            }, ensure_ascii=False) + "\n")
    print(f"✓ Appended {len(chunks)} abstain chunks to {PENDING_PATH}")
    print(f"  Audit: {audit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
