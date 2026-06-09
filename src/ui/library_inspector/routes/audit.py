"""routes/audit.py — Audit Log page (`/audit`).

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.4.7 +
Phase 2 Commit 22 dashboard expansion (spec v1.3 Section 5.6.4 + 5.6.6)."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, render_template, request

from ..lib.trace_reader import TraceReader

bp = Blueprint("audit", __name__)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
AUDIT_LOG_DIR = REPO_ROOT / "data" / "pattern_library" / "audit_log"


def _origin_breakdown(patterns) -> dict[str, int]:
    c: Counter = Counter()
    for p in patterns:
        c[p.origin.type] += 1
    return dict(c)


def _hit_count_histogram(patterns) -> list[tuple[str, int]]:
    """Bucket patterns by hit_count for histogram display."""
    buckets = [
        ("0", 0), ("1-9", 0), ("10-99", 0),
        ("100-999", 0), ("1000+", 0),
    ]
    by_label = {b[0]: 0 for b in buckets}
    for p in patterns:
        c = p.lifecycle.hit_count
        if c == 0:
            label = "0"
        elif c < 10:
            label = "1-9"
        elif c < 100:
            label = "10-99"
        elif c < 1000:
            label = "100-999"
        else:
            label = "1000+"
        by_label[label] += 1
    return [(k, by_label[k]) for k in
            ("0", "1-9", "10-99", "100-999", "1000+")]


def _library_size_growth(patterns) -> list[tuple[str, int]]:
    """Cumulative pattern count by creation date (lifecycle.history
    entries with event='created')."""
    by_date: dict[str, int] = defaultdict(int)
    for p in patterns:
        for h in p.lifecycle.history:
            if h.event == "created":
                date_key = h.timestamp.strftime("%Y-%m-%d")
                by_date[date_key] += 1
                break
    cum = 0
    out: list[tuple[str, int]] = []
    for d in sorted(by_date):
        cum += by_date[d]
        out.append((d, cum))
    return out


def _autogen_batch_summary() -> list[dict]:
    """Aggregate audit log files for autogen batches: id, summary
    metrics, decision."""
    if not AUDIT_LOG_DIR.exists():
        return []
    out: list[dict] = []
    for fp in sorted(AUDIT_LOG_DIR.glob("autogen_*.summary.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "batch_id": data.get("batch_id"),
            "started_at": data.get("started_at"),
            "patterns_count": len(data.get("patterns", [])),
            "examples_added": sum(
                p.get("examples_added", 0)
                for p in data.get("patterns", [])
            ),
            "primary_used_count": sum(
                1 for p in data.get("patterns", [])
                if p.get("primary_used")
            ),
        })
    out.sort(key=lambda d: d.get("started_at", ""), reverse=True)
    return out[:30]


def _trace_summary(trace_reader: TraceReader, n: int = 200) -> dict:
    """Aggregate metrics from the latest N traces."""
    traces = trace_reader.latest(n=n)
    if not traces:
        return {
            "count": 0, "with_match": 0, "match_rate": 0.0,
            "by_topic": {}, "by_confidence": {},
        }
    with_match = 0
    by_topic: Counter = Counter()
    by_conf: Counter = Counter()
    for t in traces:
        lk = t.get("library_lookup") or {}
        if lk.get("matched_pattern_id"):
            with_match += 1
            if lk.get("topic"):
                by_topic[lk["topic"]] += 1
            if lk.get("confidence"):
                by_conf[lk["confidence"]] += 1
    return {
        "count": len(traces),
        "with_match": with_match,
        "match_rate": with_match / max(len(traces), 1),
        "by_topic": dict(by_topic),
        "by_confidence": dict(by_conf),
    }


@bp.route("/audit", methods=["GET"])
def audit_index():
    reader = current_app.config["LIBRARY_READER"]
    patterns = reader.list_patterns()

    pending_proposals: list[dict] = []
    for p in patterns:
        for prop in p.lifecycle.deletion_proposals:
            if prop.status == "pending":
                pending_proposals.append({
                    "pattern_id": p.id,
                    "proposal_id": prop.proposal_id,
                    "proposer": prop.proposer,
                    "date": prop.date,
                    "reason": prop.reason,
                })
    pending_proposals.sort(key=lambda d: d["date"], reverse=True)

    deprecation_candidates = [
        p for p in patterns
        if p.lifecycle.audit_status == "deprecation_candidate"
    ]

    timeline: list[dict] = []
    for p in patterns:
        for h in p.lifecycle.history:
            timeline.append({
                "pattern_id": p.id,
                "timestamp": h.timestamp,
                "event": h.event,
                "actor": h.actor,
                "detail": h.detail,
            })
    timeline.sort(key=lambda d: d["timestamp"], reverse=True)

    # Pagination — default 100 events/page
    try:
        page = max(0, int(request.args.get("page", "0")))
    except ValueError:
        page = 0
    page_size = 100
    timeline_total = len(timeline)
    timeline = timeline[page * page_size:(page + 1) * page_size]

    trace_reader = TraceReader(current_app.config["TRACES_DIR"])
    trace_metrics = _trace_summary(trace_reader)

    return render_template(
        "audit_log.html",
        stats=reader.stats(),
        pending_proposals=pending_proposals,
        deprecation_candidates=deprecation_candidates,
        timeline=timeline,
        timeline_page=page,
        timeline_total=timeline_total,
        timeline_page_size=page_size,
        recent_trace_count=trace_metrics["count"],
        trace_metrics=trace_metrics,
        # Phase 2 Commit 22 dashboard data:
        library_size_growth=_library_size_growth(patterns),
        hit_count_histogram=_hit_count_histogram(patterns),
        origin_breakdown=_origin_breakdown(patterns),
        autogen_batches=_autogen_batch_summary(),
    )
