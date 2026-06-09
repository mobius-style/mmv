#!/usr/bin/env python3
"""Verify that Box 0 contains the current L0 v8.4 authority files."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "box_0" / "index_manifest.json"

REQUIRED = {
    "MMV_SYSTEM_OVERVIEW_RC3_3.md",
    "l0_integrated_v8_4.md",
    "mobius_l0_v8_4_protocol.json",
}

HISTORICAL_SUBSTRATE = {
    "l0_integrated_v8_2.md",
}


def main() -> int:
    if not MANIFEST.exists():
        print(f"[FAIL] Missing Box 0 manifest: {MANIFEST}")
        return 1

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = set((data.get("files") or {}).keys())

    ok = True
    for name in sorted(REQUIRED):
        passed = name in files
        print(f"[{'OK' if passed else 'FAIL'}] current authority in Box 0: {name}")
        ok = ok and passed

    for name in sorted(HISTORICAL_SUBSTRATE):
        passed = name in files
        print(f"[{'OK' if passed else 'FAIL'}] inherited substrate retained: {name}")
        ok = ok and passed

    print(f"[INFO] chunk_count={data.get('chunk_count')} model={data.get('model')}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
