import pytest

from deep_research.tools.search import SearchHit
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
