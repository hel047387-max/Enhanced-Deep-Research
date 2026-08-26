import pytest
from pydantic import ValidationError

from deep_research.config import ResearchBudgets, Settings


def test_default_budgets_match_the_approved_spec() -> None:
    budgets = ResearchBudgets()
    assert budgets.max_initial_tasks == 5
    assert budgets.max_supervisor_tasks == 2
    assert budgets.max_reviewer_tasks == 1
    assert budgets.max_research_rounds == 2
    assert budgets.max_queries_per_round == 2
    assert budgets.max_concurrent_researchers == 3
    assert budgets.max_total_search_queries == 20
    assert budgets.max_sources_per_task == 8
    assert budgets.max_evidence_per_task == 20


def test_client_cannot_construct_an_unbounded_budget() -> None:
    with pytest.raises(ValidationError):
        ResearchBudgets(max_total_search_queries=21)


def test_settings_allow_missing_provider_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm_api_key is None
    assert settings.tavily_api_key is None
