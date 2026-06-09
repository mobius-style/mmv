#!/usr/bin/env python3
"""run_negatives.py — apply NegativesGenerator across the seed library.

Phase 2 Commit 15 driver. Mirrors run_variants.py for negative_examples
expansion. Per-pattern target: ~20 negatives total.

Usage:
    python scripts/pattern_autogen/run_negatives.py
    python scripts/pattern_autogen/run_negatives.py --dry-run
    python scripts/pattern_autogen/run_negatives.py --pattern pat_x
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
from scripts.pattern_autogen.negatives_generator import (  # noqa: E402
    NegativesGenerator,
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
    parser = argparse.ArgumentParser(description="Phase 2 Commit 15")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pattern", help="Restrict to one pattern_id")
    parser.add_argument("--n", type=int, default=15,
                        help="Target candidate count per pattern")
    parser.add_argument("--max-accept-per-pattern", type=int, default=12,
                        help="Cap accepted negatives per pattern")
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
    batch_id = ("bat_negatives_" + now.strftime("%Y%m%d_%H%M%S")
                + "_" + secrets.token_hex(2))
    print(f"batch_id={batch_id}")

    gen = NegativesGenerator()

    audit_records: list[dict] = []
    summary = {
        "batch_id": batch_id,
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "patterns": [],
    }

    for source_file, patterns_in_file in by_source.items():
        full_in_file = [
            p for fp, p in load_patterns(CONFIG_DIR) if fp == source_file
        ]
        any_changed = False
        for p in patterns_in_file:
            if args.pattern and p.id != args.pattern:
                continue
            print(f"  ▶ {p.id}", flush=True)
            r = gen.generate(p, n=args.n, batch_id=batch_id)
            accepted = r.accepted[: args.max_accept_per_pattern]

            print(f"    raw={r.raw_candidate_count} "
                  f"accepted={len(accepted)} rejected={len(r.rejected)}")
            for t, reason in r.rejected[:3]:
                print(f"      rej: {t[:50]!r} — {reason[:55]}")

            audit_records.append({
                "pattern_id": p.id, "batch_id": batch_id,
                "raw_count": r.raw_candidate_count,
                "accepted": accepted,
                "rejected": [{"text": t, "reason": rr}
                             for t, rr in r.rejected],
                "consensus": (
                    {"primary_used": r.consensus.primary_used,
                     "groq_run_id": r.consensus.groq_run_id}
                    if r.consensus else None
                ),
            })

            summary["patterns"].append({
                "pattern_id": p.id,
                "negatives_before": len(p.negative_examples),
                "negatives_added": len(accepted),
                "negatives_after": len(p.negative_examples) + len(accepted),
                "primary_used": (r.consensus.primary_used
                                  if r.consensus else None),
            })

            if accepted and not args.dry_run:
                for i, fp in enumerate(full_in_file):
                    if fp.id == p.id:
                        existing_lower = {
                            e.strip().lower()
                            for e in fp.negative_examples
                        }
                        new_negs = list(fp.negative_examples)
                        for a in accepted:
                            if a.strip().lower() not in existing_lower:
                                new_negs.append(a)
                                existing_lower.add(a.strip().lower())
                        if len(new_negs) > len(fp.negative_examples):
                            event = LifecycleEvent(
                                timestamp=now, event="updated",
                                actor="claude_code_autogen",
                                detail=(
                                    f"negatives batch {batch_id}: +"
                                    f"{len(new_negs) - len(fp.negative_examples)} "
                                    f"negatives"
                                ),
                            )
                            updated = fp.model_copy(update={
                                "negative_examples": new_negs,
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
    summary_path = AUDIT_DIR / f"autogen_{batch_id}.summary.json"
    summary["finished_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"audit: {audit_path}")
    print(f"summary: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
