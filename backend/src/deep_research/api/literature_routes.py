from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import ValidationError

from deep_research.api.schemas import (
    LiteratureSearchBody,
    LiteratureSearchItem,
    LiteratureSearchResponse,
)
from deep_research.application.answer_service import (
    InsufficientLiteratureEvidence,
    InvalidLiteratureCitation,
)
from deep_research.application.document_processor import DocumentProcessor
from deep_research.application.retriever import LiteratureRetriever
from deep_research.domain.literature import LiteratureAnswer, LiteratureMetadata
from deep_research.infrastructure.docling_parser import (
    EmptyDocument,
    UnsupportedDocument,
)


@dataclass(frozen=True)
class LiteratureApplication:
    processor: DocumentProcessor
    retriever: LiteratureRetriever
    answer_service: Any | None = None


def _application(request: Request) -> LiteratureApplication:
    application = getattr(request.app.state, "literature_application", None)
    if application is None:
        raise HTTPException(status_code=503, detail="Literature RAG is unavailable.")
    return application


router = APIRouter(prefix="/api/v1/literature")


@router.post(
    "/documents",
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    metadata_json: Annotated[str | None, Form()] = None,
):
    filename = file.filename or "document"
    content = await file.read(request.app.state.rag_max_upload_bytes + 1)
    if len(content) > request.app.state.rag_max_upload_bytes:
        raise HTTPException(status_code=413, detail="Uploaded document is too large.")

    try:
        metadata = (
            LiteratureMetadata.model_validate(json.loads(metadata_json))
            if metadata_json
            else LiteratureMetadata(title=Path(filename).stem or filename)
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="Invalid document metadata.") from exc

    try:
        return await _application(request).processor.ingest(filename, content, metadata)
    except UnsupportedDocument as exc:
        raise HTTPException(status_code=415, detail="Unsupported document type.") from exc
    except EmptyDocument as exc:
        raise HTTPException(status_code=422, detail="Document contains no searchable text.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Document indexing failed.") from exc


@router.post("/search", response_model=LiteratureSearchResponse)
async def search_literature(
    body: LiteratureSearchBody,
    request: Request,
) -> LiteratureSearchResponse:
    try:
        results = await _application(request).retriever.search(body.to_domain())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Literature search failed.") from exc
    return LiteratureSearchResponse(
        items=[LiteratureSearchItem.from_result(item) for item in results]
    )



@router.post("/answer", response_model=LiteratureAnswer)
async def answer_literature(
    body: LiteratureSearchBody,
    request: Request,
) -> LiteratureAnswer:
    service = _application(request).answer_service
    if service is None:
        raise HTTPException(status_code=503, detail="Literature answering is unavailable.")
    try:
        return await service.answer(body.to_domain())
    except InsufficientLiteratureEvidence as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The indexed literature does not contain enough evidence.",
        ) from exc
    except InvalidLiteratureCitation as exc:
        raise HTTPException(
            status_code=502,
            detail="The answer contained an invalid literature citation.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Literature answering failed.") from exc

@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(document_id: UUID, request: Request) -> Response:
    try:
        await _application(request).processor.delete(document_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Document deletion failed.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)