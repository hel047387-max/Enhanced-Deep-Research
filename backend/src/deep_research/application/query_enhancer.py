from __future__ import annotations

from typing import Annotated

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, StringConstraints

from deep_research.domain.literature import QueryMode
from deep_research.llm import StructuredModel
from deep_research.prompts.literature import hyde_prompt, multi_query_prompt

CleanQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ExpandedQueries(BaseModel, frozen=True):
    queries: list[CleanQuery] = Field(min_length=1, max_length=3)


class HypotheticalPassage(BaseModel, frozen=True):
    text: CleanQuery


class QueryEnhancer:
    def __init__(
        self,
        multi_query_model: StructuredModel,
        hyde_model: StructuredModel,
    ) -> None:
        self._multi_query_model = multi_query_model
        self._hyde_model = hyde_model

    async def expand(self, query: str, mode: QueryMode) -> list[str]:
        if mode == "direct":
            return [query]
        if mode == "mqe":
            raw = await self._multi_query_model.ainvoke(
                [
                    SystemMessage(content=multi_query_prompt()),
                    HumanMessage(content=query),
                ]
            )
            return ExpandedQueries.model_validate(raw).queries

        raw = await self._hyde_model.ainvoke(
            [
                SystemMessage(content=hyde_prompt()),
                HumanMessage(content=query),
            ]
        )
        return [HypotheticalPassage.model_validate(raw).text]