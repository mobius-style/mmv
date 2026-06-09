"""routes/pattern_detail.py — Pattern Detail page (`/pattern/<id>`).

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.4.2."""
from __future__ import annotations

from flask import Blueprint, abort, current_app, render_template

bp = Blueprint("pattern_detail", __name__)


@bp.route("/pattern/<pattern_id>", methods=["GET"])
def detail(pattern_id: str):
    reader = current_app.config["LIBRARY_READER"]
    p = reader.get(pattern_id)
    if p is None:
        abort(404)
    raw = reader.get_raw(pattern_id) or {}
    return render_template(
        "pattern_detail.html",
        p=p,
        raw=raw,
    )
