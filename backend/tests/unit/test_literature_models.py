from uuid import UUID

import pytest
from pydantic import ValidationError

from deep_research.domain.literature import (
    LiteratureFilter,
    LiteratureMetadata,
    SearchableUnit,
)


def make_unit(**updates: object) -> SearchableUnit:
    values: dict[str, object] = {
        "unit_id": "11111111-1111-4111-8111-111111111111",
        "document_id": "22222222-2222-4222-8222-222222222222",
        "title": "混合检索研究",
        "authors": ["张三"],
        "publication_year": 2025,
        "doi": "10.1/example",
        "language": "zh",
        "tags": ["RAG"],
        "heading_path": ["方法", "检索"],
        "page_start": 12,
        "page_end": 13,
        "content_type": "paragraph",
        "text": "统一向量检索正文。",
    }
    values.update(updates)
    return SearchableUnit.model_validate(values)


def test_searchable_unit_builds_embedding_text_and_complete_payload() -> None:
    unit = make_unit()

    assert "标题：混合检索研究" in unit.embedding_text()
    assert "作者：张三" in unit.embedding_text()
    assert "章节：方法 > 检索" in unit.embedding_text()
    assert "正文：统一向量检索正文。" in unit.embedding_text()
    assert unit.to_payload() == unit.model_dump(mode="json")


def test_searchable_unit_keeps_position_fields_out_of_embedding_text() -> None:
    unit = make_unit(
        previous_unit_id="33333333-3333-4333-8333-333333333333",
        next_unit_id="44444444-4444-4444-8444-444444444444",
    )

    embedded = unit.embedding_text()
    assert str(unit.unit_id) not in embedded
    assert "12" not in embedded
    assert "33333333" not in embedded


def test_searchable_unit_rejects_reversed_page_range() -> None:
    with pytest.raises(ValidationError):
        make_unit(page_start=13, page_end=12)


def test_literature_metadata_requires_a_title() -> None:
    with pytest.raises(ValidationError):
        LiteratureMetadata(title="   ")


def test_literature_filter_rejects_reversed_year_range() -> None:
    with pytest.raises(ValidationError):
        LiteratureFilter(year_from=2025, year_to=2024)


def test_ids_are_typed_as_uuids() -> None:
    unit = make_unit()
    assert isinstance(unit.unit_id, UUID)
    assert isinstance(unit.document_id, UUID)
