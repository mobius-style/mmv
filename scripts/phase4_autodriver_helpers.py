#!/usr/bin/env python3
"""Phase 4 autodriver helpers — state management + handover doc parsing.

Subcommands:
  extract-trigger <handover.md>    -> stdout: self-trigger paste-block
  parse-state <handover.md>        -> stdout: JSON {head, active, quarantined, tokens_cumul, hard_stop_articulated}
  init-state <state.json>          -> create initial state
  read-state <state.json>          -> stdout: current state JSON
  update-state <state.json> --from-handover <handover.md>
                                   -> merge handover findings into state
  check-thresholds <state.json>    -> stdout: JSON {milestone_crossed, token_threshold_crossed, hard_stop, notify_actions}
  set-disabled <state.json> <bool> -> toggle disabled flag

The handover-doc contract (established cf15a5f):
  ## Self-trigger for next conversation
  Paste the following into a fresh Claude Code conversation to resume:
  ```
  <paste-block contents>
  ```
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PATTERN_MILESTONES = [1000, 3000, 5000, 10000]
TOKEN_NOTIFY_THRESHOLDS_M = [20, 40, 70]
TOKEN_HARD_STOP_M = 70

# Explicit machine-readable markers the handover-doc author opts into.
# Discussion of these phrases in prose is fine — only an exact match on
# its own line counts. Format examples:
#     AUTODRIVER_HARD_STOP: gpu_saturation_observed
#     AUTODRIVER_PHASE4_CLOSED: all_metrics_pass
#     AUTODRIVER_SYSTEMIC_BROKEN_COUNT: 3
HARD_STOP_MARKER = "AUTODRIVER_HARD_STOP:"
PHASE4_CLOSED_MARKER = "AUTODRIVER_PHASE4_CLOSED"
SYSTEMIC_BROKEN_MARKER = "AUTODRIVER_SYSTEMIC_BROKEN_COUNT:"


def find_latest_handover(docs_dir: Path) -> Path | None:
    """Return the most recently modified pattern-library handover doc."""
    candidates = list(docs_dir.glob("PATTERN_LIBRARY_PHASE4*HANDOVER.md"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


TRIGGER_START = "<!-- AUTODRIVER_TRIGGER_START -->"
TRIGGER_END = "<!-- AUTODRIVER_TRIGGER_END -->"


def extract_trigger(handover_md: Path) -> str:
    """Extract the self-trigger paste-block from the handover doc.

    The block lives between explicit HTML-comment markers
    `<!-- AUTODRIVER_TRIGGER_START -->` and `<!-- AUTODRIVER_TRIGGER_END -->`
    on their own lines. Markdown ``` fences inside the block are
    preserved verbatim (no nesting issues).
    """
    text = handover_md.read_text(encoding="utf-8")
    start = text.find(TRIGGER_START)
    if start == -1:
        raise ValueError(
            f"missing {TRIGGER_START} marker in {handover_md}; "
            f"add it before the paste-block."
        )
    end = text.find(TRIGGER_END, start)
    if end == -1:
        raise ValueError(
            f"missing {TRIGGER_END} marker after start in {handover_md}"
        )
    # Trim leading newline after the start marker, drop trailing whitespace
    body = text[start + len(TRIGGER_START):end]
    body = body.lstrip("\n").rstrip() + "\n"
    return body


def parse_state(handover_md: Path) -> dict:
    """Parse handover doc for: HEAD, active, quarantined, FAISS, tokens, hard_stop.

    Lines look like:
      - HEAD: e4c8c4a "..."
      - Active patterns: 125 (...)
      - Quarantined: 26 (...)
      - FAISS vectors: 1,128
      - Tokens cumul (this + prior conv): ~390K Groq of 50M ST1 budget = 0.78%
    """
    text = handover_md.read_text(encoding="utf-8")
    out: dict = {
        "handover_path": str(handover_md),
        "parsed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    m = re.search(r"-\s*HEAD:\s*([0-9a-f]{7,40})", text)
    if m:
        out["head"] = m.group(1)

    m = re.search(r"Active patterns?:\s*(\d+)", text)
    if m:
        out["active"] = int(m.group(1))

    m = re.search(r"Quarantined:\s*(\d+)", text)
    if m:
        out["quarantined"] = int(m.group(1))

    m = re.search(r"FAISS vectors?:\s*([\d,]+)", text)
    if m:
        out["faiss_vectors"] = int(m.group(1).replace(",", ""))

    # Tokens — capture absolute K/M then normalize to integer tokens
    m = re.search(r"Tokens?\s+cumul[^:]*:\s*~?([\d.]+)\s*([KM])\b", text)
    if m:
        n = float(m.group(1))
        unit = m.group(2)
        out["tokens_cumul"] = int(n * (1_000 if unit == "K" else 1_000_000))

    # Hard-stop articulation — only explicit machine-readable markers count.
    # Discussion of "hard stop" / "system down" in prose does NOT trigger.
    hard_stop_reasons: list[str] = []
    systemic_broken: int | None = None
    for line in text.splitlines():
        s = line.strip().lstrip("#- *>").strip()
        if s.startswith(HARD_STOP_MARKER):
            hard_stop_reasons.append(s[len(HARD_STOP_MARKER):].strip())
        if s.startswith(SYSTEMIC_BROKEN_MARKER):
            try:
                systemic_broken = int(s[len(SYSTEMIC_BROKEN_MARKER):].strip())
            except ValueError:
                pass

    if systemic_broken is not None and systemic_broken >= 3:
        hard_stop_reasons.append(
            f"systemic_broken_modules={systemic_broken} (>=3 ceiling)"
        )

    out["hard_stop_articulated"] = bool(hard_stop_reasons)
    out["hard_stop_reasons"] = hard_stop_reasons
    out["systemic_broken_count"] = systemic_broken

    # Phase 4 closure positive signal — explicit marker only.
    closed = False
    for line in text.splitlines():
        s = line.strip().lstrip("#- *>").strip()
        if s.startswith(PHASE4_CLOSED_MARKER):
            closed = True
            break
    out["phase4_closed"] = closed
    return out


def init_state(state_path: Path) -> dict:
    state = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "disabled": False,
        "disabled_reason": None,
        "last_invoke_utc": None,
        "last_handover": None,
        "head": None,
        "active": 0,
        "quarantined": 0,
        "faiss_vectors": 0,
        "tokens_cumul": 0,
        "milestones_notified": [],
        "token_thresholds_notified_m": [],
        "invoke_count": 0,
        "phase4_closed": False,
    }
    state_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return state


def read_state(state_path: Path) -> dict:
    if not state_path.exists():
        return init_state(state_path)
    return json.loads(state_path.read_text(encoding="utf-8"))


def write_state(state_path: Path, state: dict) -> None:
    state_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def update_state_from_handover(
    state_path: Path,
    handover_md: Path,
) -> tuple[dict, list[str]]:
    """Merge handover findings into state. Returns (new_state, notify_actions).

    notify_actions is a list of strings describing things the wrapper
    should send to the user (milestones crossed, thresholds crossed,
    hard-stop articulated).
    """
    state = read_state(state_path)
    findings = parse_state(handover_md)
    notify: list[str] = []

    prev_active = state.get("active", 0)
    prev_tokens = state.get("tokens_cumul", 0)

    # Update HEAD/active/etc. only if newer
    for key in ("head", "active", "quarantined", "faiss_vectors", "tokens_cumul"):
        if key in findings:
            state[key] = findings[key]
    state["last_handover"] = findings["handover_path"]
    state["last_invoke_utc"] = findings["parsed_at_utc"]
    state["invoke_count"] = state.get("invoke_count", 0) + 1
    state["phase4_closed"] = findings.get("phase4_closed", False)

    # Milestone crossings
    new_active = state.get("active", prev_active)
    notified = set(state.get("milestones_notified", []))
    for mile in PATTERN_MILESTONES:
        if prev_active < mile <= new_active and mile not in notified:
            notify.append(f"MILESTONE: active patterns crossed {mile} ({prev_active} → {new_active})")
            notified.add(mile)
    state["milestones_notified"] = sorted(notified)

    # Token threshold crossings
    new_tokens = state.get("tokens_cumul", prev_tokens)
    notified_thr = set(state.get("token_thresholds_notified_m", []))
    for thr_m in TOKEN_NOTIFY_THRESHOLDS_M:
        thr = thr_m * 1_000_000
        if prev_tokens < thr <= new_tokens and thr_m not in notified_thr:
            notify.append(f"TOKEN THRESHOLD: cumul crossed {thr_m}M ({prev_tokens:,} → {new_tokens:,})")
            notified_thr.add(thr_m)
    state["token_thresholds_notified_m"] = sorted(notified_thr)

    # Hard stop checks
    if findings.get("hard_stop_articulated"):
        reasons = findings.get("hard_stop_reasons") or []
        notify.append(
            "HARD STOP marker found in handover: " + "; ".join(reasons)
        )
        state["disabled"] = True
        state["disabled_reason"] = "hard_stop_articulated: " + "; ".join(reasons)
    if new_tokens >= TOKEN_HARD_STOP_M * 1_000_000:
        notify.append(
            f"HARD STOP: tokens cumul {new_tokens:,} >= "
            f"{TOKEN_HARD_STOP_M}M ceiling — autodriver disabled"
        )
        state["disabled"] = True
        state["disabled_reason"] = f"tokens_cumul_exceeded_{TOKEN_HARD_STOP_M}M"
    if findings.get("phase4_closed"):
        notify.append("PHASE 4 CLOSED — autodriver disabled")
        state["disabled"] = True
        state["disabled_reason"] = "phase4_closed"

    write_state(state_path, state)
    return state, notify


def check_thresholds(state_path: Path) -> dict:
    state = read_state(state_path)
    out = {
        "disabled": state.get("disabled", False),
        "disabled_reason": state.get("disabled_reason"),
        "active": state.get("active", 0),
        "tokens_cumul": state.get("tokens_cumul", 0),
        "phase4_closed": state.get("phase4_closed", False),
    }
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract-trigger")
    e.add_argument("handover", type=Path)

    ps = sub.add_parser("parse-state")
    ps.add_argument("handover", type=Path)

    init = sub.add_parser("init-state")
    init.add_argument("state", type=Path)

    rs = sub.add_parser("read-state")
    rs.add_argument("state", type=Path)

    us = sub.add_parser("update-state")
    us.add_argument("state", type=Path)
    us.add_argument("--from-handover", required=True, type=Path,
                    dest="from_handover")

    ct = sub.add_parser("check-thresholds")
    ct.add_argument("state", type=Path)

    sd = sub.add_parser("set-disabled")
    sd.add_argument("state", type=Path)
    sd.add_argument("disabled", choices=["true", "false"])
    sd.add_argument("--reason", default="manual")

    fl = sub.add_parser("find-latest-handover")
    fl.add_argument("docs_dir", type=Path)

    args = p.parse_args()

    if args.cmd == "extract-trigger":
        sys.stdout.write(extract_trigger(args.handover))
        return 0
    if args.cmd == "parse-state":
        print(json.dumps(parse_state(args.handover), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "init-state":
        st = init_state(args.state)
        print(json.dumps(st, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "read-state":
        print(json.dumps(read_state(args.state), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "update-state":
        st, notes = update_state_from_handover(args.state, args.from_handover)
        print(json.dumps({"state": st, "notify": notes}, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "check-thresholds":
        print(json.dumps(check_thresholds(args.state), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "set-disabled":
        st = read_state(args.state)
        st["disabled"] = (args.disabled == "true")
        st["disabled_reason"] = args.reason if st["disabled"] else None
        write_state(args.state, st)
        print(json.dumps({"disabled": st["disabled"], "reason": st["disabled_reason"]}))
        return 0
    if args.cmd == "find-latest-handover":
        h = find_latest_handover(args.docs_dir)
        if h is None:
            print("", end="")
            return 1
        print(str(h))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
