#!/usr/bin/env python3
"""run_xling.py — apply XlingGenerator across the seed library.

Phase 2 Commit 16 driver. Per-pattern: expand cross_lingual_test_queries
from 4 to 8 entries (Phase 2 strengthens schema requirement to ≥3 ja
+ ≥3 zh).

Usage: same flag set as run_variants.py / run_negatives.py.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config" / "pattern_library"
AUDIT_DIR = REPO_ROOT / "data" / "pattern_library" / "audit_log"

import sys
sys.path.insert(0, str(REPO_ROOT))

from src.retrieval.pattern_schema import LifecycleEvent, Pattern  # noqa: E402
from scripts.pattern_autogen.xling_query_generator import (  # noqa: E402
    XlingGenerator,
)


def load_patterns(config_dir: Path) -> list[tuple[Path, Pattern]]:
    out: list[tuple[Path, Pattern]] = []
    for fp in sorted(config_dir.glob("*.jsonl")):
        if fp.name.startswith("_"):
            continue
        for line in fp.open("r", encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            try:
                p = Pattern.model_validate(raw)
            except Exception as e:
                print(f"WARN: skipping invalid pattern: {e}", file=sys.stderr)
                continue
            out.append((fp, p))
    return out


def atomic_rewrite(source_file: Path, patterns: list[Pattern]) -> None:
    tmp = source_file.with_suffix(source_file.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for p in patterns:
            fh.write(p.model_dump_json(exclude_none=False) + "\n")
    os.replace(tmp, source_file)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 Commit 16")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pattern", help="Restrict to one pattern_id")
    parser.add_argument("--n", type=int, default=8,
                        help="Target candidate count per pattern")
    parser.add_argument("--max-accept-per-pattern", type=int, default=8)
    args = parser.parse_args()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    pairs = load_patterns(CONFIG_DIR)
    if args.pattern:
        pairs = [(fp, p) for fp, p in pairs if p.id == args.pattern]
    if not pairs:
        print("No patterns to process.", file=sys.stderr)
        return 1

    by_source: dict[Path, list[Pattern]] = {}
    for fp, p in pairs:
        by_source.setdefault(fp, []).append(p)

    now = datetime.now(timezone.utc)
    batch_id = ("bat_xling_" + now.strftime("%Y%m%d_%H%M%S")
                + "_" + secrets.token_hex(2))
    print(f"batch_id={batch_id}")

    gen = XlingGenerator()
    audit_records: list[dict] = []

    for source_file, _ in by_source.items():
        full_in_file = [
            p for fp, p in load_patterns(CONFIG_DIR) if fp == source_file
        ]
        any_changed = False
        for p in full_in_file:
            if args.pattern and p.id != args.pattern:
                continue
            print(f"  ▶ {p.id}", flush=True)
            r = gen.generate(p, n=args.n, batch_id=batch_id)
            accepted = r.accepted[: args.max_accept_per_pattern]

            print(f"    raw={r.raw_candidate_count} "
                  f"accepted={len(accepted)} rejected={len(r.rejected)}")

            audit_records.append({
                "pattern_id": p.id, "batch_id": batch_id,
                "raw_count": r.raw_candidate_count,
                "accepted": [
                    {"lang": q.lang, "query": q.query,
                     "expected_match": q.expected_match,
                     "min_cosine": q.min_cosine}
                    for q in accepted
                ],
                "rejected": [{"text": str(c)[:80], "reason": rr}
                             for c, rr in r.rejected],
                "consensus": (
                    {"primary_used": r.consensus.primary_used,
                     "groq_run_id": r.consensus.groq_run_id}
                    if r.consensus else None
                ),
            })

            if accepted and not args.dry_run:
                for i, fp_p in enumerate(full_in_file):
                    if fp_p.id == p.id:
                        existing = list(fp_p.cross_lingual_test_queries)
                        seen_keys = {
                            (q.lang, q.query.strip().lower())
                            for q in existing
                        }
                        for a in accepted:
                            k = (a.lang, a.query.strip().lower())
                            if k not in seen_keys:
                                existing.append(a)
                                seen_keys.add(k)
                        if len(existing) > len(fp_p.cross_lingual_test_queries):
                            event = LifecycleEvent(
                                timestamp=now, event="updated",
                                actor="claude_code_autogen",
                                detail=(
                                    f"xling batch {batch_id}: "
                                    f"+{len(existing) - len(fp_p.cross_lingual_test_queries)} queries"
                                ),
                            )
                            updated = fp_p.model_copy(update={
                                "cross_lingual_test_queries": existing,
                            })
                            updated.lifecycle.history.append(event)
                            full_in_file[i] = updated
                            any_changed = True
                        break

        if any_changed and not args.dry_run:
            atomic_rewrite(source_file, full_in_file)
            print(f"  ✓ rewrote {source_file.name}")

    audit_path = AUDIT_DIR / f"autogen_{batch_id}.jsonl"
    with audit_path.open("w", encoding="utf-8") as fh:
        for rec in audit_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"audit: {audit_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
