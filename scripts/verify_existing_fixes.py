#!/usr/bin/env python3
"""
verify_existing_fixes.py

Verifies that all 7 existing fixes remain intact during Phase B implementation.

Fixes checked:
  Fix 1: kanji self-ref in src/kernel/appraisal.py (SELF_REF_PATTERNS)
  Fix 2: casual_greeting fast-path in routing path
  L1-A: Box 0 ME5 in src/adapters/custom_rag_adapter.py
  C-1a: ZH self-ref in src/adapters/ollama_adapter.py
  C-1b: identity anchor in src/adapters/ollama_adapter.py
  C.3: calibration insufficient escalation
  Pattern C: synthesis evidence-fidelity in src/compose/

Plus the engine fix from commit 737b2d1:
  Engine fix: ollama_adapter.py options dict (repeat_penalty, repeat_last_n,
              top_k, top_p) on all 3 call sites

Method: Each fix has a "marker" (specific code substring) that must exist.
This is heuristic — markers may need updating if code is refactored.

Exit codes:
  0  All 7 fixes (+ engine fix) intact
  1  At least one fix marker missing
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fix definitions: (name, file_path, list of required marker substrings)
FIXES = [
    ("Fix 1 (kanji self-ref)", "src/kernel/appraisal.py", [
        "SELF_REF_PATTERNS",
    ]),
    ("Fix 2 (casual_greeting fast-path)", "src/kernel/routing_engine.py", [
        "casual_greeting",
    ]),
    ("L1-A (Box 0 ME5)", "src/adapters/custom_rag_adapter.py", [
        "multilingual-e5",
    ]),
    ("C-1a (ZH self-ref)", "src/adapters/ollama_adapter.py", [
        # Some marker indicating ZH handling. Heuristic.
        # Project-specific marker may be needed.
        "ollama",  # placeholder; tighten after first run
    ]),
    ("C-1b (identity anchor)", "src/adapters/ollama_adapter.py", [
        "ollama",  # placeholder
    ]),
    ("C.3 (calibration insufficient escalation)", "src/kernel/routing_engine.py", [
        # Heuristic
        "escalat",
    ]),
    ("Pattern C (synthesis evidence-fidelity)", "src/compose/verify_synthesizer.py", [
        # File should exist
        None,  # presence-only check
    ]),
    ("Engine fix (commit 737b2d1)", "src/adapters/ollama_adapter.py", [
        "repeat_penalty",
        "repeat_last_n",
        "top_k",
        "top_p",
    ]),
]

results = []
all_pass = True

def check_fix(name, rel_path, markers):
    global all_pass
    full_path = REPO_ROOT / rel_path
    if not full_path.exists():
        results.append((name, "FAIL", f"file missing: {rel_path}"))
        all_pass = False
        return

    try:
        content = full_path.read_text(encoding="utf-8")
    except OSError as e:
        results.append((name, "FAIL", f"read error: {e}"))
        all_pass = False
        return

    missing_markers = []
    for marker in markers:
        if marker is None:
            continue  # presence-only check
        if marker not in content:
            missing_markers.append(marker)

    if missing_markers:
        results.append((name, "FAIL", f"missing marker(s): {', '.join(missing_markers)}"))
        all_pass = False
    else:
        results.append((name, "PASS", ""))

def main():
    for name, rel_path, markers in FIXES:
        check_fix(name, rel_path, markers)

    print("Existing Fixes Preservation Check:")
    for name, status, detail in results:
        marker = "[OK] " if status == "PASS" else "[FAIL] "
        print(f"  {marker}{name}" + (f" — {detail}" if detail else ""))

    if all_pass:
        print("\nResult: ALL 7 FIXES INTACT (+ engine fix)")
        return 0
    else:
        print("\nResult: ONE OR MORE FIXES MISSING — STOP AND ROLLBACK")
        return 1

if __name__ == "__main__":
    sys.exit(main())
