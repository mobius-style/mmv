#!/usr/bin/env python3
"""create_seed_patterns.py — generate full Pattern JSON from a structured
spec. Phase 2 Commit 19 driver.

Each spec entry provides: id, topic, intent, brief description, and a
RouteConfig. The script asks Groq to generate examples + negatives +
cross-lingual queries in a single call per pattern, validates the
resulting JSON against Pattern (Pydantic), and appends to the
appropriate source JSONL.

Per-pattern token cost: ~2-3K (single multi-judge consensus call).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config" / "pattern_library"
AUDIT_DIR = REPO_ROOT / "data" / "pattern_library" / "audit_log"

sys.path.insert(0, str(REPO_ROOT))

from src.retrieval.pattern_schema import (  # noqa: E402
    LifecycleEvent, Origin, Pattern, RouteConfig,
)
from scripts.pattern_autogen.groq_client import (  # noqa: E402
    AutogenGroqClient,
)


SYSTEM_PROMPT = (
    "You design AI intent patterns for the MOBIUS Pattern Library. "
    "Given an intent specification, produce examples + negatives + "
    "cross-lingual test queries in STRICT JSON format. "
    "Examples: 5-10 surface phrasings of the intent (English, "
    "diverse word choice). "
    "Negatives: 4-6 disambiguators that look surface-similar but are "
    "ABOUT A DIFFERENT topic/entity. "
    "Cross-lingual queries: at least 2 Japanese (ja) + 2 Chinese (zh), "
    "mix of expected_match=true (positive paraphrases) and "
    "expected_match=false (disambiguators). "
    "min_cosine: 0.62 for expected_match=true entries, null for false. "
    "Output STRICT JSON only, no preface: "
    '{"examples": ["...", ...], "negative_examples": ["...", ...], '
    '"cross_lingual_test_queries": ['
    '{"lang": "ja|zh|...", "query": "...", '
    '"expected_match": true|false, "min_cosine": 0.62 or null}, ...]}.'
)


def build_user_prompt(spec: dict) -> str:
    return (
        f"Pattern id: {spec['id']}\n"
        f"Topic: {spec['topic']}\n"
        f"Intent: {spec['intent']}\n"
        f"Description: {spec['description']}\n\n"
        f"Output the strict JSON spec for this intent."
    )


def assemble_pattern(spec: dict, content: dict, batch_id: str,
                     run_id: str, now: datetime) -> Pattern:
    return Pattern(
        id=spec["id"],
        version="1.0",
        lang="en",
        topic=spec["topic"],
        sub_topic=spec.get("sub_topic", ""),  # Phase 4 v2.1
        intent=spec["intent"],
        concepts=spec.get("concepts", []),
        priority=spec.get("priority", 100),
        examples=content["examples"][:15],
        negative_examples=content.get("negative_examples", []),
        context_required=spec.get("context_required"),
        context_excluded=spec.get("context_excluded", []),
        route=RouteConfig(**spec["route"]),
        tags=spec.get("tags", []),
        cross_lingual_test_queries=content["cross_lingual_test_queries"],
        lifecycle={"history": [{
            "timestamp": now.isoformat(),
            "event": "created",
            "actor": "claude_code_autogen",
            "detail": f"Phase 2 Commit 19 seed (batch {batch_id})",
        }]},
        origin=Origin(
            type="autogen",
            evolution_log_entry=22,
            date=now,
            batch_id=batch_id,
            groq_run_id=run_id,
            prompt_version="seed_v1",
        ),
        deprecated=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 2 Commit 19 seed-pattern creator"
    )
    parser.add_argument("--spec", type=Path, required=True,
                        help="Path to JSON file with pattern specs")
    parser.add_argument("--target-jsonl", type=Path, required=True,
                        help="Path to config/pattern_library/<topic>.jsonl")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only first N specs (smoke)")
    args = parser.parse_args()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    specs = json.loads(args.spec.read_text(encoding="utf-8"))
    if args.limit:
        specs = specs[:args.limit]
    if not specs:
        print("No specs to process.", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    batch_id = ("bat_seed_" + now.strftime("%Y%m%d_%H%M%S")
                + "_" + secrets.token_hex(2))
    print(f"batch_id={batch_id} specs={len(specs)} target={args.target_jsonl}")

    client = AutogenGroqClient()

    accepted: list[Pattern] = []
    rejected: list[tuple[str, str]] = []

    for spec in specs:
        print(f"  ▶ {spec['id']} ({spec['intent']})", flush=True)
        consensus = client.consensus(
            SYSTEM_PROMPT, build_user_prompt(spec),
            max_tokens=2500, prompt_version="seed_v1",
            batch_id=batch_id,
        )
        # Take first parseable call's content
        content = None
        for call in consensus.calls:
            if call.parsed and isinstance(call.parsed, dict):
                if (isinstance(call.parsed.get("examples"), list)
                        and len(call.parsed["examples"]) >= 5):
                    content = call.parsed
                    break
        if content is None:
            rejected.append((spec["id"], "no parseable content"))
            print(f"    ✗ {spec['id']}: no parseable content")
            continue
        try:
            patt = assemble_pattern(
                spec, content, batch_id, consensus.groq_run_id, now,
            )
        except Exception as e:
            rejected.append((spec["id"], f"validation: {str(e)[:120]}"))
            print(f"    ✗ {spec['id']}: schema {str(e)[:80]}")
            continue
        accepted.append(patt)
        print(f"    ✓ {spec['id']}: ex={len(patt.examples)} "
              f"neg={len(patt.negative_examples)} "
              f"xl={len(patt.cross_lingual_test_queries)}")

    # Append to target JSONL
    if accepted:
        existing = []
        if args.target_jsonl.exists():
            existing = args.target_jsonl.read_text(
                encoding="utf-8"
            ).splitlines()
        with args.target_jsonl.open("w", encoding="utf-8") as fh:
            for line in existing:
                if line.strip():
                    fh.write(line + "\n")
            for p in accepted:
                fh.write(p.model_dump_json(exclude_none=False) + "\n")
        print(f"✓ Appended {len(accepted)} patterns to {args.target_jsonl}")

    # Audit
    audit_path = AUDIT_DIR / f"autogen_{batch_id}.jsonl"
    with audit_path.open("w", encoding="utf-8") as fh:
        for p in accepted:
            fh.write(json.dumps({
                "pattern_id": p.id, "batch_id": batch_id,
                "examples_count": len(p.examples),
                "neg_count": len(p.negative_examples),
                "xling_count": len(p.cross_lingual_test_queries),
            }, ensure_ascii=False) + "\n")
        for pid, reason in rejected:
            fh.write(json.dumps({
                "pattern_id": pid, "rejected": reason,
                "batch_id": batch_id,
            }, ensure_ascii=False) + "\n")
    print(f"audit: {audit_path}")

    print(f"Summary: accepted={len(accepted)} rejected={len(rejected)}")
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
