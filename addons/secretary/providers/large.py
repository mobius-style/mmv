"""MMV-Large provider — delegates to the operate-fr-bench harness adapter.

We do not duplicate any HTTP wiring. The harness in
`operate-fr-bench/harness/adapters.py:call_adapter` already knows how to
apply the route_transformer, post_validator, and purity_guard for the
current RC3.x Large profile. The provider:

  1. Resolves the active release pointer (so freezes auto-propagate)
  2. Loads the named profile dict from the profile YAML it points at
  3. Cross-checks the profile's model_id against the pointer's
     provider_model_id — surfaces silent drift loudly
  4. Calls `harness.adapters.call_adapter(prompt, profile)`

The hyphen in `operate-fr-bench` prevents a plain import, so we inject
that directory onto sys.path before importing.
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from addons.secretary.release import REPO_ROOT, ActiveRelease, load_active_release


OPFR_DIR = REPO_ROOT / "operate-fr-bench"


class ProfileDriftError(RuntimeError):
    """Raised when the pointer and the profile YAML disagree on model_id."""


@dataclass
class LargeResponse:
    """What the secretary records about a Large call. Mirrors the
    harness AdapterResult minus internal fields, plus the release
    binding that was in effect at call time."""

    text: str
    model_id: str
    latency_ms: int
    tokens_in: int | None
    tokens_out: int | None
    error: str | None
    release: str
    profile_name: str


def resolve_profile(active: ActiveRelease) -> dict[str, Any]:
    """Load the profile dict named by the active pointer, with drift check."""
    profile_yaml = active.profile_path_abs
    if not profile_yaml.exists():
        raise FileNotFoundError(
            f"profile YAML not found at {profile_yaml} "
            f"(pointer expected profile_path={active.profile_path!r})"
        )
    data = yaml.safe_load(profile_yaml.read_text(encoding="utf-8")) or {}
    profiles = data.get("profiles") or {}
    if active.profile_name not in profiles:
        raise KeyError(
            f"profile {active.profile_name!r} not found in {profile_yaml}. "
            f"Available: {sorted(profiles)}"
        )
    profile = dict(profiles[active.profile_name])
    declared = str(profile.get("model_id", ""))
    if declared != active.provider_model_id:
        raise ProfileDriftError(
            f"silent model drift: pointer expects model_id="
            f"{active.provider_model_id!r} but profile "
            f"{active.profile_name!r} now declares model_id={declared!r}. "
            f"Re-bump or fix the profile."
        )
    return profile


def _load_harness_adapters():
    """Import operate-fr-bench/harness.adapters via sys.path injection."""
    if str(OPFR_DIR) not in sys.path:
        sys.path.insert(0, str(OPFR_DIR))
    return importlib.import_module("harness.adapters")


def call_large(
    prompt: str,
    *,
    release: ActiveRelease | None = None,
    profile_overrides: dict[str, Any] | None = None,
) -> LargeResponse:
    """Send a prompt to the currently-pinned MMV Large profile.

    `profile_overrides` lets callers tweak per-call knobs (max_tokens,
    temperature) without bumping the release. Use sparingly — the whole
    point of the release pointer is to have a canonical configuration.
    """
    release = release or load_active_release()
    profile = resolve_profile(release)
    if profile_overrides:
        profile.update(profile_overrides)

    adapters = _load_harness_adapters()
    result = adapters.call_adapter(prompt, profile)
    return LargeResponse(
        text=result.text,
        model_id=result.model_id,
        latency_ms=result.latency_ms,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        error=result.error,
        release=release.short_name,
        profile_name=release.profile_name,
    )
