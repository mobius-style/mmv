"""Backend purity guard.

Prevents silent fallback (e.g. a 120B request being satisfied by the local 9B
because $OLLAMA_ENDPOINT happened to be reachable). Every model call MUST be
checked through enforce_purity() before being trusted.

Failure mode is fail-loud: PurityViolation is raised, not logged-and-continued.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class PurityViolation(RuntimeError):
    """Raised when the realised call diverges from the declared profile."""


@dataclass(frozen=True)
class CallEvidence:
    """What actually happened on a model call."""

    backend: str            # ollama | groq | openai_compatible | dummy
    endpoint: str           # the actual base URL hit
    reported_model: str | None  # whatever the server echoed back in its response


def enforce_purity(profile: dict[str, Any], evidence: CallEvidence) -> None:
    """Check evidence against profile['purity_guard']. Raise on mismatch.

    Soft checks (reported_model unknown for a backend that does not echo the
    id) skip the substring assertion but still enforce the others.
    """
    guard = profile.get("purity_guard") or {}

    required_backend = guard.get("require_backend")
    if required_backend and evidence.backend != required_backend:
        raise PurityViolation(
            f"backend mismatch: declared={required_backend!r}, "
            f"actual={evidence.backend!r}"
        )

    forbid = guard.get("forbid_endpoint_substring") or []
    ep_lower = (evidence.endpoint or "").lower()
    for needle in forbid:
        if needle.lower() in ep_lower:
            raise PurityViolation(
                f"endpoint {evidence.endpoint!r} contains forbidden substring "
                f"{needle!r} for profile (would indicate cross-backend leak)"
            )

    need_model_sub = guard.get("require_model_substring")
    if need_model_sub and evidence.reported_model:
        if need_model_sub.lower() not in evidence.reported_model.lower():
            raise PurityViolation(
                f"model echo mismatch: declared substring {need_model_sub!r} "
                f"not in reported model {evidence.reported_model!r}"
            )


def declared_endpoint(profile: dict[str, Any]) -> str:
    return str(profile.get("endpoint", "")).rstrip("/")
