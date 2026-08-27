from typing import TYPE_CHECKING, Protocol

from pydantic import AnyHttpUrl, BaseModel

if TYPE_CHECKING:
    from tavily import AsyncTavilyClient


class SearchHit(BaseModel, frozen=True):
    title: str
    url: AnyHttpUrl
    content: str
    raw_content: str | None = None


class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int) -> list[SearchHit]: ...


class TavilySearchProvider:
    def __init__(self, client: "AsyncTavilyClient") -> None:
        self._client = client

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        response = await self._client.search(
            query=query,
            max_results=max_results,
            include_raw_content=True,
        )
        return [
            SearchHit(
                title=result["title"],
                url=result["url"],
                content=result.get("content", ""),
                raw_content=result.get("raw_content"),
            )
            for result in response.get("results", [])
        ]
