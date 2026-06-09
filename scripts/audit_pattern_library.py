#!/usr/bin/env python3
"""audit_pattern_library.py — Phase 3 Commit 35.

Lifecycle audit pipeline (lite). Manual-trigger script that:
1. Reads all patterns from `config/pattern_library/*.jsonl`.
2. Computes a health snapshot — total / by-topic / by-status /
   hit-count percentile bands / origin breakdown.
3. Flags deprecation candidates by heuristic:
   - hit_count == 0 AND created > 60 days ago AND audit_status == active
   - last_xling_pass_rate < 0.5 (when measured)
4. Writes a structured report to `data/pattern_library/audit/`
   with both a machine-readable JSON and a human-readable Markdown.

Spec ref: docs/PATTERN_LIBRARY_SPEC_v1_4.md §5.4.3 + §4.3 (stage 3
Secretary feed) + §7.6 (audit / memory separation — audit only,
NEVER mutates the library).

This is the "lite" version: read-only, no proposal generation, no
deletion. The Secretary proposal generator (Commit 37) consumes
this output as one of its trigger sources.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config" / "pattern_library"
AUDIT_DIR = REPO_ROOT / "data" / "pattern_library" / "audit"

DEFAULT_DEPRECATION_AGE_DAYS = 60
DEFAULT_XLING_PASS_RATE_FLOOR = 0.5

sys.path.insert(0, str(REPO_ROOT))


def _load_patterns(config_dir: Path) -> list[dict]:
    patterns: list[dict] = []
    for jsonl in sorted(config_dir.glob("*.jsonl")):
        if jsonl.name.startswith("_"):
            continue
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                patterns.append(json.loads(line))
    return patterns


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * p
    lo = int(rank)
    frac = rank - lo
    if lo + 1 < len(sorted_values):
        return float(sorted_values[lo]
                     + frac * (sorted_values[lo + 1] - sorted_values[lo]))
    return float(sorted_values[-1])


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def compute_audit(
    patterns: list[dict],
    now: datetime | None = None,
    deprecation_age_days: int = DEFAULT_DEPRECATION_AGE_DAYS,
    xling_floor: float = DEFAULT_XLING_PASS_RATE_FLOOR,
) -> dict:
    """Run the audit pass over all loaded patterns. Returns a dict
    suitable for JSON / Markdown rendering. Pure (no I/O)."""
    now = now or datetime.now(timezone.utc)
    threshold_date = now - timedelta(days=deprecation_age_days)

    by_topic: Counter = Counter()
    by_audit_status: Counter = Counter()
    by_origin: Counter = Counter()
    hits = []
    deprecation_candidates: list[dict] = []
    xling_floor_violations: list[dict] = []
    for p in patterns:
        topic = p.get("topic", "?")
        by_topic[topic] += 1

        lifecycle = p.get("lifecycle") or {}
        status = lifecycle.get("audit_status", "active") if isinstance(
            lifecycle, dict
        ) else "active"
        by_audit_status[status] += 1

        origin = (p.get("origin") or {}).get("type", "?") if isinstance(
            p.get("origin"), dict
        ) else "?"
        by_origin[origin] += 1

        hit_count = (
            int(lifecycle.get("hit_count", 0))
            if isinstance(lifecycle, dict) else 0
        )
        hits.append(hit_count)

        # Deprecation candidate heuristic
        created_date = _parse_date(
            (p.get("origin") or {}).get("date") if isinstance(
                p.get("origin"), dict
            ) else None
        )
        is_old = (
            created_date is not None and created_date < threshold_date
        )
        is_active_status = status == "active"
        if (hit_count == 0 and is_old and is_active_status):
            deprecation_candidates.append({
                "id": p.get("id"),
                "topic": topic, "intent": p.get("intent"),
                "age_days": (now - created_date).days if created_date else None,
                "reason": "no_hits_after_60_days",
            })

        # Cross-lingual pass-rate floor
        xling_rate = lifecycle.get("last_xling_pass_rate") if isinstance(
            lifecycle, dict
        ) else None
        if xling_rate is not None and xling_rate < xling_floor:
            xling_floor_violations.append({
                "id": p.get("id"),
                "topic": topic, "intent": p.get("intent"),
                "xling_pass_rate": xling_rate,
            })

    sorted_hits = sorted(hits)
    return {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "total_patterns": len(patterns),
        "by_topic": dict(by_topic),
        "by_audit_status": dict(by_audit_status),
        "by_origin": dict(by_origin),
        "hit_count_summary": {
            "total_hits": sum(hits),
            "patterns_with_hits": sum(1 for h in hits if h > 0),
            "p50": _percentile(sorted_hits, 0.5),
            "p75": _percentile(sorted_hits, 0.75),
            "p95": _percentile(sorted_hits, 0.95),
            "max": max(hits) if hits else 0,
        },
        "deprecation_candidates": deprecation_candidates,
        "deprecation_candidates_count": len(deprecation_candidates),
        "xling_floor_violations": xling_floor_violations,
        "xling_floor_violations_count": len(xling_floor_violations),
        "config": {
            "deprecation_age_days": deprecation_age_days,
            "xling_floor": xling_floor,
        },
    }


def render_markdown(audit: dict) -> str:
    lines = [
        "# Pattern Library Audit Report",
        "",
        f"**Generated**: {audit['generated_at']}",
        f"**Total patterns**: {audit['total_patterns']}",
        "",
        "## Composition",
        "",
        "### By topic",
        "",
    ]
    for topic, n in sorted(audit["by_topic"].items(),
                            key=lambda kv: -kv[1]):
        lines.append(f"- {topic}: {n}")
    lines.extend(["", "### By audit_status", ""])
    for status, n in sorted(audit["by_audit_status"].items()):
        lines.append(f"- {status}: {n}")
    lines.extend(["", "### By origin", ""])
    for origin, n in sorted(audit["by_origin"].items()):
        lines.append(f"- {origin}: {n}")

    h = audit["hit_count_summary"]
    lines.extend([
        "", "## Hit-count summary", "",
        f"- Total hits: {h['total_hits']}",
        f"- Patterns with ≥1 hit: {h['patterns_with_hits']} / "
        f"{audit['total_patterns']}",
        f"- p50: {h['p50']:.1f}",
        f"- p75: {h['p75']:.1f}",
        f"- p95: {h['p95']:.1f}",
        f"- max: {h['max']}",
    ])

    cand = audit["deprecation_candidates"]
    lines.extend([
        "", "## Deprecation candidates "
        f"({len(cand)})", "",
        f"Heuristic: hit_count == 0 AND created > "
        f"{audit['config']['deprecation_age_days']} days AND "
        f"audit_status == active.",
        "",
    ])
    if cand:
        lines.append("| id | topic | intent | age_days | reason |")
        lines.append("|---|---|---|---|---|")
        for c in cand:
            lines.append(
                f"| {c['id']} | {c['topic']} | {c.get('intent', '?')} | "
                f"{c.get('age_days')} | {c.get('reason')} |"
            )
    else:
        lines.append("_None._")

    xl = audit["xling_floor_violations"]
    lines.extend([
        "", "## Cross-lingual pass-rate floor violations "
        f"({len(xl)})", "",
        f"Floor: {audit['config']['xling_floor']}",
        "",
    ])
    if xl:
        lines.append("| id | topic | xling_pass_rate |")
        lines.append("|---|---|---|")
        for v in xl:
            lines.append(
                f"| {v['id']} | {v['topic']} | "
                f"{v['xling_pass_rate']:.2f} |"
            )
    else:
        lines.append("_None._")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pattern Library lifecycle audit (lite)"
    )
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR)
    parser.add_argument("--output-dir", type=Path, default=AUDIT_DIR)
    parser.add_argument("--age-days", type=int,
                        default=DEFAULT_DEPRECATION_AGE_DAYS,
                        help="Deprecation candidate age threshold")
    parser.add_argument("--xling-floor", type=float,
                        default=DEFAULT_XLING_PASS_RATE_FLOOR,
                        help="Cross-lingual pass rate floor")
    parser.add_argument("--print", action="store_true",
                        help="Print Markdown report to stdout (no file)")
    args = parser.parse_args()

    patterns = _load_patterns(args.config_dir)
    audit = compute_audit(
        patterns,
        deprecation_age_days=args.age_days,
        xling_floor=args.xling_floor,
    )

    md = render_markdown(audit)
    if args.print:
        print(md)
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = args.output_dir / f"audit_{stamp}.json"
    md_path = args.output_dir / f"audit_{stamp}.md"
    json_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    md_path.write_text(md, encoding="utf-8")
    print(f"Audit written to:")
    print(f"  {json_path}")
    print(f"  {md_path}")
    print(f"\nSummary: total={audit['total_patterns']}, "
          f"deprecation_candidates={audit['deprecation_candidates_count']}, "
          f"total_hits={audit['hit_count_summary']['total_hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
