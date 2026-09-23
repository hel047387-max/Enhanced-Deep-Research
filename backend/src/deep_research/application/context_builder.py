from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from deep_research.domain.literature import (
    LiteratureIndex,
    RetrievedUnit,
    SearchableUnit,
)


class LiteratureContext(BaseModel, frozen=True):
    text: str
    units: list[SearchableUnit]


class ContextBuilder:
    def __init__(self, index: LiteratureIndex, *, max_chars: int) -> None:
        self._index = index
        self._max_chars = max_chars

    async def build(self, ranked: list[RetrievedUnit]) -> LiteratureContext:
        primary = [item.unit for item in ranked]
        primary_ids = {unit.unit_id for unit in primary}
        neighbor_ids: list[UUID] = []
        seen_neighbors: set[UUID] = set()
        for unit in primary:
            for neighbor_id in (unit.previous_unit_id, unit.next_unit_id):
                if (
                    neighbor_id is not None
                    and neighbor_id not in primary_ids
                    and neighbor_id not in seen_neighbors
                ):
                    seen_neighbors.add(neighbor_id)
                    neighbor_ids.append(neighbor_id)

        neighbors = await self._index.retrieve(neighbor_ids) if neighbor_ids else []
        ordered = [*primary, *neighbors]
        blocks: list[str] = []
        included: list[SearchableUnit] = []
        used = 0
        for unit in ordered:
            block = self._format_unit(unit)
            separator = "\n\n" if blocks else ""
            remaining = self._max_chars - used - len(separator)
            if remaining <= 0:
                break
            if len(block) > remaining:
                if unit.unit_id in primary_ids:
                    blocks.append(separator + block[:remaining])
                    included.append(unit)
                break
            blocks.append(separator + block)
            included.append(unit)
            used += len(separator) + len(block)

        return LiteratureContext(text="".join(blocks), units=included)

    @staticmethod
    def _format_unit(unit: SearchableUnit) -> str:
        section = " > ".join(unit.heading_path) or "(no section)"
        if unit.page_start is None:
            pages = "unknown"
        elif unit.page_end is None or unit.page_end == unit.page_start:
            pages = str(unit.page_start)
        else:
            pages = f"{unit.page_start}-{unit.page_end}"
        return (
            f"[unit_id={unit.unit_id}]\n"
            f"Title: {unit.title}\n"
            f"Section: {section}\n"
            f"Pages: {pages}\n"
            f"Content: {unit.text}"
        )