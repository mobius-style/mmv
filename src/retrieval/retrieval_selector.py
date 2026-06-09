from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetrievalPlan:
    use_local_rag: bool
    use_web_search: bool
    use_kiwix_fallback: bool = False


def choose_retrieval_plan(freshness_sensitive: bool, local_hits_available: bool) -> RetrievalPlan:
    """Choose a minimal MMV retrieval plan.

    Policy v7.4.8 MMV + v2 Kiwix integration:
    - Local RAG is attempted first whenever local hits are available.
    - Web search is only used when local evidence is unavailable and the turn is
      freshness-sensitive.
    - Kiwix fallback is used when local evidence is unavailable and the turn is
      NOT freshness-sensitive (static Wikipedia snapshot suffices).
    - This keeps search route-driven and prevents needless always-on web access.
    """
    if local_hits_available:
        return RetrievalPlan(use_local_rag=True, use_web_search=False)
    if freshness_sensitive:
        return RetrievalPlan(use_local_rag=False, use_web_search=True)
    return RetrievalPlan(use_local_rag=False, use_web_search=False, use_kiwix_fallback=True)
