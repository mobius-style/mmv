"""routes/propose.py — Deletion Proposal page (`/propose/<id>`).

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.4.6 + 5.7.5.

GET /propose/<id>   render the form
POST /propose/<id>  validate via DeletionManager, append proposal,
                    update lifecycle, render confirmation page

Rate limiting: 5 proposals/day per IP (spec 5.7.6.3) via Flask-Limiter
attached at app level (`limiter` is read from app.config).
"""
from __future__ import annotations

from flask import (
    Blueprint, abort, current_app, render_template, request,
)

from ..lib.proposal_writer import (
    ProposalError, submit_proposal,
)

bp = Blueprint("propose", __name__)


@bp.route("/propose/<pattern_id>", methods=["GET", "POST"])
def propose(pattern_id: str):
    reader = current_app.config["LIBRARY_READER"]
    p = reader.get(pattern_id)
    if p is None:
        abort(404)

    if request.method == "POST":
        proposer = request.form.get("proposer", "").strip()
        reason = request.form.get("reason", "").strip()
        try:
            result = submit_proposal(pattern_id, proposer, reason)
        except ProposalError as e:
            return render_template(
                "propose_form.html", p=p, error=str(e),
                proposer=proposer, reason=reason,
            ), 400
        # On success, force a reload so subsequent UI views see the
        # updated audit_status.
        reader.reload()
        return render_template(
            "propose_form.html", p=p, error=None,
            proposer=proposer, reason=reason,
            result=result,
        )

    return render_template(
        "propose_form.html", p=p, error=None,
        proposer="", reason="", result=None,
    )
