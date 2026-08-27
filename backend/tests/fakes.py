from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from deep_research.tools.search import SearchHit


class FakeSearchProvider:
    def __init__(self, scripted_hits: dict[str, list[SearchHit]]) -> None:
        self.scripted_hits = scripted_hits
        self.queries: list[str] = []

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        self.queries.append(query)
        return self.scripted_hits.get(query, [])[:max_results]


class ScriptedStructuredModel:
    def __init__(self, scripted_outputs: Sequence[BaseModel | dict[str, object]]) -> None:
        self._scripted_outputs = list(scripted_outputs)
        self.calls: list[Any] = []

    async def ainvoke(self, input: Any) -> BaseModel | dict[str, object]:
        self.calls.append(input)
        if not self._scripted_outputs:
            raise AssertionError("No scripted structured output remains")
        return self._scripted_outputs.pop(0)
