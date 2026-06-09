"""Pseudo-UI scenario regression (Stage A — cyc_20260424_stage_abc_trilingual_complete).

Each YAML in tests/scenarios/ is one multi-turn scenario exercised
through the RoutingEngine via PseudoUISession. Assertions are
deterministic (route / intent_type / box consultation flags / response
substring contains/not-contains / reason_codes / length bounds).

Runtime cost: each scenario consumes the real qwen3.5:9b via Ollama,
so this file is SKIPPED by default and only runs when the opt-in
environment variable MOBIUS_RUN_SCENARIOS=1 is set. pytest baseline
runs remain fast (~7 min); scenario runs should be invoked explicitly:

    MOBIUS_RUN_SCENARIOS=1 pytest tests/test_pseudo_ui_scenarios.py -v

or equivalently:

    python scripts/scenario_runner.py tests/scenarios/
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"
SCENARIO_FILES = sorted(SCENARIO_DIR.glob("*.yaml"))

# Opt-in gate so the 30-scenario run (each Ollama-bound) does not slow
# every pytest invocation. CI / nightly / manual invocations set the
# flag; default developer runs skip the module.
RUN_ENABLED = os.environ.get("MOBIUS_RUN_SCENARIOS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_ENABLED,
    reason="Pseudo-UI scenarios are opt-in via MOBIUS_RUN_SCENARIOS=1",
)


@pytest.fixture(scope="module")
def scenario_runner_module():
    """Lazy import so the module is skipped cleanly when Ollama / Box 0
    are unavailable in CI environments. The real adapters are wired
    at PseudoUISession() construction time."""
    # Ensure .env is loaded so BRAVE / GROQ keys are available to any
    # adapters that consult them at construction time.
    from pathlib import Path as _P
    env = _P(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    from scripts.scenario_runner import run_scenario  # noqa: E402
    return run_scenario


@pytest.mark.parametrize("scenario_path", SCENARIO_FILES,
                         ids=[p.stem for p in SCENARIO_FILES])
def test_scenario(scenario_path: Path, scenario_runner_module):
    result = scenario_runner_module(scenario_path)
    if not result.passed:
        lines = [f"{result.scenario_name} FAILED ({result.language}/{result.category})"]
        for f in result.failures:
            lines.append(f"  turn {f.turn_index} {f.assertion}: "
                         f"expected={f.expected!r} actual={f.actual!r} "
                         f"detail={f.detail}")
        pytest.fail("\n".join(lines))
