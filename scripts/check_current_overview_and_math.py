#!/usr/bin/env python3
"""Verify current RC3.3 overview and mathematical doctrine placement."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SYSTEM_OVERVIEW = ROOT / "docs" / "current" / "MMV_SYSTEM_OVERVIEW_RC3_3.md"
MATH_DOCTRINE = ROOT / "docs" / "current" / "MMV_MATHEMATICAL_MODELING_DOCTRINE_RC3_3.md"
BOX0_MANIFEST = ROOT / "data" / "box_0" / "index_manifest.json"
BOXA_MANIFEST = ROOT / "data" / "box_a" / "index_manifest.json"
ME5_NAME = "intfloat/multilingual-e5-large"


def _manifest_files(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return set((data.get("files") or {}).keys())


def _manifest_model(path: Path) -> str | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("model")


def main() -> int:
    checks = [
        ("system overview doc exists", SYSTEM_OVERVIEW.exists()),
        ("math doctrine doc exists", MATH_DOCTRINE.exists()),
        (
            "system overview is RC3.3 / L0 v8.4 aware",
            SYSTEM_OVERVIEW.exists()
            and "MMV-S-RC3.3" in SYSTEM_OVERVIEW.read_text(encoding="utf-8")
            and "L0 v8.4" in SYSTEM_OVERVIEW.read_text(encoding="utf-8"),
        ),
        (
            "math doctrine has current route set",
            MATH_DOCTRINE.exists()
            and "date_bound_answer" in MATH_DOCTRINE.read_text(encoding="utf-8")
            and "re_anchor" in MATH_DOCTRINE.read_text(encoding="utf-8")
            and "explore` is not a Core route" in MATH_DOCTRINE.read_text(encoding="utf-8"),
        ),
        (
            "Box 0 manifest contains current system overview",
            "MMV_SYSTEM_OVERVIEW_RC3_3.md" in _manifest_files(BOX0_MANIFEST),
        ),
        (
            "Box A manifest contains current system overview",
            "MMV_SYSTEM_OVERVIEW_RC3_3.md" in _manifest_files(BOXA_MANIFEST),
        ),
        (
            "Box A manifest contains current math doctrine source",
            "MMV_Mathematical_Modeling_Doctrine_and_Formalism_EN.md"
            in _manifest_files(BOXA_MANIFEST),
        ),
        (
            "Box A manifest records ME5-large",
            _manifest_model(BOXA_MANIFEST) == ME5_NAME,
        ),
    ]

    ok = True
    for label, passed in checks:
        print(f"[{'OK' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
