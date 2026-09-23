from __future__ import annotations

import json
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from deep_research.application.context_builder import ContextBuilder
from deep_research.application.retriever import LiteratureRetriever
from deep_research.domain.literature import (
    LiteratureAnswer,
    LiteratureCitation,
    LiteratureSearchRequest,
    SearchableUnit,
)
from deep_research.llm import StructuredModel
from deep_research.prompts.literature import literature_answer_prompt


class InsufficientLiteratureEvidence(ValueError):
    pass


class InvalidLiteratureCitation(ValueError):
    pass


class LiteratureAnswerDraft(BaseModel, frozen=True):
    answer: str = Field(min_length=1)
    citation_unit_ids: list[UUID] = Field(min_length=1)


class AnswerService:
    def __init__(
        self,
        retriever: LiteratureRetriever,
        context_builder: ContextBuilder,
        model: StructuredModel,
    ) -> None:
        self._retriever = retriever
        self._context_builder = context_builder
        self._model = model

    async def answer(self, request: LiteratureSearchRequest) -> LiteratureAnswer:
        results = await self._retriever.search(request)
        if not results:
            raise InsufficientLiteratureEvidence(request.query)

        context = await self._context_builder.build(results)
        if not context.units:
            raise InsufficientLiteratureEvidence(request.query)

        raw = await self._model.ainvoke(
            [
                SystemMessage(content=literature_answer_prompt()),
                HumanMessage(
                    content=json.dumps(
                        {"question": request.query, "context": context.text},
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        draft = LiteratureAnswerDraft.model_validate(raw)
        units_by_id = {unit.unit_id: unit for unit in context.units}
        unknown = set(draft.citation_unit_ids) - set(units_by_id)
        if unknown:
            raise InvalidLiteratureCitation(
                ", ".join(str(unit_id) for unit_id in sorted(unknown, key=str))
            )

        cited_units: list[SearchableUnit] = []
        seen: set[UUID] = set()
        for unit_id in draft.citation_unit_ids:
            if unit_id not in seen:
                seen.add(unit_id)
                cited_units.append(units_by_id[unit_id])
        return LiteratureAnswer(
            answer=draft.answer,
            citations=[self._citation(unit) for unit in cited_units],
        )

    @staticmethod
    def _citation(unit: SearchableUnit) -> LiteratureCitation:
        return LiteratureCitation(
            unit_id=unit.unit_id,
            document_id=unit.document_id,
            title=unit.title,
            authors=unit.authors,
            publication_year=unit.publication_year,
            doi=unit.doi,
            heading_path=unit.heading_path,
            page_start=unit.page_start,
            page_end=unit.page_end,
        )