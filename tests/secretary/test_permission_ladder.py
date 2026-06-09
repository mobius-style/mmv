"""Permission-ladder consistency tests.

The ladder at `addons/secretary/permission_ladder.yaml` is supposed to
declare every verb that exists in the CLI. We treat the YAML as the
source of truth and compare it against what `build_parser()` actually
exposes.

If a new verb is added but not declared, this test fails — the policy
boundary needs an explicit statement of read/write/network surface.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from addons.secretary.cli import build_parser, PERMISSION_LADDER


REQUIRED_KEYS = {
    "description", "reads", "writes", "network",
}


def _load_ladder() -> dict:
    return yaml.safe_load(PERMISSION_LADDER.read_text(encoding="utf-8")) or {}


def _cli_verbs() -> set[str]:
    """Pull subcommand names directly from the argparse object."""
    import argparse
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices.keys())
    return set()


def test_ladder_file_exists() -> None:
    assert PERMISSION_LADDER.exists(), (
        f"permission ladder missing at {PERMISSION_LADDER}"
    )


def test_every_cli_verb_is_declared_in_ladder() -> None:
    cli = _cli_verbs()
    declared = set((_load_ladder().get("verbs") or {}).keys())
    missing = cli - declared
    assert not missing, (
        f"verbs declared in CLI but not in permission_ladder.yaml: {missing}"
    )


def test_every_declared_verb_has_required_keys() -> None:
    verbs = _load_ladder().get("verbs") or {}
    for name, spec in verbs.items():
        assert isinstance(spec, dict), f"{name}: spec is not a dict"
        missing = REQUIRED_KEYS - set(spec.keys())
        assert not missing, f"{name} missing keys: {missing}"


def test_ladder_writes_are_inside_addon_or_pointer() -> None:
    """Hard rule: secretary verbs only write inside addons/secretary/state
    or a small allowlist of explicit shared-control files. Anything else
    is a policy violation that should be flagged loudly."""
    verbs = _load_ladder().get("verbs") or {}
    allowed_prefixes = (
        "addons/secretary/state/",
        "operate-fr-bench/releases/large/current.yaml",
        "AGENTS.md",
        "docs/current/HANDOFF.md",
    )
    for name, spec in verbs.items():
        for path in spec.get("writes") or []:
            assert path.startswith(allowed_prefixes), (
                f"{name}: write path {path!r} is outside the allowed "
                f"surface {allowed_prefixes}"
            )
