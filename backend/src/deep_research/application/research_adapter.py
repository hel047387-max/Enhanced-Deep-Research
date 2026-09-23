from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from deep_research.application.retriever import LiteratureRetriever
from deep_research.domain.evidence import (
    EvidenceItem,
    EvidenceSource,
    LiteratureSource,
    Relevance,
)
from deep_research.domain.literature import LiteratureSearchRequest, SearchableUnit
from deep_research.domain.plan import ResearchBrief, ResearchTask
from deep_research.llm import StructuredModel
from deep_research.prompts.research import evidence_extraction_prompt
from deep_research.services.evidence_store import build_evidence


class ExtractedLiteratureEvidence(BaseModel, frozen=True):
    claim: str = Field(min_length=1)
    excerpt: str = Field(min_length=1, max_length=1000)
    context: str = Field(min_length=1)
    relevance: Relevance


class LiteratureEvidenceExtraction(BaseModel, frozen=True):
    items: list[ExtractedLiteratureEvidence]


@dataclass(frozen=True)
class ResearchEvidenceBatch:
    sources: dict[str, EvidenceSource]
    evidence: dict[str, EvidenceItem]


class ResearchAdapter:
    def __init__(
        self,
        retriever: LiteratureRetriever,
        evidence_model: StructuredModel,
    ) -> None:
        self._retriever = retriever
        self._evidence_model = evidence_model

    async def search(
        self,
        query: str,
        *,
        task: ResearchTask,
        brief: ResearchBrief,
        round_number: int,
        max_sources: int,
        max_evidence: int,
    ) -> ResearchEvidenceBatch:
        results = await self._retriever.search(
            LiteratureSearchRequest(query=query, limit=max_sources)
        )
        sources: dict[str, EvidenceSource] = {}
        evidence: dict[str, EvidenceItem] = {}
        for result in results[:max_sources]:
            unit = result.unit
            source = self._source(unit)
            raw = await self._evidence_model.ainvoke(
                [
                    SystemMessage(
                        content=evidence_extraction_prompt(brief, task, round_number)
                    ),
                    HumanMessage(content=unit.embedding_text()),
                ]
            )
            extraction = LiteratureEvidenceExtraction.model_validate(raw)
            sources[source.source_id] = source
            for item in extraction.items:
                if len(evidence) >= max_evidence:
                    break
                built = build_evidence(
                    task_id=task.task_id,
                    source_id=source.source_id,
                    claim=item.claim,
                    excerpt=item.excerpt,
                    context=self._context(unit, item.context),
                    relevance=item.relevance,
                    discovered_in_round=round_number,
                )
                evidence[built.evidence_id] = built
            if len(evidence) >= max_evidence:
                break
        return ResearchEvidenceBatch(sources=sources, evidence=evidence)

    @staticmethod
    def _source(unit: SearchableUnit) -> LiteratureSource:
        return LiteratureSource(
            source_id=f"lit-{unit.unit_id}",
            document_id=unit.document_id,
            unit_id=unit.unit_id,
            title=unit.title,
            authors=unit.authors,
            publication_year=unit.publication_year,
            doi=unit.doi,
            heading_path=unit.heading_path,
            page_start=unit.page_start,
            page_end=unit.page_end,
            retrieved_at=datetime.now(UTC),
        )

    @staticmethod
    def _context(unit: SearchableUnit, context: str) -> str:
        location = " > ".join(unit.heading_path) or "unknown section"
        if unit.page_start is None:
            pages = "unknown pages"
        elif unit.page_end is None or unit.page_end == unit.page_start:
            pages = f"page {unit.page_start}"
        else:
            pages = f"pages {unit.page_start}-{unit.page_end}"
        return f"{unit.title}; {location}; {pages}. {context}"