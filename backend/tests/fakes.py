from deep_research.tools.search import SearchHit


class FakeSearchProvider:
    def __init__(self, scripted_hits: dict[str, list[SearchHit]]) -> None:
        self.scripted_hits = scripted_hits
        self.queries: list[str] = []

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        self.queries.append(query)
        return self.scripted_hits.get(query, [])[:max_results]
