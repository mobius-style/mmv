"""routes/trace.py — Trace Viewer page (`/trace`).

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.4.4."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from ..lib.trace_reader import TraceReader

bp = Blueprint("trace", __name__)


@bp.route("/trace", methods=["GET"])
def trace_index():
    matched = request.args.get("matched_pattern_id") or None
    topic = request.args.get("topic") or None
    from_date = request.args.get("from") or None
    to_date = request.args.get("to") or None
    try:
        n = max(1, min(int(request.args.get("n", "50")), 500))
    except ValueError:
        n = 50
    reader = TraceReader(current_app.config["TRACES_DIR"])
    traces = reader.latest(
        n=n, matched_pattern_id=matched, topic=topic,
        from_date=from_date, to_date=to_date,
    )
    return render_template(
        "trace_viewer.html",
        traces=traces, matched=matched, topic=topic,
        from_date=from_date, to_date=to_date, n=n,
        traces_dir=str(current_app.config["TRACES_DIR"]),
    )
