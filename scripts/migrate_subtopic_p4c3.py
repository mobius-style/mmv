#!/usr/bin/env python3
"""migrate_subtopic_p4c3.py — Phase 4 v2 Commit 3.

One-shot migration: assign `sub_topic` to all 80 existing Phase 1-3
patterns by looking up their `intent` in `_taxonomy.yaml` legacy_intents
mapping. Patterns whose intent is not mapped get sub_topic=""
(topic-level fallback).

Usage:
    python3 scripts/migrate_subtopic_p4c3.py
    python3 scripts/migrate_subtopic_p4c3.py --dry-run
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "pattern_library"
TAXONOMY = CFG / "_taxonomy.yaml"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    taxonomy = yaml.safe_load(TAXONOMY.read_text(encoding="utf-8"))

    # Build intent → sub_topic_id reverse index
    intent_to_subtopic: dict[str, str] = {}
    for topic, info in taxonomy.items():
        if not isinstance(info, dict) or "sub_topics" not in info:
            continue
        for sid, sinfo in info["sub_topics"].items():
            for intent in sinfo.get("legacy_intents") or []:
                intent_to_subtopic[intent] = sid

    print(f"Loaded {len(intent_to_subtopic)} intent → sub_topic mappings")

    migrated = 0
    unmapped: list[tuple[str, str]] = []
    for jsonl in sorted(CFG.glob("*.jsonl")):
        if jsonl.name.startswith("_"):
            continue
        lines = [
            json.loads(line) for line in
            jsonl.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        changed = False
        for obj in lines:
            intent = obj.get("intent", "")
            sub_topic = intent_to_subtopic.get(intent, "")
            if obj.get("sub_topic", "") != sub_topic:
                obj["sub_topic"] = sub_topic
                changed = True
                migrated += 1
            if not sub_topic:
                unmapped.append((obj.get("id", "?"), intent))
        if changed and not args.dry_run:
            with jsonl.open("w", encoding="utf-8") as fh:
                for obj in lines:
                    fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            print(f"  ✓ {jsonl.name}: migrated {sum(1 for o in lines if o.get('sub_topic'))} patterns")

    print(f"\nMigrated {migrated} patterns")
    if unmapped:
        print(f"\nUnmapped ({len(unmapped)}):")
        for pid, intent in unmapped:
            print(f"  {pid} (intent={intent}) → topic-level fallback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
