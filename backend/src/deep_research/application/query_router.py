from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from deep_research.domain.literature import QueryDecision
from deep_research.llm import StructuredModel
from deep_research.prompts.literature import query_routing_prompt


class QueryRouter:
    def __init__(self, model: StructuredModel) -> None:
        self._model = model

    async def route(self, query: str) -> QueryDecision:
        raw = await self._model.ainvoke(
            [
                SystemMessage(content=query_routing_prompt()),
                HumanMessage(content=query),
            ]
        )
        return QueryDecision.model_validate(raw)