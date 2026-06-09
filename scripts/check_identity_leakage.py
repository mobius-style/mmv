#!/usr/bin/env python3
"""
check_identity_leakage.py

Checks the most recent 33-scenario harness run for identity leakage tokens.

Identity leakage = response contains markers that should never appear:
  - System / role tokens (system:, assistant:, user:)
  - Internal model identifiers leaking
  - Internal box names appearing literally in user-facing response

Method:
  1. Look for the most recent scenario run output (or accept --output FILE)
  2. Scan responses for forbidden tokens
  3. Report count

Exit codes:
  0  No leakage detected
  1  Leakage detected (any > 0)
  2  Cannot find scenario run output
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Forbidden tokens in user-facing responses
FORBIDDEN_TOKENS = [
    r"\bsystem:",
    r"\bassistant:",
    r"\buser:",
    r"\bbox_[0-9w]\b",
    r"\bqwen3",  # internal model name in response
    r"\bllama3",
    r"\b<\|im_start\|>",
    r"\b<\|im_end\|>",
    r"\b\[INST\]",
    r"\b\[/INST\]",
]

def find_latest_run_output():
    """Find the most recent scenario run JSON output."""
    candidates = [
        REPO_ROOT / "data" / "supervisor" / "latest_run.json",
        REPO_ROOT / "data" / "supervisor" / "scenario_runs",
    ]

    for c in candidates:
        if c.is_file():
            return c
        if c.is_dir():
            jsons = sorted(c.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if jsons:
                return jsons[0]

    # Fall back to /tmp
    tmp_jsons = sorted(Path("/tmp").glob("*scenario*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if tmp_jsons:
        return tmp_jsons[0]
    tmp_jsons = sorted(Path("/tmp").glob("*33scenario*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if tmp_jsons:
        return tmp_jsons[0]

    return None

def scan_for_leakage(text):
    """Return list of leaked tokens found."""
    found = []
    for pattern in FORBIDDEN_TOKENS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            found.append(m.group())
    return found

def extract_responses(data):
    """Extract response texts from various possible JSON shapes."""
    responses = []

    if isinstance(data, dict):
        # Look for common keys
        for key in ("responses", "results", "scenarios", "data"):
            if key in data:
                inner = data[key]
                if isinstance(inner, list):
                    responses.extend(extract_responses(inner))
                elif isinstance(inner, dict):
                    responses.extend(extract_responses(inner))

        # Look for direct response field
        for key in ("response", "output", "text", "content"):
            if key in data and isinstance(data[key], str):
                responses.append(data[key])

        # Recurse into all dict values
        for v in data.values():
            if isinstance(v, (dict, list)):
                responses.extend(extract_responses(v))

    elif isinstance(data, list):
        for item in data:
            responses.extend(extract_responses(item))

    return responses

def main():
    parser = argparse.ArgumentParser(description="Check identity leakage in scenario run")
    parser.add_argument("--output", type=Path, help="Specific scenario run output JSON")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    target = args.output if args.output else find_latest_run_output()

    if target is None or not target.exists():
        print("ERROR: Cannot find scenario run output", file=sys.stderr)
        print("       Tried: data/supervisor/latest_run.json, data/supervisor/scenario_runs/, /tmp/*scenario*.json", file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"[check_identity_leakage] Scanning: {target}")

    try:
        data = json.loads(target.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: Cannot parse {target}: {e}", file=sys.stderr)
        return 2

    responses = extract_responses(data)

    total_leaks = 0
    leak_summary = {}
    for resp in responses:
        if not isinstance(resp, str):
            continue
        leaks = scan_for_leakage(resp)
        for leak in leaks:
            leak_summary[leak] = leak_summary.get(leak, 0) + 1
            total_leaks += 1

    if not args.quiet:
        print(f"identity_leakage: {total_leaks}")
        if leak_summary:
            print("Breakdown:")
            for token, count in sorted(leak_summary.items(), key=lambda x: -x[1]):
                print(f"  {token}: {count}")

    if total_leaks > 0:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
