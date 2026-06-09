"""Active-release loader for MMV Large.

Reads `operate-fr-bench/releases/large/current.yaml` and exposes it as a
typed dataclass. The secretary reads this on every invocation so a freeze
bump propagates immediately without code changes.

`resolve_active_profile()` additionally cross-checks the harness profile
file at `profile_path` to make sure no silent backend/endpoint/model
drift has slipped in since the pointer was bumped.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POINTER = (
    REPO_ROOT / "operate-fr-bench" / "releases" / "large" / "current.yaml"
)

REQUIRED_FIELDS = (
    "release", "short_name", "frozen_at",
    "profile_name", "profile_path", "harness_root",
    "freeze_note",
    "provider_backend", "provider_endpoint", "provider_model_id",
    "api_key_env",
)


@dataclass(frozen=True)
class ActiveRelease:
    release: str
    short_name: str
    frozen_at: str
    profile_name: str
    profile_path: str
    harness_root: str
    freeze_note: str
    provider_backend: str
    provider_endpoint: str
    provider_model_id: str
    api_key_env: str
    pointer_path: Path = DEFAULT_POINTER

    @property
    def freeze_note_abs(self) -> Path:
        return REPO_ROOT / self.freeze_note

    @property
    def profile_path_abs(self) -> Path:
        return REPO_ROOT / self.profile_path

    @property
    def harness_root_abs(self) -> Path:
        return REPO_ROOT / self.harness_root

    def summary_line(self) -> str:
        return (
            f"{self.short_name} (frozen {self.frozen_at}, "
            f"profile={self.profile_name}, model={self.provider_model_id})"
        )


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping at top level")
    return data


def load_pointer(pointer_path: Path | None = None) -> dict[str, Any]:
    """Load the raw pointer YAML. Validates required keys."""
    path = pointer_path or DEFAULT_POINTER
    if not path.exists():
        raise FileNotFoundError(
            f"active-release pointer missing: {path}. "
            "Run `python -m addons.secretary bump ...` to create it."
        )
    data = _read_yaml(path)
    missing = [k for k in REQUIRED_FIELDS if k not in data]
    if missing:
        raise ValueError(
            f"active-release pointer {path} missing keys: {missing}"
        )
    return data


def load_active_release(pointer_path: Path | None = None) -> ActiveRelease:
    """Resolve the pointer into a typed ActiveRelease."""
    path = pointer_path or DEFAULT_POINTER
    data = load_pointer(path)
    return ActiveRelease(
        **{k: data[k] for k in REQUIRED_FIELDS},
        pointer_path=path,
    )


# Backwards-compatible alias for the simpler name used elsewhere.
load_active = load_active_release


def resolve_active_profile(
    pointer_path: Path | None = None,
) -> tuple[ActiveRelease, dict[str, Any]]:
    """Load the active release AND its named profile out of the harness
    profile YAML. Raises ValueError on silent drift between the pointer
    and the actual profile (backend / endpoint / model_id mismatch).
    """
    active = load_active_release(pointer_path)
    if not active.profile_path_abs.exists():
        raise FileNotFoundError(
            f"profile config not found at {active.profile_path_abs} "
            f"(referenced from {active.pointer_path})"
        )
    config = _read_yaml(active.profile_path_abs)
    profiles = config.get("profiles") or {}
    if active.profile_name not in profiles:
        raise KeyError(
            f"profile '{active.profile_name}' not found in "
            f"{active.profile_path_abs}. Available: {sorted(profiles)}"
        )
    profile = dict(profiles[active.profile_name])

    # Drift detection — anything bumped on one side without the other is a bug.
    drift = []
    if (profile.get("backend") or "") != active.provider_backend:
        drift.append(
            f"backend: pointer={active.provider_backend!r} "
            f"profile={profile.get('backend')!r}"
        )
    profile_endpoint = (
        profile.get("base_url") or profile.get("endpoint") or ""
    )
    if profile_endpoint and profile_endpoint != active.provider_endpoint:
        drift.append(
            f"endpoint: pointer={active.provider_endpoint!r} "
            f"profile={profile_endpoint!r}"
        )
    if (profile.get("model_id") or "") != active.provider_model_id:
        drift.append(
            f"model_id: pointer={active.provider_model_id!r} "
            f"profile={profile.get('model_id')!r}"
        )
    if drift:
        raise ValueError(
            f"silent drift between pointer and profile "
            f"{active.profile_name!r}:\n  - " + "\n  - ".join(drift)
        )

    return active, profile


def bump_active_release(
    *,
    release: str,
    profile_name: str,
    freeze_note: str,
    frozen_at: str,
    pointer_path: Path | None = None,
    short_name: str | None = None,
    profile_path: str | None = None,
    harness_root: str | None = None,
    provider_backend: str | None = None,
    provider_endpoint: str | None = None,
    provider_model_id: str | None = None,
    api_key_env: str | None = None,
) -> ActiveRelease:
    """Update the active-release pointer. Fields left None are preserved
    from the existing pointer. Returns the new ActiveRelease."""
    path = pointer_path or DEFAULT_POINTER
    current = load_active_release(path)
    new = {
        "release": release,
        "short_name": short_name or release,
        "frozen_at": frozen_at,
        "profile_name": profile_name,
        "profile_path": profile_path or current.profile_path,
        "harness_root": harness_root or current.harness_root,
        "freeze_note": freeze_note,
        "provider_backend": provider_backend or current.provider_backend,
        "provider_endpoint": provider_endpoint or current.provider_endpoint,
        "provider_model_id": provider_model_id or current.provider_model_id,
        "api_key_env": api_key_env or current.api_key_env,
    }
    header = (
        "# MMV Large — Active Release Pointer\n"
        "# Updated by `python -m addons.secretary bump`. The secretary reads\n"
        "# this file on every invocation; do not commit a half-finished bump.\n"
        "\n"
    )
    body = yaml.safe_dump(new, sort_keys=False, allow_unicode=True)
    path.write_text(header + body, encoding="utf-8")
    return load_active_release(path)


# Backwards-compatible alias for the simpler name used elsewhere.
write_pointer = bump_active_release
