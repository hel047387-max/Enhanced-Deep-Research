import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

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


class _Probe(BaseModel):
    ok: bool


@pytest.mark.asyncio
async def test_deepseek_structured_model_disables_thinking_and_repairs_parse_once(
    monkeypatch,
) -> None:
    responses = [
        {"raw": "invalid output", "parsed": None, "parsing_error": ValueError("bad JSON")},
        {"raw": object(), "parsed": {"ok": True}, "parsing_error": None},
    ]

    class FakeRunnable:
        def __init__(self) -> None:
            self.calls = []

        async def ainvoke(self, messages):
            self.calls.append(messages)
            return responses.pop(0)

    runnable = FakeRunnable()

    class FakeChatOpenAI:
        kwargs = None
        structured_kwargs = None

        def __init__(self, **kwargs) -> None:
            type(self).kwargs = kwargs

        def with_structured_output(self, schema, **kwargs):
            type(self).structured_kwargs = kwargs
            return runnable

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=FakeChatOpenAI),
    )
    settings = Settings(
        llm_provider="deepseek",
        llm_model="deepseek-v4-flash",
        llm_api_key="test-key",
        llm_base_url="https://api.deepseek.com",
    )

    model = create_structured_model(settings, _Probe)
    result = await model.ainvoke([])

    assert result == {"ok": True}
    assert len(runnable.calls) == 2
    assert "Correct the previous structured output" in runnable.calls[1][-1].content
    assert "invalid output" in runnable.calls[1][-1].content
    assert FakeChatOpenAI.kwargs["temperature"] == 0
    assert FakeChatOpenAI.kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert FakeChatOpenAI.structured_kwargs == {
        "method": "function_calling",
        "include_raw": True,
    }
