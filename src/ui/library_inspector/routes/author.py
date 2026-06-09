"""routes/author.py — Pattern authoring form (T-only).

Phase 2 Commit 21. Spec v1.3 Section 5.7 + 5.7.6.

GET /pattern/new       Render the form
POST /pattern/new      Validate Pydantic schema → atomic JSONL append
                       → optional async index rebuild → redirect to detail

Auth: HTTP Basic Auth with env var MOBIUS_LIB_AUTHOR_PASSWORD_HASH
(SHA-256 hex of password). When env unset, both routes return 403.
This keeps the form OFF by default; T enables it locally only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from base64 import b64decode
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from flask import (
    Blueprint, abort, current_app, redirect, render_template, request,
    Response, url_for,
)
from pydantic import ValidationError

from src.retrieval.pattern_schema import (
    CrossLingualTestQuery, LifecycleEvent, Origin, Pattern, RouteConfig,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config" / "pattern_library"

bp = Blueprint("author", __name__)

ID_PATTERN = re.compile(r"^pat_[a-z_]+_\d{3}$")
KNOWN_TOPICS = (
    "self_reference", "conceptual_explain", "factual_inquiry",
    "correction", "casual_engagement", "casual_greeting",
)
BOX_NS = ("box_0", "box_1", "box_2", "box_3", "box_4",
          "box_5", "box_6", "box_7", "box_w")


# ─── Auth ────────────────────────────────────────────────────────────

def _required_password_hash() -> Optional[str]:
    """Returns the SHA-256 hex digest expected, or None if env unset.
    When None, the form is disabled (returns 403)."""
    return os.environ.get("MOBIUS_LIB_AUTHOR_PASSWORD_HASH")


def _check_auth() -> bool:
    """Verify HTTP Basic Auth against MOBIUS_LIB_AUTHOR_PASSWORD_HASH.
    Constant-time comparison to avoid timing leaks."""
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
        headers={"WWW-Authenticate": 'Basic realm="MOBIUS lib author"'},
    )


# ─── Form rendering ──────────────────────────────────────────────────

@bp.route("/pattern/new", methods=["GET"])
def new_form():
    if _required_password_hash() is None:
        abort(403, description=(
            "Authoring form disabled. Set "
            "MOBIUS_LIB_AUTHOR_PASSWORD_HASH env var to enable."
        ))
    if not _check_auth():
        return _challenge()
    return render_template(
        "author_form.html",
        topics=KNOWN_TOPICS, boxes=BOX_NS,
        error=None, form={},
    )


# ─── Submission ──────────────────────────────────────────────────────

_FILE_LOCK = threading.Lock()


def _parse_lines(s: str) -> list[str]:
    """Split textarea body into stripped non-empty lines."""
    return [ln.strip() for ln in s.splitlines() if ln.strip()]


def _build_pattern_from_form(form: dict) -> Pattern:
    examples = _parse_lines(form.get("examples", ""))
    if len(examples) < 5:
        raise ValueError(
            f"Need at least 5 examples (got {len(examples)})."
        )

    negatives = _parse_lines(form.get("negative_examples", ""))

    # Cross-lingual queries are submitted as parallel arrays
    xling_langs = form.getlist("xl_lang") if hasattr(form, "getlist") else []
    xling_queries = form.getlist("xl_query") if hasattr(form, "getlist") else []
    xling_match = form.getlist("xl_match") if hasattr(form, "getlist") else []
    xling_min_cos = form.getlist("xl_min_cos") if hasattr(form, "getlist") else []

    xling: list[CrossLingualTestQuery] = []
    for lang, q, m, mc in zip(xling_langs, xling_queries, xling_match,
                                xling_min_cos):
        q = (q or "").strip()
        if not q:
            continue
        is_match = (m == "true")
        mc_val: Optional[float] = None
        if is_match:
            try:
                mc_val = float(mc) if mc else 0.62
            except ValueError:
                mc_val = 0.62
        xling.append(CrossLingualTestQuery(
            lang=lang, query=q,
            expected_match=is_match,
            min_cosine=mc_val,
        ))

    pid = form.get("id", "").strip()
    if not ID_PATTERN.fullmatch(pid):
        raise ValueError(
            f"id must match {ID_PATTERN.pattern} (got {pid!r})"
        )

    topic = form.get("topic", "").strip()
    intent = form.get("intent", "").strip()
    if not intent:
        raise ValueError("intent is required")

    primary_box = form.get("primary_box", "box_0").strip()

    now = datetime.now(timezone.utc)
    return Pattern(
        id=pid, version="1.0", lang="en",
        topic=topic, intent=intent,
        examples=examples, negative_examples=negatives,
        route=RouteConfig(
            primary_box=primary_box,
            exclude_boxes=[],
            synthesis_mode=form.get(
                "synthesis_mode", "factual_synthesis"
            ).strip() or "factual_synthesis",
        ),
        cross_lingual_test_queries=xling,
        lifecycle={"history": [{
            "timestamp": now.isoformat(),
            "event": "created",
            "actor": "user_t",
            "detail": "authored via Library Inspector form",
        }]},
        origin=Origin(
            type="manual", date=now,
            evolution_log_entry=22,
        ),
        deprecated=False,
    )


def _atomic_append(target_path: Path, p: Pattern) -> None:
    """Append a pattern to the end of target_path's JSONL.
    Uses temp+rename so concurrent readers see consistent state."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if target_path.exists():
        existing = target_path.read_text(encoding="utf-8").splitlines()

    tmp = target_path.with_suffix(
        target_path.suffix + f".{secrets.token_hex(3)}.tmp"
    )
    with tmp.open("w", encoding="utf-8") as fh:
        for line in existing:
            if line.strip():
                fh.write(line + "\n")
        fh.write(p.model_dump_json(exclude_none=False) + "\n")
    os.replace(tmp, target_path)


@bp.route("/pattern/new", methods=["POST"])
def submit_form():
    if _required_password_hash() is None:
        abort(403, description="Authoring form disabled")
    if not _check_auth():
        return _challenge()

    try:
        p = _build_pattern_from_form(request.form)
    except (ValueError, ValidationError) as e:
        return render_template(
            "author_form.html",
            topics=KNOWN_TOPICS, boxes=BOX_NS,
            error=str(e),
            form=request.form.to_dict(),
        ), 422

    target = CONFIG_DIR / f"{p.topic}.jsonl"
    with _FILE_LOCK:
        # Pre-check: does this id already exist anywhere in the library?
        for existing in CONFIG_DIR.glob("*.jsonl"):
            if existing.name.startswith("_"):
                continue
            for line in existing.open("r", encoding="utf-8"):
                line = line.strip()
                if line and json.loads(line).get("id") == p.id:
                    return render_template(
                        "author_form.html",
                        topics=KNOWN_TOPICS, boxes=BOX_NS,
                        error=f"id {p.id!r} already exists in library",
                        form=request.form.to_dict(),
                    ), 422
        _atomic_append(target, p)

    # Reload Library Reader (so /pattern/<id> shows the new entry on
    # next request without restart)
    reader = current_app.config.get("LIBRARY_READER")
    if reader is not None:
        try:
            reader.reload()
        except Exception:
            pass

    return redirect(url_for("pattern_detail.detail", pattern_id=p.id))
