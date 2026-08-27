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

    @classmethod
    def from_api_key(cls, api_key: str) -> "TavilySearchProvider":
        try:
            from tavily import AsyncTavilyClient
        except ImportError:
            raise RuntimeError(
                "Missing search dependency; install the 'tavily-python' package."
            ) from None
        try:
            return cls(AsyncTavilyClient(api_key=api_key))
        except Exception as exc:
            raise RuntimeError(
                "Could not initialize Tavily search; verify the tavily-python "
                "installation and API key."
            ) from exc

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
