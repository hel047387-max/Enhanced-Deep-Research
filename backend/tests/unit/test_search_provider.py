import pytest

from deep_research.config import Settings
from deep_research.llm import create_structured_model
from deep_research.nodes.clarify import ClarificationDecision
from deep_research.tools.search import SearchHit, TavilySearchProvider
from tests.fakes import FakeSearchProvider


@pytest.mark.asyncio
async def test_fake_search_records_queries_and_returns_scripted_hits() -> None:
    hit = SearchHit(
        title="Official docs",
        url="https://example.com/docs",
        content="Evidence text",
        raw_content=None,
    )
    provider = FakeSearchProvider({"query": [hit]})

    assert await provider.search("query", max_results=5) == [hit]
    assert provider.queries == ["query"]


@pytest.mark.asyncio
async def test_fake_search_returns_empty_list_for_unknown_query() -> None:
    provider = FakeSearchProvider({})

    assert await provider.search("missing", max_results=5) == []


def test_missing_openai_dependency_has_actionable_startup_error(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def missing_openai(name, *args, **kwargs):
        if name == "langchain_openai":
            raise ModuleNotFoundError("No module named langchain_openai")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_openai)

    with pytest.raises(RuntimeError, match="install.*langchain-openai"):
        create_structured_model(Settings(), ClarificationDecision)


def test_missing_tavily_dependency_has_actionable_startup_error(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def missing_tavily(name, *args, **kwargs):
        if name == "tavily":
            raise ModuleNotFoundError("No module named tavily")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_tavily)

    with pytest.raises(RuntimeError, match="install.*tavily-python"):
        TavilySearchProvider.from_api_key("test-key")
