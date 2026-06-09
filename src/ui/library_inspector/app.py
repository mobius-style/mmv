"""library_inspector/app.py — Flask app entry for the Pattern Library Inspector.

Spec: docs/PATTERN_LIBRARY_SPEC_v1_2.md Section 5.7.

Phase 1 (Commit 7): browse + pattern_detail routes; CDN-served Pico.css
+ Alpine.js (no vendored static yet — Commit 8 may inline).

Default bind: 127.0.0.1:5000 (local-first per spec 5.7.6.1). No auth.
PII redaction OFF by default. Public mode (--public) is opt-in and
prints a warning that HTTPS reverse proxy is required.

Launch:
    python -m src.ui.library_inspector.app
    python -m src.ui.library_inspector.app --port 5050
    python -m src.ui.library_inspector.app --public --port 8080
"""
from __future__ import annotations

import argparse
from pathlib import Path

from flask import Flask

from .lib.library_reader import DEFAULT_CONFIG_DIR, LibraryReader

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def create_app(
    config_dir: Path = DEFAULT_CONFIG_DIR,
) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["LIBRARY_READER"] = LibraryReader(config_dir=config_dir)
    app.config["TRACES_DIR"] = (
        REPO_ROOT / "data" / "pattern_library" / "traces"
    )
    app.config["PII_REDACTION"] = False  # spec 5.7.6.1 default

    # Rate limiting (spec 5.7.6.3 — 5 proposals/day/IP, 100 browse/min/IP).
    # Flask-Limiter attaches a default limit; per-route stricter limits
    # are applied in the propose blueprint.
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        limiter = Limiter(
            key_func=get_remote_address,
            app=app,
            default_limits=["100 per minute"],
            storage_uri="memory://",
        )
    except Exception:
        limiter = None
    app.config["LIMITER"] = limiter

    # Routes
    from .routes import (
        audit, author, browse, pattern_detail, propose, search,
        secretary, trace, verify,
    )
    app.register_blueprint(browse.bp)
    app.register_blueprint(pattern_detail.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(trace.bp)
    app.register_blueprint(verify.bp)
    app.register_blueprint(audit.bp)
    app.register_blueprint(propose.bp)
    app.register_blueprint(author.bp)
    app.register_blueprint(secretary.bp)

    if limiter is not None:
        # Spec 5.7.6.3: 5 proposals/day per IP
        try:
            limiter.limit("5 per day")(propose.propose)
        except Exception:
            pass

    return app


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pattern Library Inspector — local-first read UI"
    )
    parser.add_argument(
        "--port", type=int, default=5000,
        help="Listen port (default 5000)",
    )
    parser.add_argument(
        "--public", action="store_true",
        help="Bind 0.0.0.0 (Phase 3+ opt-in; requires HTTPS proxy)",
    )
    parser.add_argument(
        "--config-dir", type=Path, default=DEFAULT_CONFIG_DIR,
        help="config/pattern_library/ directory",
    )
    args = parser.parse_args()

    app = create_app(config_dir=args.config_dir)
    host = "0.0.0.0" if args.public else "127.0.0.1"
    if args.public:
        print(
            "WARNING: Running in public mode. Ensure HTTPS reverse "
            "proxy + rate limiting in production."
        )
    print(f"Starting library inspector at http://{host}:{args.port}")
    app.run(host=host, port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
