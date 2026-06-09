#!/usr/bin/env python3
"""
merge_qk_results.py — Merge dual-worker QK response files.

Deduplicates by (wall_ball_id, qk_id).
Also merges per-worker checkpoints into shared checkpoint.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
MDIR = ROOT / "data" / "measurement"
CKPT = MDIR / "checkpoints"

def main():
    # Merge response files
    seen = set()
    merged = []

    for fname in ["qk_responses.jsonl",
                  "qk_responses_w0.jsonl",
                  "qk_responses_w1.jsonl"]:
        fpath = MDIR / fname
        if not fpath.exists():
            print(f"  Skip (not found): {fname}")
            continue
        count = 0
        for line in open(fpath, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            key = (r["wall_ball_id"], r["qk_id"])
            if key not in seen:
                seen.add(key)
                merged.append(r)
                count += 1
        print(f"  Loaded {count} unique from {fname}")

    out = MDIR / "qk_responses.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n  Merged: {len(merged)} unique pairs → {out.name}")

    # Merge checkpoints
    combined = {}
    for fname in ["qk_done.json", "qk_done_w0.json", "qk_done_w1.json"]:
        fpath = CKPT / fname
        if not fpath.exists():
            continue
        d = json.load(open(fpath))
        for wid, qks in d.items():
            combined.setdefault(wid, [])
            for qk in qks:
                if qk not in combined[wid]:
                    combined[wid].append(qk)
        print(f"  Checkpoint {fname}: {sum(len(v) for v in d.values())} pairs")

    with open(CKPT / "qk_done.json", "w") as f:
        json.dump(combined, f, ensure_ascii=False)
    total = sum(len(v) for v in combined.values())
    print(f"\n  Combined checkpoint: {total} pairs → qk_done.json")


if __name__ == "__main__":
    print("=== Merging QK Results ===")
    main()
    print("\n=== Done ===")
