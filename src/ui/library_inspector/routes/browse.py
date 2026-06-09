"""routes/browse.py — Library Browse page (`/`).

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.4.1."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from flask import Blueprint, current_app, render_template, request

bp = Blueprint("browse", __name__)


@bp.route("/", methods=["GET"])
def index():
    reader = current_app.config["LIBRARY_READER"]
    audit_status = request.args.get("audit_status") or None
    origin_type = request.args.get("origin_type") or None
    heat = request.args.get("heat") or None
    sort = request.args.get("sort", "id")

    patterns_by_topic = reader.by_topic()
    if audit_status or origin_type:
        for topic, pats in patterns_by_topic.items():
            patterns_by_topic[topic] = [
                p for p in pats
                if (not audit_status
                    or p.lifecycle.audit_status == audit_status)
                and (not origin_type or p.origin.type == origin_type)
            ]
    # Phase 3 Commit 34: hot / cold filters by lifecycle.hit_count.
    # "hot" = hit_count > library median (≥ 1 if no hits yet); "cold"
    # = hit_count == 0. Computed on the union after the audit / origin
    # filters so the heat label refers to the visible subset.
    if heat in ("hot", "cold"):
        all_visible = [
            p for pats in patterns_by_topic.values() for p in pats
        ]
        counts = sorted(p.lifecycle.hit_count for p in all_visible)
        median = (counts[len(counts) // 2]
                  if counts else 0)
        if heat == "hot":
            threshold = max(median, 1)
            for topic in patterns_by_topic:
                patterns_by_topic[topic] = [
                    p for p in patterns_by_topic[topic]
                    if p.lifecycle.hit_count >= threshold
                ]
        elif heat == "cold":
            for topic in patterns_by_topic:
                patterns_by_topic[topic] = [
                    p for p in patterns_by_topic[topic]
                    if p.lifecycle.hit_count == 0
                ]

    if sort == "hit_count":
        for topic in patterns_by_topic:
            patterns_by_topic[topic] = sorted(
                patterns_by_topic[topic],
                key=lambda p: p.lifecycle.hit_count,
                reverse=True,
            )
    elif sort == "audit_status":
        for topic in patterns_by_topic:
            patterns_by_topic[topic] = sorted(
                patterns_by_topic[topic],
                key=lambda p: p.lifecycle.audit_status,
            )
    elif sort == "last_hit":
        def lh_key(p):
            return p.lifecycle.last_hit_date or datetime.min.replace(
                tzinfo=timezone.utc
            )
        for topic in patterns_by_topic:
            patterns_by_topic[topic] = sorted(
                patterns_by_topic[topic], key=lh_key, reverse=True,
            )

    stats = reader.stats()
    # Phase 3 Commit 34: live in-memory hit-count tracker snapshot
    # (cumulative since process start, not yet flushed to JSONL).
    try:
        from src.retrieval.hit_count_tracker import get_tracker
        tracker_snapshot = get_tracker().snapshot()
        tracker_total = sum(tracker_snapshot.values())
    except Exception:
        tracker_snapshot = {}
        tracker_total = 0

    return render_template(
        "browse.html",
        patterns_by_topic=patterns_by_topic,
        stats=stats,
        sort=sort,
        audit_status=audit_status,
        origin_type=origin_type,
        heat=heat,
        tracker_snapshot=tracker_snapshot,
        tracker_total=tracker_total,
    )
