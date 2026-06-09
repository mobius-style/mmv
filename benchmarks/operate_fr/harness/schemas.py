"""Schema definitions and validators for OPERATE-FR v0.1.

Lightweight — no pydantic dependency. Validation is dict-shape checks.
"""
from __future__ import annotations

from typing import Any


ROUTE_TAXONOMY = {
    "answer", "ask", "verify", "date_bound_answer",
    "abstain", "re_anchor", "execute", "refuse",
}

# Routes used for OPERATE-FR v0.1 scoring (per spec §6)
SCORING_ROUTES = {
    "answer", "ask", "verify", "date_bound_answer", "abstain", "re_anchor",
}

FAMILIES = {
    "volatile_current",
    "stale_premise_trap",
    "stable_control",
    "date_boundary",
    "query_neutrality",
    "ambiguous_time_frame",
    "freshness_long_run",
}

TASK_REQUIRED = (
    "id", "suite", "family", "domain", "language", "user_prompt",
    "temporal_volatility", "requires_current_verification", "tool_mode",
    "expected_routes", "disallowed_routes",
    "primary_metric",
)

LABEL_REQUIRED = (
    "task_id", "allowed_routes", "preferred_route",
    "disallowed_routes", "failure_modes_to_check",
)

RESULT_REQUIRED = (
    "task_id", "profile", "user_prompt", "response_text",
    "predicted_route", "classifier_confidence",
    "classifier_evidence", "latency_ms",
)


class SchemaError(ValueError):
    pass


def validate_task(rec: dict[str, Any]) -> None:
    missing = [k for k in TASK_REQUIRED if k not in rec]
    if missing:
        raise SchemaError(f"task missing required fields: {missing}")
    if rec["family"] not in FAMILIES:
        raise SchemaError(f"unknown family: {rec['family']!r}")
    for r in rec.get("expected_routes", []):
        if r not in ROUTE_TAXONOMY:
            raise SchemaError(f"expected_route not in taxonomy: {r!r}")
    for r in rec.get("disallowed_routes", []):
        if r not in ROUTE_TAXONOMY:
            raise SchemaError(f"disallowed_route not in taxonomy: {r!r}")


def validate_label(rec: dict[str, Any]) -> None:
    missing = [k for k in LABEL_REQUIRED if k not in rec]
    if missing:
        raise SchemaError(f"label missing required fields: {missing}")
    for r in rec.get("allowed_routes", []):
        if r not in ROUTE_TAXONOMY:
            raise SchemaError(f"allowed_route not in taxonomy: {r!r}")
    if rec["preferred_route"] not in ROUTE_TAXONOMY:
        raise SchemaError(f"preferred_route not in taxonomy: {rec['preferred_route']!r}")


def validate_result(rec: dict[str, Any]) -> None:
    missing = [k for k in RESULT_REQUIRED if k not in rec]
    if missing:
        raise SchemaError(f"result missing required fields: {missing}")
    if rec["predicted_route"] not in ROUTE_TAXONOMY and rec["predicted_route"] is not None:
        raise SchemaError(f"predicted_route not in taxonomy: {rec['predicted_route']!r}")
