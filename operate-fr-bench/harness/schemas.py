"""Schemas (dict shapes) for OPERATE-FR v0.1.

These are intentionally plain dictionaries rather than pydantic / dataclass
models so the harness has zero non-stdlib dependencies beyond PyYAML and
requests.

Tightly enforced fields are validated by `validate_task()` and
`validate_label()`; everything else is best-effort.
"""
from __future__ import annotations

from typing import Any, Iterable

# ─── route taxonomy ──────────────────────────────────────────────────

ROUTES: tuple[str, ...] = (
    "answer",
    "ask",
    "verify",
    "date_bound_answer",
    "abstain",
    "re_anchor",
    "execute",
    "refuse",
)

# In v0.1 we score primarily on these; the others are accepted but rare.
SCORED_PRIMARY_ROUTES: tuple[str, ...] = (
    "answer",
    "ask",
    "verify",
    "date_bound_answer",
    "abstain",
    "re_anchor",
)

FAMILIES: tuple[str, ...] = (
    "volatile_current",
    "stale_premise_trap",
    "stable_control",
    "date_boundary",
    "query_neutrality",
    "ambiguous_time_frame",
    "freshness_long_run",
)

TOOL_MODES: tuple[str, ...] = (
    "no_tool",
    "tool_available",
    "tool_available_or_no_tool",
)


# ─── failure modes (closed enum) ─────────────────────────────────────

FAILURE_MODES: tuple[str, ...] = (
    "stale_commitment",
    "unsupported_current_claim",
    "missing_date_boundary",
    "over_verification_on_stable",
    "fabricated_citation",
    "false_clarifying_question_on_stable",
    "stale_premise_accepted",
    "query_contamination",
    "verification_started_not_completed",
    "no_response",
)


# ─── validators ──────────────────────────────────────────────────────


def _err(field: str, why: str) -> str:
    return f"field {field!r}: {why}"


def validate_task(t: dict[str, Any]) -> list[str]:
    """Return list of validation errors; empty list means OK."""
    errs: list[str] = []
    required = (
        "id", "suite", "family", "domain", "language",
        "user_prompt", "temporal_volatility",
        "requires_current_verification", "tool_mode",
        "expected_routes", "disallowed_routes",
        "primary_metric",
    )
    for k in required:
        if k not in t:
            errs.append(_err(k, "missing"))
    if "family" in t and t["family"] not in FAMILIES:
        errs.append(_err("family", f"not in {FAMILIES}"))
    if "tool_mode" in t and t["tool_mode"] not in TOOL_MODES:
        errs.append(_err("tool_mode", f"not in {TOOL_MODES}"))
    if "expected_routes" in t:
        if not isinstance(t["expected_routes"], list) or not t["expected_routes"]:
            errs.append(_err("expected_routes", "must be non-empty list"))
        else:
            for r in t["expected_routes"]:
                if r not in ROUTES:
                    errs.append(_err("expected_routes", f"unknown route {r!r}"))
    if "disallowed_routes" in t:
        if not isinstance(t["disallowed_routes"], list):
            errs.append(_err("disallowed_routes", "must be list"))
        else:
            for r in t["disallowed_routes"]:
                if r not in ROUTES:
                    errs.append(_err("disallowed_routes", f"unknown route {r!r}"))
    if "temporal_volatility" in t and t["temporal_volatility"] not in (
        "low", "medium", "high",
    ):
        errs.append(_err("temporal_volatility", "must be low|medium|high"))
    if "primary_metric" in t and t["primary_metric"] != "route_correctness":
        errs.append(_err("primary_metric", "v0.1 uses 'route_correctness'"))
    return errs


def validate_label(l: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    required = (
        "task_id", "allowed_routes", "preferred_route",
        "disallowed_routes", "failure_modes_to_check",
    )
    for k in required:
        if k not in l:
            errs.append(_err(k, "missing"))
    if "allowed_routes" in l:
        if not isinstance(l["allowed_routes"], list) or not l["allowed_routes"]:
            errs.append(_err("allowed_routes", "must be non-empty list"))
        else:
            for r in l["allowed_routes"]:
                if r not in ROUTES:
                    errs.append(_err("allowed_routes", f"unknown route {r!r}"))
    if "preferred_route" in l and l["preferred_route"] not in ROUTES:
        errs.append(_err("preferred_route", f"unknown route {l['preferred_route']!r}"))
    if "disallowed_routes" in l:
        if not isinstance(l["disallowed_routes"], list):
            errs.append(_err("disallowed_routes", "must be list"))
        else:
            for r in l["disallowed_routes"]:
                if r not in ROUTES:
                    errs.append(_err("disallowed_routes", f"unknown route {r!r}"))
    if "failure_modes_to_check" in l:
        if not isinstance(l["failure_modes_to_check"], list):
            errs.append(_err("failure_modes_to_check", "must be list"))
        else:
            for fm in l["failure_modes_to_check"]:
                if fm not in FAILURE_MODES:
                    errs.append(_err("failure_modes_to_check",
                                     f"unknown failure mode {fm!r}"))
    return errs


# ─── result schema ───────────────────────────────────────────────────


def make_result_record(
    *,
    task_id: str,
    suite: str,
    profile: str,
    model_id: str,
    response_text: str,
    tool_calls: list[dict] | None,
    classified: dict,
    latency_ms: int,
    tokens_in: int | None,
    tokens_out: int | None,
    error: str | None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "suite": suite,
        "profile": profile,
        "model_id": model_id,
        "response_text": response_text,
        "tool_calls": tool_calls or [],
        "classified_route": classified.get("route"),
        "classified_confidence": classified.get("confidence"),
        "classified_evidence": classified.get("evidence", {}),
        "classified_notes": classified.get("notes", ""),
        "latency_ms": int(latency_ms),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "error": error,
        "metadata": metadata or {},
    }


def _enum_or_none(value: Any, allowed: Iterable[str]) -> str | None:
    return value if value in tuple(allowed) else None
