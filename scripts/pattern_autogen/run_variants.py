#!/usr/bin/env python3
"""run_variants.py — apply VariantsGenerator across the seed library.

Phase 2 Commit 14 driver.

Workflow:
    1. Load every pattern from `config/pattern_library/*.jsonl`
    2. For each pattern, call VariantsGenerator.generate(p, per_call_n=10)
    3. Atomically rewrite the source JSONL with new examples appended
       and a `lifecycle.history.event="updated"` event recorded
    4. Write a per-batch summary to data/pattern_library/audit_log/
       autogen_<batch_id>.jsonl

Pre/post measurement: caller is expected to have run
`scripts/golden_set_eval.py --output BEFORE.json` before invoking this
script and another `--output AFTER.json` after rebuild_index. This
script does not invoke them itself.

Token cost: ~3K Groq tokens / pattern * 10 patterns ≈ 30K tokens total.

Usage:
    python scripts/pattern_autogen/run_variants.py
    python scripts/pattern_autogen/run_variants.py --dry-run
    python scripts/pattern_autogen/run_variants.py --pattern pat_self_ref_identity_001
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
from scripts.pattern_autogen.variants_generator import (  # noqa: E402
    VariantsGenerator,
)


def load_patterns(config_dir: Path) -> list[tuple[Path, Pattern]]:
    """Yield (source_file, Pattern) pairs from config/pattern_library/*.jsonl."""
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
                print(f"WARN: skipping invalid pattern in {fp.name}: {e}",
                      file=sys.stderr)
                continue
            out.append((fp, p))
    return out


def atomic_rewrite_source(
    source_file: Path, patterns_in_file: list[Pattern],
) -> None:
    tmp = source_file.with_suffix(source_file.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for p in patterns_in_file:
            fh.write(p.model_dump_json(exclude_none=False) + "\n")
    os.replace(tmp, source_file)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 2 Commit 14 — apply variants generator"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without writing")
    parser.add_argument("--pattern",
                        help="Only this pattern_id (smoke test)")
    parser.add_argument("--per-call-n", type=int, default=10)
    parser.add_argument("--max-accept-per-pattern", type=int, default=15,
                        help="Cap accepted variants per pattern")
    args = parser.parse_args()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    pairs = load_patterns(CONFIG_DIR)
    if args.pattern:
        pairs = [(fp, p) for fp, p in pairs if p.id == args.pattern]
    if not pairs:
        print("No patterns to process.", file=sys.stderr)
        return 1

    # Group by source file so we can rewrite atomically per file
    by_source: dict[Path, list[Pattern]] = {}
    for fp, p in pairs:
        by_source.setdefault(fp, []).append(p)

    now = datetime.now(timezone.utc)
    batch_id = ("bat_variants_" + now.strftime("%Y%m%d_%H%M%S")
                + "_" + secrets.token_hex(2))
    print(f"batch_id={batch_id}")

    gen = VariantsGenerator()

    audit_records: list[dict] = []
    summary = {
        "batch_id": batch_id,
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "patterns": [],
    }

    for source_file, patterns_in_file in by_source.items():
        # Load FULL pattern list for this file (including ones we don't
        # touch this run — needed for atomic rewrite)
        full_in_file = [
            p for fp, p in load_patterns(CONFIG_DIR) if fp == source_file
        ]
        any_changed = False
        for p in patterns_in_file:
            if args.pattern and p.id != args.pattern:
                continue
            print(f"  ▶ {p.id}", flush=True)
            r = gen.generate(p, per_call_n=args.per_call_n,
                              batch_id=batch_id)
            accepted = r.accepted[: args.max_accept_per_pattern]
            existing_room = 15 - len(p.examples)
            accepted = accepted[:existing_room]  # schema cap

            print(f"    raw={r.raw_candidate_count} "
                  f"accepted={len(accepted)} rejected={len(r.rejected)}")
            for cand, reason in r.rejected[:3]:
                print(f"      rej: {cand[:50]!r} — {reason}")

            audit_records.append({
                "pattern_id": p.id, "batch_id": batch_id,
                "raw_count": r.raw_candidate_count,
                "accepted": accepted,
                "rejected": [{"text": t, "reason": rr}
                             for t, rr in r.rejected],
                "consensus": (
                    {"primary_used": r.consensus.primary_used,
                     "accepted_meta": r.consensus.accepted,
                     "groq_run_id": r.consensus.groq_run_id}
                    if r.consensus else None
                ),
            })

            summary_entry = {
                "pattern_id": p.id,
                "examples_before": len(p.examples),
                "examples_added": len(accepted),
                "examples_after": len(p.examples) + len(accepted),
                "primary_used": (r.consensus.primary_used
                                  if r.consensus else None),
            }
            summary["patterns"].append(summary_entry)

            if accepted and not args.dry_run:
                # Update the in-place pattern within full_in_file
                for i, fp in enumerate(full_in_file):
                    if fp.id == p.id:
                        # Append, deduped against existing
                        existing_lower = {e.strip().lower()
                                          for e in fp.examples}
                        new_examples = list(fp.examples)
                        for a in accepted:
                            if a.strip().lower() not in existing_lower:
                                new_examples.append(a)
                                existing_lower.add(a.strip().lower())
                        if len(new_examples) > len(fp.examples):
                            event = LifecycleEvent(
                                timestamp=now, event="updated",
                                actor="claude_code_autogen",
                                detail=f"variants batch {batch_id}: +{len(new_examples) - len(fp.examples)} examples",
                            )
                            updated = fp.model_copy(update={
                                "examples": new_examples,
                            })
                            updated.lifecycle.history.append(event)
                            full_in_file[i] = updated
                            any_changed = True
                        break

        if any_changed and not args.dry_run:
            atomic_rewrite_source(source_file, full_in_file)
            print(f"  ✓ rewrote {source_file.name}")

    # Save audit
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
