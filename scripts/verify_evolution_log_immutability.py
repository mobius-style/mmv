#!/usr/bin/env python3
"""
verify_evolution_log_immutability.py

Verifies that data/supervisor/evolution_log.jsonl has not been modified for
existing entries — only appended to.

Method:
  1. On first run, record md5 of all existing lines except the last (newest)
  2. On subsequent runs, recompute and compare
  3. New entries can only be appended (line count grows by N, hash of first
     (count - N) lines must match stored hash)

Stored state: data/supervisor/.evolution_log_first_n_hash

Exit codes:
  0  Immutability verified
  1  Existing entries modified (drift detected)
  2  Cannot verify (file missing)
"""
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVOLUTION_LOG = REPO_ROOT / "data" / "supervisor" / "evolution_log.jsonl"
HASH_FILE = REPO_ROOT / "data" / "supervisor" / ".evolution_log_first_n_hash"

def main():
    if not EVOLUTION_LOG.exists():
        print(f"ERROR: {EVOLUTION_LOG} not found", file=sys.stderr)
        return 2

    lines = EVOLUTION_LOG.read_text().splitlines()
    if not lines:
        print("Evolution Log empty — nothing to verify")
        return 0

    if len(lines) == 1:
        # Only one entry. Record it as the immutable state.
        text = lines[0] + "\n"
        h = hashlib.md5(text.encode()).hexdigest()
        HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HASH_FILE.write_text(json.dumps({"hash": h, "count": 1}))
        print(f"Bootstrapped: 1 entry, hash {h}")
        return 0

    # Hash all lines (we'll verify that count >= stored_count and prefix matches)
    full_text = "\n".join(lines) + "\n"

    if not HASH_FILE.exists():
        # First run: record everything except last as immutable
        prefix_text = "\n".join(lines[:-1]) + "\n"
        prefix_hash = hashlib.md5(prefix_text.encode()).hexdigest()
        HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HASH_FILE.write_text(json.dumps({
            "hash": prefix_hash,
            "count": len(lines) - 1,
        }))
        print(f"Bootstrapped: first {len(lines) - 1} entries, hash {prefix_hash}")
        return 0

    try:
        stored = json.loads(HASH_FILE.read_text())
        stored_hash = stored["hash"]
        stored_count = stored["count"]
    except (json.JSONDecodeError, OSError, KeyError) as e:
        print(f"ERROR: Cannot read hash file: {e}", file=sys.stderr)
        return 2

    # Current line count must be >= stored_count (only appends allowed)
    if len(lines) < stored_count:
        print(f"FAIL: Line count decreased ({len(lines)} < stored {stored_count})", file=sys.stderr)
        return 1

    # Hash of the first stored_count lines must match
    prefix_text = "\n".join(lines[:stored_count]) + "\n"
    current_prefix_hash = hashlib.md5(prefix_text.encode()).hexdigest()

    if current_prefix_hash != stored_hash:
        print(f"FAIL: First {stored_count} lines hash drift", file=sys.stderr)
        print(f"  stored:  {stored_hash}", file=sys.stderr)
        print(f"  current: {current_prefix_hash}", file=sys.stderr)
        return 1

    # Update stored state to reflect current N-1 lines (one line behind)
    # This way each run protects all-but-the-newest entry
    if len(lines) > stored_count:
        new_prefix_text = "\n".join(lines[:-1]) + "\n"
        new_prefix_hash = hashlib.md5(new_prefix_text.encode()).hexdigest()
        HASH_FILE.write_text(json.dumps({
            "hash": new_prefix_hash,
            "count": len(lines) - 1,
        }))
        print(f"PASS: First {stored_count} entries unchanged. Updated stored hash to first {len(lines) - 1} entries.")
    else:
        print(f"PASS: First {stored_count} entries unchanged.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
