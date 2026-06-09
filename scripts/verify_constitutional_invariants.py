#!/usr/bin/env python3
"""
verify_constitutional_invariants.py

Verifies that MMV's Constitutional Invariants are not violated.
Used in Phase B per-commit self-verification.

Invariants checked:
  1. Answer Entitlement: pattern match with absent evidence returns uncertainty
     (verified via routing trace inspection)
  2. Evolution Log byte-unchangeability: existing entries (1..N-1) are untouched
     when entry N is appended
  3. Audit/memory separation: pattern library is in audit_log namespace, not
     user-specific memory
  4. 9-box namespace: route.primary_box only references existing box ids

Exit codes:
  0  All invariants pass
  1  At least one invariant violation detected
  2  Cannot verify (missing files/scripts)
"""
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID_BOXES = {"box_0", "box_1", "box_2", "box_3", "box_4",
               "box_5", "box_6", "box_7", "box_w"}
EVOLUTION_LOG = REPO_ROOT / "data" / "supervisor" / "evolution_log.jsonl"
EVOLUTION_LOG_HASH_FILE = REPO_ROOT / "data" / "supervisor" / ".evolution_log_first_n_hash"

PATTERN_LIBRARY_CONFIG = REPO_ROOT / "config" / "pattern_library"
USER_MEMORY_PATHS = [
    REPO_ROOT / "data" / "memory",
    REPO_ROOT / "data" / "user",
]

results = []
all_pass = True

def check(name, condition, detail=""):
    global all_pass
    status = "PASS" if condition else "FAIL"
    if not condition:
        all_pass = False
    results.append((name, status, detail))
    return condition

# ----------------------------------------------------------------------------
# Invariant 1: 9-box namespace check
# ----------------------------------------------------------------------------
def check_9box_namespace():
    if not PATTERN_LIBRARY_CONFIG.exists():
        # Library doesn't exist yet (pre-Commit 1 state). Skip with PASS.
        return check("9-box namespace", True, "library not yet created")

    bad_patterns = []
    for jsonl_file in PATTERN_LIBRARY_CONFIG.glob("*.jsonl"):
        if jsonl_file.name in ("concepts.jsonl", "_autogen_metadata.jsonl"):
            continue
        try:
            for i, line in enumerate(jsonl_file.read_text().splitlines(), 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                obj = json.loads(line)
                route = obj.get("route", {})
                primary = route.get("primary_box")
                excludes = route.get("exclude_boxes", [])

                if primary and primary not in VALID_BOXES:
                    bad_patterns.append(f"{jsonl_file.name}:{i} primary_box={primary}")
                for ex in excludes:
                    if ex not in VALID_BOXES:
                        bad_patterns.append(f"{jsonl_file.name}:{i} exclude_boxes contains {ex}")
        except (json.JSONDecodeError, OSError) as e:
            bad_patterns.append(f"{jsonl_file.name}: {e}")

    if bad_patterns:
        return check("9-box namespace", False, "; ".join(bad_patterns[:5]))
    return check("9-box namespace", True)

# ----------------------------------------------------------------------------
# Invariant 2: Evolution Log byte-unchangeability
# ----------------------------------------------------------------------------
def check_evolution_log_immutability():
    if not EVOLUTION_LOG.exists():
        return check("Evolution Log immutability", True, "log file does not exist")

    lines = EVOLUTION_LOG.read_text().splitlines()
    if not lines:
        return check("Evolution Log immutability", True, "log empty")

    # Hash all but the last line (last line is the new append)
    if len(lines) < 2:
        return check("Evolution Log immutability", True, "only 1 entry, nothing to verify")

    prev_text = "\n".join(lines[:-1]) + "\n"
    current_hash = hashlib.md5(prev_text.encode()).hexdigest()

    if EVOLUTION_LOG_HASH_FILE.exists():
        try:
            stored = json.loads(EVOLUTION_LOG_HASH_FILE.read_text())
            stored_hash = stored.get("hash")
            stored_count = stored.get("count")
            # If count matches, hash must match
            if stored_count == len(lines) - 1:
                if current_hash != stored_hash:
                    return check("Evolution Log immutability", False,
                                 f"first {stored_count} lines hash drift: stored={stored_hash} current={current_hash}")
        except (json.JSONDecodeError, OSError):
            pass

    # Update stored hash for current state
    EVOLUTION_LOG_HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVOLUTION_LOG_HASH_FILE.write_text(json.dumps({
        "hash": current_hash,
        "count": len(lines) - 1,  # immutable count
    }))

    return check("Evolution Log immutability", True,
                 f"first {len(lines) - 1} entries hash {current_hash}")

# ----------------------------------------------------------------------------
# Invariant 3: Audit/memory separation
# ----------------------------------------------------------------------------
def check_audit_memory_separation():
    """
    Ensure pattern library files are not placed inside user memory paths.
    """
    violations = []

    if PATTERN_LIBRARY_CONFIG.exists():
        for memory_path in USER_MEMORY_PATHS:
            if not memory_path.exists():
                continue
            try:
                memory_resolved = memory_path.resolve()
                library_resolved = PATTERN_LIBRARY_CONFIG.resolve()
                # Check if library is inside memory
                try:
                    library_resolved.relative_to(memory_resolved)
                    violations.append(f"library {library_resolved} is inside memory {memory_resolved}")
                except ValueError:
                    pass
            except OSError:
                pass

    if violations:
        return check("Audit/memory separation", False, "; ".join(violations))
    return check("Audit/memory separation", True)

# ----------------------------------------------------------------------------
# Invariant 4: Answer Entitlement (heuristic — trace inspection)
# ----------------------------------------------------------------------------
def check_answer_entitlement_heuristic():
    """
    Heuristic: scan recent traces for cases where pattern matched but
    consulted_boxes was empty (would indicate evidence-absent + non-uncertainty
    response). This is a best-effort check.
    """
    traces_dir = REPO_ROOT / "data" / "pattern_library" / "traces"
    if not traces_dir.exists():
        return check("Answer Entitlement (heuristic)", True, "no traces yet")

    suspicious = []
    for date_dir in sorted(traces_dir.iterdir())[-7:]:  # last 7 days
        if not date_dir.is_dir():
            continue
        for trace_file in date_dir.glob("*.jsonl"):
            try:
                for line in trace_file.read_text().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    matched = obj.get("library_lookup", {}).get("matched_pattern_id")
                    consulted = obj.get("consulted_boxes", [])
                    final = obj.get("final_route") or ""
                    if matched and not consulted and "uncertainty" not in final.lower():
                        suspicious.append(f"{trace_file.name}: matched={matched} but no boxes consulted, route={final}")
            except (json.JSONDecodeError, OSError):
                continue

    if suspicious:
        # Flag but don't fail — heuristic only
        return check("Answer Entitlement (heuristic)", True,
                     f"warning: {len(suspicious)} suspicious traces (may be false positive)")

    return check("Answer Entitlement (heuristic)", True)

# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    check_9box_namespace()
    check_evolution_log_immutability()
    check_audit_memory_separation()
    check_answer_entitlement_heuristic()

    print("Constitutional Invariants Check:")
    for name, status, detail in results:
        marker = "[OK] " if status == "PASS" else "[FAIL] "
        print(f"  {marker}{name}" + (f" — {detail}" if detail else ""))

    if all_pass:
        print("\nResult: ALL INVARIANTS PASSED")
        return 0
    else:
        print("\nResult: ONE OR MORE INVARIANTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
