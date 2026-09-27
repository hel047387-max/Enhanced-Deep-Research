from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

from deep_research.domain.literature import LiteratureMetadata, SearchableUnit


class UnsupportedDocument(ValueError):
    pass


class EmptyDocument(ValueError):
    pass


class DoclingParser:
    _SUPPORTED_SUFFIXES: ClassVar[frozenset[str]] = frozenset(
        {".pdf", ".docx", ".md", ".markdown", ".html", ".htm", ".txt"}
    )

    def __init__(self, *, converter: Any, chunker: Any) -> None:
        self._converter = converter
        self._chunker = chunker

    @classmethod
    def from_model_name(
        cls,
        embedding_model: str,
        *,
        max_tokens: int,
    ) -> DoclingParser:
        try:
            from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
            from docling.chunking import HybridChunker
            from docling.datamodel.base_models import InputFormat
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling_core.transforms.chunker.tokenizer.huggingface import (
                HuggingFaceTokenizer,
            )
            from transformers import AutoTokenizer
        except ImportError:
            raise RuntimeError(
                "Literature parsing requires the optional 'rag' dependencies."
            ) from None

        tokenizer = HuggingFaceTokenizer(
            tokenizer=AutoTokenizer.from_pretrained(embedding_model),
            max_tokens=max_tokens,
        )
        return cls(
            converter=DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        backend=PyPdfiumDocumentBackend,
                    )
                }
            ),
            chunker=HybridChunker(tokenizer=tokenizer, merge_peers=True),
        )

    async def parse(
        self,
        *,
        filename: str,
        content: bytes,
        metadata: LiteratureMetadata,
    ) -> list[SearchableUnit]:
        suffix = Path(filename).suffix.casefold()
        if suffix not in self._SUPPORTED_SUFFIXES:
            raise UnsupportedDocument(filename)

        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                handle.write(content)
                temporary_path = handle.name
            conversion = await asyncio.to_thread(
                self._converter.convert,
                source=temporary_path,
            )
            chunks = await asyncio.to_thread(
                lambda: list(self._chunker.chunk(dl_doc=conversion.document))
            )
            return self._build_units(chunks, metadata)
        finally:
            if temporary_path is not None:
                os.unlink(temporary_path)

    @classmethod
    def _build_units(
        cls,
        chunks: list[Any],
        metadata: LiteratureMetadata,
    ) -> list[SearchableUnit]:
        document_id = uuid4()
        unit_ids = [uuid4() for _ in chunks]
        units: list[SearchableUnit] = []
        for index, chunk in enumerate(chunks):
            text = str(chunk.text).strip()
            if not text:
                continue
            exported = chunk.meta.export_json_dict()
            headings = [
                str(heading).strip()
                for heading in exported.get("headings", [])
                if str(heading).strip()
            ]
            page_numbers = cls._page_numbers(exported.get("doc_items", []))
            content_type = cls._content_type(exported.get("doc_items", []))
            units.append(
                SearchableUnit(
                    unit_id=unit_ids[index],
                    document_id=document_id,
                    title=metadata.title,
                    authors=metadata.authors,
                    publication_year=metadata.publication_year,
                    doi=metadata.doi,
                    language=metadata.language,
                    tags=metadata.tags,
                    heading_path=headings,
                    page_start=min(page_numbers) if page_numbers else None,
                    page_end=max(page_numbers) if page_numbers else None,
                    content_type=content_type,
                    text=text,
                )
            )
        if not units:
            raise EmptyDocument(metadata.title)

        return [
            unit.model_copy(
                update={
                    "previous_unit_id": units[index - 1].unit_id if index > 0 else None,
                    "next_unit_id": (
                        units[index + 1].unit_id if index + 1 < len(units) else None
                    ),
                }
            )
            for index, unit in enumerate(units)
        ]

    @staticmethod
    def _page_numbers(doc_items: object) -> list[int]:
        if not isinstance(doc_items, list):
            return []
        pages: list[int] = []
        for item in doc_items:
            if not isinstance(item, dict):
                continue
            provenance = item.get("prov", [])
            if not isinstance(provenance, list):
                continue
            for entry in provenance:
                if isinstance(entry, dict) and isinstance(entry.get("page_no"), int):
                    pages.append(entry["page_no"])
        return pages

    @staticmethod
    def _content_type(doc_items: object) -> str:
        if not isinstance(doc_items, list):
            return "other"
        labels = {
            str(item.get("label", "")).casefold()
            for item in doc_items
            if isinstance(item, dict)
        }
        if "table" in labels:
            return "table"
        if labels.intersection({"list", "list_item"}):
            return "list"
        if labels.intersection({"text", "paragraph", "section_header", "title"}):
            return "paragraph"
        return "other"
