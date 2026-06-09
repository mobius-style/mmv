"""YAML loaders for benchmark_matrix.yaml, model_profiles.yaml, and suites."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"
SUITES_DIR = Path(__file__).resolve().parent.parent / "suites"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_model_profiles() -> dict[str, dict[str, Any]]:
    data = _load_yaml(CONFIG_DIR / "model_profiles.yaml")
    return data.get("profiles", {})


def load_benchmark_matrix() -> list[dict[str, Any]]:
    data = _load_yaml(CONFIG_DIR / "benchmark_matrix.yaml")
    return data.get("benchmarks", [])


def load_suite(name: str) -> dict[str, Any]:
    path = SUITES_DIR / f"{name}.yaml"
    return _load_yaml(path)


def get_profile(profile_name: str) -> dict[str, Any]:
    profiles = load_model_profiles()
    if profile_name not in profiles:
        raise KeyError(
            f"profile '{profile_name}' not in model_profiles.yaml; "
            f"available: {sorted(profiles.keys())}"
        )
    return profiles[profile_name]


def get_benchmark(name: str) -> dict[str, Any]:
    for entry in load_benchmark_matrix():
        if entry.get("name") == name:
            return entry
    raise KeyError(f"benchmark '{name}' not in benchmark_matrix.yaml")
