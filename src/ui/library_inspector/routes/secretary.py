"""routes/secretary.py — Library Inspector Secretary integration.

Phase 3 Commit 38. Surfaces the proposal store from
src.secretary.secretary_core to the Library Inspector UI:
- GET  /secretary           — list pending proposals (T-only auth)
- POST /secretary/<pid>/decide  — approve / reject a proposal

HARD CONSTRAINT 7: even on approval, this route only flips the
proposal status — it does NOT mutate config/pattern_library/*. The
actual library modification remains a manual step gated on T's
review.

Auth: same MOBIUS_LIB_AUTHOR_PASSWORD_HASH used by routes/author.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from base64 import b64decode
from pathlib import Path
from typing import Optional

from flask import (
    Blueprint, Response, abort, current_app, redirect, render_template,
    request, url_for,
)

from src.secretary.secretary_core import ProposalStore

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
DEFAULT_PROPOSALS_PATH = (
    REPO_ROOT / "data" / "secretary" / "proposals.jsonl"
)

bp = Blueprint("secretary", __name__)


# ─── Auth ────────────────────────────────────────────────────────────


def _required_password_hash() -> Optional[str]:
    return os.environ.get("MOBIUS_LIB_AUTHOR_PASSWORD_HASH")


def _check_auth() -> bool:
    expected = _required_password_hash()
    if not expected:
        return False
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        creds = b64decode(auth[6:]).decode("utf-8", errors="replace")
        if ":" not in creds:
            return False
        _user, password = creds.split(":", 1)
    except Exception:
        return False
    actual_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(actual_hash, expected)


def _challenge() -> Response:
    return Response(
        "Auth required", status=401,
        headers={"WWW-Authenticate": 'Basic realm="MOBIUS lib secretary"'},
    )


def _get_store() -> ProposalStore:
    path = current_app.config.get(
        "SECRETARY_PROPOSALS_PATH", DEFAULT_PROPOSALS_PATH,
    )
    return ProposalStore(proposals_path=Path(path))


# ─── Routes ─────────────────────────────────────────────────────────


@bp.route("/secretary", methods=["GET"])
def index():
    if _required_password_hash() is None:
        abort(403, description=(
            "Secretary UI disabled. Set "
            "MOBIUS_LIB_AUTHOR_PASSWORD_HASH env var to enable."
        ))
    if not _check_auth():
        return _challenge()
    store = _get_store()
    pending = store.list_pending()
    all_props = store.list_all()
    counts = {
        "pending": sum(1 for p in all_props if p.status == "pending"),
        "approved": sum(1 for p in all_props if p.status == "approved"),
        "rejected": sum(1 for p in all_props if p.status == "rejected"),
        "applied": sum(1 for p in all_props if p.status == "applied"),
    }
    return render_template(
        "secretary.html",
        pending=pending,
        counts=counts,
    )


@bp.route("/secretary/<proposal_id>/decide", methods=["POST"])
def decide(proposal_id: str):
    if _required_password_hash() is None:
        abort(403)
    if not _check_auth():
        return _challenge()
    decision = (request.form.get("decision") or "").strip()
    note = (request.form.get("note") or "").strip() or None
    if decision not in ("approved", "rejected"):
        abort(400, description="decision must be approved|rejected")
    store = _get_store()
    updated = store.update_status(
        proposal_id, decision,
        decided_by="human:taiko",
        decision_note=note,
    )
    if updated is None:
        abort(404, description=f"Proposal {proposal_id} not found")
    return redirect(url_for("secretary.index"))
