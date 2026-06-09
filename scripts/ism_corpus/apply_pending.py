#!/usr/bin/env python3
"""apply_pending.py — ISM corpus apply gate (Phase 4 ST3).

Bridges the auto-gen output (data/raf/ism_chunks_pending.jsonl) to the
source-of-truth corpus (data/raf/teacher_data_raw.jsonl). After this
script runs, scripts/build_ism_index.py rebuilds ism_index.faiss with
the new chunks included.

Pipeline:
    1. Generate variants → ism_chunks_pending.jsonl
    2. (Optional human review)
    3. apply_pending.py → append pending to teacher_data_raw.jsonl,
       move applied chunks to data/raf/applied/<batch_id>.jsonl,
       clear pending.
    4. build_ism_index.py → rebuild FAISS (GPU embedding work).

The apply step is gated and reversible: a backup of teacher_data_raw
is written before append, and applied chunks remain in the per-batch
audit file.

Usage:
    python3 scripts/ism_corpus/apply_pending.py --dry-run
    python3 scripts/ism_corpus/apply_pending.py
    python3 scripts/ism_corpus/apply_pending.py --build   # auto-trigger rebuild
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PENDING = REPO_ROOT / "data" / "raf" / "ism_chunks_pending.jsonl"
TEACHER = REPO_ROOT / "data" / "raf" / "teacher_data_raw.jsonl"
APPLIED_DIR = REPO_ROOT / "data" / "raf" / "applied"
BUILDER = REPO_ROOT / "scripts" / "build_ism_index.py"

REQUIRED_FIELDS = (
    "id", "intent_type", "formal_type", "language", "query",
    "qk_entitlement",
)


def validate_chunk(c: dict) -> str | None:
    """Return None if chunk passes validation, else error message."""
    for f in REQUIRED_FIELDS:
        if f not in c or c[f] in (None, ""):
            return f"missing field: {f}"
    if not isinstance(c["query"], str) or not c["query"].strip():
        return "query empty"
    if c["language"] not in {"ja", "en", "zh"}:
        return f"unsupported language: {c['language']}"
    return None


def load_pending() -> list[dict]:
    if not PENDING.exists():
        return []
    out = []
    for i, line in enumerate(PENDING.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError as e:
            print(f"  ! line {i}: invalid JSON ({e})", file=sys.stderr)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate + show plan, do not modify files")
    parser.add_argument("--build", action="store_true",
                        help="Run scripts/build_ism_index.py after apply "
                             "(GPU embedding work — set CUDA_VISIBLE_DEVICES=0)")
    args = parser.parse_args()

    chunks = load_pending()
    if not chunks:
        print(f"No pending chunks at {PENDING} — nothing to do.")
        return 0

    print(f"Loaded {len(chunks)} pending chunks")

    valid: list[dict] = []
    rejected: list[tuple[int, str]] = []
    by_batch: dict[str, int] = defaultdict(int)
    by_intent: dict[str, int] = defaultdict(int)
    for i, c in enumerate(chunks, 1):
        err = validate_chunk(c)
        if err:
            rejected.append((i, err))
            continue
        valid.append(c)
        bid = c.get("_origin", {}).get("batch_id", "<unknown>")
        by_batch[bid] += 1
        by_intent[c["intent_type"]] += 1

    print(f"  Valid: {len(valid)}  Rejected: {len(rejected)}")
    if rejected:
        for i, err in rejected[:5]:
            print(f"    line {i}: {err}")
        if len(rejected) > 5:
            print(f"    ... +{len(rejected) - 5} more")
    print(f"  By intent: {dict(by_intent)}")
    print(f"  By batch:  {dict(by_batch)}")

    if not valid:
        print("  ✗ no valid chunks — abort")
        return 1

    if args.dry_run:
        print(f"  [dry-run] would append {len(valid)} chunks to {TEACHER.name}")
        return 0

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")
    backup = TEACHER.with_name(f"teacher_data_raw_backup_{ts}.jsonl")
    shutil.copy2(TEACHER, backup)
    print(f"  ✓ backup: {backup.name}")

    with TEACHER.open("a", encoding="utf-8") as fh:
        for c in valid:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"  ✓ appended {len(valid)} chunks to {TEACHER.name}")

    APPLIED_DIR.mkdir(parents=True, exist_ok=True)
    for batch_id, n in by_batch.items():
        applied_path = APPLIED_DIR / f"{batch_id}.jsonl"
        with applied_path.open("w", encoding="utf-8") as fh:
            for c in valid:
                if c.get("_origin", {}).get("batch_id") == batch_id:
                    fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"  ✓ archived batch {batch_id} ({n} chunks) → {applied_path.name}")

    PENDING.write_text("", encoding="utf-8")
    print(f"  ✓ cleared {PENDING.name}")

    if args.build:
        print("\n=== Triggering FAISS rebuild ===")
        print("REMINDER: set CUDA_VISIBLE_DEVICES=0 for GPU slot 1 only.")
        rc = subprocess.call([sys.executable, str(BUILDER)])
        if rc != 0:
            print(f"  ✗ build failed (rc={rc})", file=sys.stderr)
            return rc
    else:
        print("\nNext step: rebuild FAISS index (GPU work, slot 1 only):")
        print("    export CUDA_VISIBLE_DEVICES=0")
        print(f"    python3 {BUILDER.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
