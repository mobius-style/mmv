"""Tests for the MMV-Large release pointer (addons.secretary.release).

Offline: build synthetic pointer YAML + synthetic profile YAML in
tmp_path and verify the loader resolves them correctly, including
silent-drift detection.

A separate smoke test verifies the *real* on-disk pointer at
operate-fr-bench/releases/large/current.yaml still resolves — the
canary that ensures freezes can't silently misalign profile and pointer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from addons.secretary.release import (
    DEFAULT_POINTER,
    REQUIRED_FIELDS,
    ActiveRelease,
    bump_active_release,
    load_active_release,
    load_pointer,
    resolve_active_profile,
)


def _write_profile_yaml(
    path: Path,
    profile_name: str,
    *,
    model_id: str,
    backend: str = "openai_compatible",
    base_url: str = "https://api.groq.com/openai/v1",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "profiles:\n"
        f"  {profile_name}:\n"
        f"    backend: {backend}\n"
        f"    base_url: {base_url}\n"
        f"    model_id: {model_id}\n"
        f"    temperature: 0.0\n"
        f"    max_tokens: 1024\n",
        encoding="utf-8",
    )


def _write_pointer_yaml(
    path: Path,
    *,
    release: str = "MMV-L-RC9.9",
    profile_name: str = "rc99_profile",
    profile_path: str = "configs/profiles.yaml",
    harness_root: str = "harness",
    freeze_note: str = "FREEZE.md",
    provider_backend: str = "openai_compatible",
    provider_endpoint: str = "https://api.groq.com/openai/v1",
    provider_model_id: str = "openai/gpt-oss-120b",
    api_key_env: str = "GROQ_API_KEY",
    frozen_at: str = "2099-01-01",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"release: {release}\n"
        f"short_name: {release}\n"
        f"frozen_at: '{frozen_at}'\n"
        f"profile_name: {profile_name}\n"
        f"profile_path: {profile_path}\n"
        f"harness_root: {harness_root}\n"
        f"freeze_note: {freeze_note}\n"
        f"provider_backend: {provider_backend}\n"
        f"provider_endpoint: {provider_endpoint}\n"
        f"provider_model_id: {provider_model_id}\n"
        f"api_key_env: {api_key_env}\n",
        encoding="utf-8",
    )


def test_load_pointer_validates_required_fields(tmp_path: Path) -> None:
    bad = tmp_path / "current.yaml"
    bad.write_text("release: foo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing keys"):
        load_pointer(bad)


def test_load_pointer_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_pointer(tmp_path / "nope.yaml")


def test_load_active_release_returns_typed_dataclass(tmp_path: Path) -> None:
    pointer = tmp_path / "current.yaml"
    _write_pointer_yaml(pointer)
    active = load_active_release(pointer)
    assert isinstance(active, ActiveRelease)
    assert active.release == "MMV-L-RC9.9"
    assert active.profile_name == "rc99_profile"
    assert "MMV-L-RC9.9" in active.summary_line()
    assert active.pointer_path == pointer


def test_bump_round_trips_and_preserves_omitted_fields(tmp_path: Path) -> None:
    pointer = tmp_path / "current.yaml"
    _write_pointer_yaml(pointer)
    bumped = bump_active_release(
        release="MMV-L-RC9.10",
        profile_name="rc910_profile",
        freeze_note="FREEZE2.md",
        frozen_at="2099-02-02",
        pointer_path=pointer,
    )
    assert bumped.release == "MMV-L-RC9.10"
    assert bumped.profile_name == "rc910_profile"
    # Fields not passed are inherited from the prior pointer.
    assert bumped.provider_model_id == "openai/gpt-oss-120b"
    assert bumped.api_key_env == "GROQ_API_KEY"


def test_resolve_active_profile_detects_silent_model_drift(tmp_path: Path) -> None:
    profile_yaml = tmp_path / "configs" / "profiles.yaml"
    _write_profile_yaml(
        profile_yaml, "rc99_profile", model_id="openai/gpt-oss-OTHER",
    )
    pointer = tmp_path / "current.yaml"
    _write_pointer_yaml(
        pointer,
        profile_path=str(profile_yaml.relative_to(tmp_path)),
        provider_model_id="openai/gpt-oss-120b",
    )
    # Patch REPO_ROOT semantics via absolute profile_path in the pointer.
    # The loader resolves profile_path relative to REPO_ROOT only when
    # the path is relative; to keep this test hermetic we use absolute.
    pointer.write_text(
        pointer.read_text(encoding="utf-8").replace(
            f"profile_path: configs/profiles.yaml",
            f"profile_path: {profile_yaml}",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="silent drift"):
        resolve_active_profile(pointer)


def test_resolve_active_profile_missing_profile_in_config(tmp_path: Path) -> None:
    profile_yaml = tmp_path / "profiles.yaml"
    _write_profile_yaml(profile_yaml, "real_profile", model_id="openai/gpt-oss-120b")
    pointer = tmp_path / "current.yaml"
    _write_pointer_yaml(pointer, profile_name="ghost_profile")
    pointer.write_text(
        pointer.read_text(encoding="utf-8").replace(
            "profile_path: configs/profiles.yaml",
            f"profile_path: {profile_yaml}",
        ),
        encoding="utf-8",
    )
    with pytest.raises(KeyError, match="ghost_profile"):
        resolve_active_profile(pointer)


def test_default_pointer_resolves_on_disk() -> None:
    """Canary: the real RC3.3 pointer must always resolve and clear drift
    detection against the harness profile YAML it points at."""
    assert DEFAULT_POINTER.exists()
    active, profile = resolve_active_profile()
    assert active.release.startswith("MMV-L-")
    assert profile.get("backend") == active.provider_backend
    assert profile.get("model_id") == active.provider_model_id


def test_required_fields_constant_matches_dataclass() -> None:
    """Guard against accidentally adding a field to ActiveRelease but
    forgetting to require it in the pointer (or vice-versa)."""
    declared = {
        f for f in ActiveRelease.__dataclass_fields__
        if f != "pointer_path"  # internal, never in the YAML
    }
    assert declared == set(REQUIRED_FIELDS), (
        f"ActiveRelease fields {declared} vs REQUIRED_FIELDS {REQUIRED_FIELDS}"
    )
