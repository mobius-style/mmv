from src.retrieval.retrieval_selector import choose_retrieval_plan


def test_local_rag_wins_even_when_freshness_sensitive() -> None:
    plan = choose_retrieval_plan(freshness_sensitive=True, local_hits_available=True)
    assert plan.use_local_rag is True
    assert plan.use_web_search is False


def test_web_search_used_when_freshness_sensitive_and_no_local_hits() -> None:
    plan = choose_retrieval_plan(freshness_sensitive=True, local_hits_available=False)
    assert plan.use_local_rag is False
    assert plan.use_web_search is True


def test_no_search_when_not_freshness_sensitive_and_no_local_hits() -> None:
    plan = choose_retrieval_plan(freshness_sensitive=False, local_hits_available=False)
    assert plan.use_local_rag is False
    assert plan.use_web_search is False
