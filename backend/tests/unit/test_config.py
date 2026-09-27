import pytest
from pydantic import ValidationError

from deep_research.config import ResearchBudgets, Settings

BUDGET_BOUNDS = [
    ("max_initial_tasks", 3, 5),
    ("max_supervisor_tasks", 0, 2),
    ("max_reviewer_tasks", 0, 1),
    ("max_research_rounds", 1, 2),
    ("max_queries_per_round", 1, 2),
    ("max_concurrent_researchers", 1, 3),
    ("max_total_search_queries", 1, 20),
    ("max_sources_per_task", 1, 8),
    ("max_evidence_per_task", 1, 20),
]


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


@pytest.mark.parametrize(("field", "minimum", "maximum"), BUDGET_BOUNDS)
def test_settings_enforce_every_research_budget_bound_at_construction(
    field: str,
    minimum: int,
    maximum: int,
) -> None:
    assert getattr(Settings(_env_file=None, **{field: maximum}), field) == maximum
    for invalid in (minimum - 1, maximum + 1):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{field: invalid})


@pytest.mark.parametrize(("field", "_minimum", "maximum"), BUDGET_BOUNDS)
def test_settings_reject_over_budget_environment_values_immediately(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    _minimum: int,
    maximum: int,
) -> None:
    monkeypatch.setenv(field.upper(), str(maximum + 1))

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_allow_missing_provider_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm_api_key is None
    assert settings.tavily_api_key is None


def test_rag_settings_reject_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rag_top_k=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rag_candidate_limit=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rag_chunk_max_tokens=0)


def test_rag_settings_keep_top_k_within_candidate_limit() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rag_candidate_limit=4, rag_top_k=5)


def test_embedding_provider_defaults_depend_on_the_selected_service() -> None:
    cloud = Settings(_env_file=None, embed_model_type="dashscope")
    local = Settings(_env_file=None, embed_model_type="local")

    assert cloud.embedding_model_name == "text-embedding-v3"
    assert local.embedding_model_name == "sentence-transformers/all-MiniLM-L6-v2"


def test_embedding_provider_rejects_an_unknown_service() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embed_model_type="unknown")


def test_rag_defaults_return_three_results() -> None:
    assert Settings(_env_file=None).rag_top_k == 3


def test_auth_settings_use_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_base_url == "http://localhost:5173"
    assert settings.auth_cookie_secure is False
    assert settings.auth_cookie_name == "research_session_dev"
    assert settings.auth_cookie_max_age == 604_800
    assert settings.auth_session_days == 7
    assert settings.auth_login_attempts == 5
    assert settings.auth_login_window_seconds == 900


def test_secure_auth_uses_the_host_prefixed_cookie() -> None:
    settings = Settings(_env_file=None, auth_cookie_secure=True)

    assert settings.auth_cookie_name == "__Host-research_session"
