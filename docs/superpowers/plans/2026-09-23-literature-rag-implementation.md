# Literature RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [x]) syntax for tracking.

**Goal:** Add a single-vector Qdrant literature RAG pipeline with Docling ingestion, query enhancement, reranking, grounded answers, and optional Deep Research evidence integration.

**Architecture:** Each document is parsed and structure-chunked, then each chunk and its metadata form one SearchableUnit. The same embedding provider encodes units and queries, and Qdrant stores the vector plus the complete unit payload. Application services orchestrate ingestion, retrieval, answer validation, and current-run research evidence; no RAG SQLite tables, sparse vectors, version records, or ingestion-state records are introduced.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, Docling, Sentence Transformers, Qdrant Client, LangGraph, Vue 3, TypeScript, Vitest, pytest

**Spec:** docs/superpowers/specs/2026-09-23-literature-rag-design.md

## Global Constraints

- Qdrant is the only RAG data store.
- Use exactly one vector per unit and the same embedder for documents and queries.
- Store the complete SearchableUnit in the Qdrant payload.
- Do not add RAG SQLite tables, versions, hashes, ingestion progress, retries, or index generations.
- Upload processing is synchronous and failures remain explicit.
- Preserve public HTTP validation for web sources.
- Literature sources use document and unit IDs, never file or localhost URLs.
- MQE and HyDE text assists retrieval and cannot be cited.
- Do not overwrite or broadly reformat the existing uncommitted memory-system changes.

## Review Focus

- Empty or unsupported documents fail before Qdrant writes; Task 3 tests this.
- Missing required Qdrant payload fields fail validation; Task 2 tests this.
- Qdrant upsert failures cannot return successful ingestion; Task 3 tests this.
- Answer citations outside the selected context are rejected; Task 6 tests this.
- Literature evidence works without weakening web URL validation; Task 7 tests this.

## File Map

**New backend files**

- domain/literature.py: RAG models and protocols.
- infrastructure/docling_parser.py: Docling, OCR, HybridChunker, temporary input.
- infrastructure/embedding_provider.py: one SentenceTransformer instance.
- infrastructure/qdrant_index.py: collection, upsert, query, retrieve, delete.
- infrastructure/cross_encoder_reranker.py: candidate reranking.
- application/document_processor.py: synchronous ingestion.
- application/query_router.py and query_enhancer.py: direct, MQE, HyDE.
- application/retriever.py and context_builder.py: search, rerank, neighbor expansion.
- application/answer_service.py: generation and citation validation.
- application/research_adapter.py: RAG results to current-run evidence.
- api/literature_routes.py: upload, search, answer, delete.

**Modified backend files**

- pyproject.toml and config.py: optional dependencies and bounded settings.
- api/main.py, api/schemas.py, api/routes.py: wiring and request contracts.
- domain/evidence.py, services/evidence_store.py, services/citations.py: literature sources.
- state/models.py, state/reducers.py, graph/builder.py, nodes/researcher.py, services/runtime.py: Deep Research integration.

**Frontend files**

- Add types/literature.ts, api/literature.ts, components/LiteraturePanel.vue and its test.
- Modify App.vue, ResearchForm.vue, research API/store/types, styles, and App tests.

---

### Task 1: Domain contracts and configuration

**Files:**
- Create: backend/src/deep_research/domain/literature.py
- Modify: backend/src/deep_research/config.py
- Modify: backend/pyproject.toml
- Test: backend/tests/unit/test_literature_models.py
- Test: backend/tests/unit/test_config.py

**Interfaces:**
- Produces LiteratureMetadata, SearchableUnit, LiteratureFilter, LiteratureSearchRequest, RetrievedUnit, IngestedDocument, LiteratureCitation, LiteratureAnswer, QueryMode, and QueryDecision.
- Produces DocumentParser, EmbeddingProvider, LiteratureIndex, and CandidateReranker protocols.
- Produces bounded rag_enabled, qdrant_url, qdrant_api_key, qdrant_collection, rag_embedding_model, rag_reranker_model, rag_chunk_max_tokens, rag_candidate_limit, rag_top_k, rag_context_max_chars, and rag_max_upload_bytes settings.

- [x] **Step 1: Write failing model and settings tests**

~~~python
def test_searchable_unit_builds_embedding_text_and_payload() -> None:
    unit = make_unit(title="混合检索研究", text="统一向量检索正文。")
    assert "标题：混合检索研究" in unit.embedding_text()
    assert "章节：方法 > 检索" in unit.embedding_text()
    assert unit.to_payload()["text"] == "统一向量检索正文。"

def test_rag_settings_reject_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        Settings(rag_top_k=0)
~~~

- [x] **Step 2: Run RED**

Run: python -m pytest tests/unit/test_literature_models.py tests/unit/test_config.py -q

Expected: FAIL because literature contracts and settings are absent.

- [x] **Step 3: Implement immutable models and exact protocols**

~~~python
class SearchableUnit(BaseModel, frozen=True):
    unit_id: UUID
    document_id: UUID
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    doi: str | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list)
    heading_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    content_type: Literal["paragraph", "table", "list", "other"]
    previous_unit_id: UUID | None = None
    next_unit_id: UUID | None = None
    text: str = Field(min_length=1)

    def embedding_text(self) -> str:
        fields = [
            f"标题：{self.title}",
            f"作者：{'、'.join(self.authors)}" if self.authors else "",
            f"年份：{self.publication_year}" if self.publication_year else "",
            f"标签：{'、'.join(self.tags)}" if self.tags else "",
            f"章节：{' > '.join(self.heading_path)}" if self.heading_path else "",
            f"正文：{self.text}",
        ]
        return "\n".join(field for field in fields if field)
~~~

Protocols expose parse, embed_documents, embed_query, ensure_collection, upsert, search, retrieve, delete_document, and rerank. SearchableUnit.to_payload returns model_dump(mode="json").

- [x] **Step 4: Add optional dependencies**

~~~toml
rag = [
    "docling>=2.0",
    "python-multipart>=0.0.12",
    "qdrant-client>=1.12",
    "sentence-transformers>=3.2",
    "transformers>=4.45",
]
~~~

- [x] **Step 5: Run GREEN**

Run: python -m pytest tests/unit/test_literature_models.py tests/unit/test_config.py -q

Expected: PASS.

- [x] **Step 6: Commit**

~~~text
git add backend/pyproject.toml backend/src/deep_research/config.py backend/src/deep_research/domain/literature.py backend/tests/unit/test_config.py backend/tests/unit/test_literature_models.py
git commit -m "feat: define literature RAG contracts"
~~~

---

### Task 2: Infrastructure adapters

**Files:**
- Create: backend/src/deep_research/infrastructure/__init__.py
- Create: backend/src/deep_research/infrastructure/docling_parser.py
- Create: backend/src/deep_research/infrastructure/embedding_provider.py
- Create: backend/src/deep_research/infrastructure/qdrant_index.py
- Create: backend/src/deep_research/infrastructure/cross_encoder_reranker.py
- Test: backend/tests/unit/test_literature_processing.py
- Test: backend/tests/unit/test_literature_retrieval.py

**Interfaces:**
- Consumes Task 1 contracts.
- Produces DoclingParser, SentenceTransformerEmbeddingProvider, QdrantLiteratureIndex, and SentenceTransformerReranker.

- [x] **Step 1: Write failing adapter tests**

~~~python
@pytest.mark.asyncio
async def test_index_upserts_one_vector_and_complete_payload() -> None:
    client = FakeQdrantClient()
    index = QdrantLiteratureIndex(client, "literature_units")
    await index.upsert([unit], [[0.1, 0.2, 0.3]])
    assert client.upserted[0].vector == [0.1, 0.2, 0.3]
    assert client.upserted[0].payload == unit.model_dump(mode="json")

def test_missing_payload_text_is_rejected() -> None:
    payload = unit.model_dump(mode="json")
    del payload["text"]
    with pytest.raises(ValidationError):
        SearchableUnit.model_validate(payload)
~~~

Parser tests prove title, heading, page, content type, text, and neighbor IDs survive conversion.

- [x] **Step 2: Run RED**

Run: python -m pytest tests/unit/test_literature_processing.py tests/unit/test_literature_retrieval.py -q

Expected: FAIL because adapters are absent.

- [x] **Step 3: Implement Docling adapter**

Use DocumentConverter.convert on a temporary file and HybridChunker with a HuggingFaceTokenizer configured for the embedding model. Convert chunk.text, chunk.meta.headings, page provenance, and label into SearchableUnit. Generate ordered unit UUIDs and then assign neighbor IDs. Empty parsed text raises EmptyDocument; unsupported input raises UnsupportedDocument. Always remove the temporary file.

- [x] **Step 4: Implement one embedding adapter**

~~~python
async def embed_documents(self, texts: list[str]) -> list[list[float]]:
    vectors = await asyncio.to_thread(
        self._model.encode_document, texts, normalize_embeddings=True
    )
    return vectors.tolist()

async def embed_query(self, text: str) -> list[float]:
    vector = await asyncio.to_thread(
        self._model.encode_query, text, normalize_embeddings=True
    )
    return vector.tolist()
~~~

The same provider instance implements both calls.

- [x] **Step 5: Implement Qdrant and reranker adapters**

Use AsyncQdrantClient, one cosine VectorParams collection, PointStruct with the full payload, query_points for retrieval, retrieve for neighbors, and a document_id filter for deletion. Every returned payload passes through SearchableUnit.model_validate. CrossEncoder.predict scores query/unit-text pairs and returns descending candidates.

- [x] **Step 6: Run GREEN**

Run: python -m pytest tests/unit/test_literature_processing.py tests/unit/test_literature_retrieval.py -q

Expected: PASS.

- [x] **Step 7: Commit**

~~~text
git add backend/src/deep_research/infrastructure backend/tests/unit/test_literature_processing.py backend/tests/unit/test_literature_retrieval.py
git commit -m "feat: add literature vector adapters"
~~~

---

### Task 3: Synchronous ingestion

**Files:**
- Create: backend/src/deep_research/application/__init__.py
- Create: backend/src/deep_research/application/document_processor.py
- Modify: backend/tests/fakes.py
- Test: backend/tests/unit/test_literature_processing.py

**Interfaces:**
- Consumes DocumentParser, EmbeddingProvider, and LiteratureIndex.
- Produces DocumentProcessor.ingest and DocumentProcessor.delete.

- [x] **Step 1: Write failing orchestration tests**

~~~python
@pytest.mark.asyncio
async def test_ingest_embeds_and_upserts_units() -> None:
    result = await processor.ingest("paper.pdf", b"%PDF", metadata)
    assert result.units_indexed == 2
    assert embedder.document_texts == [unit.embedding_text() for unit in parser.units]
    assert index.upserted_units == parser.units

@pytest.mark.asyncio
async def test_empty_document_never_writes_qdrant() -> None:
    parser.units = []
    with pytest.raises(EmptyDocument):
        await processor.ingest("empty.pdf", b"%PDF", metadata)
    assert index.upsert_calls == 0

@pytest.mark.asyncio
async def test_qdrant_failure_remains_an_error() -> None:
    index.upsert_error = RuntimeError("qdrant unavailable")
    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        await processor.ingest("paper.pdf", b"%PDF", metadata)
~~~

- [x] **Step 2: Run RED**

Run: python -m pytest tests/unit/test_literature_processing.py -q

Expected: FAIL because DocumentProcessor is absent.

- [x] **Step 3: Implement minimal orchestration**

Parse, reject an empty unit list, call embed_documents with every embedding_text, require the vector count to equal the unit count, ensure the collection, upsert once, and return document ID plus unit count and extracted metadata. Delete delegates to the index. Do not add retries, SQLite writes, status, hashes, or versions.

- [x] **Step 4: Run GREEN**

Run: python -m pytest tests/unit/test_literature_processing.py -q

Expected: PASS.

- [x] **Step 5: Commit**

~~~text
git add backend/src/deep_research/application backend/tests/fakes.py backend/tests/unit/test_literature_processing.py
git commit -m "feat: add synchronous literature ingestion"
~~~

---

### Task 4: Query routing, retrieval, reranking, and context

**Files:**
- Create: backend/src/deep_research/application/query_router.py
- Create: backend/src/deep_research/application/query_enhancer.py
- Create: backend/src/deep_research/application/retriever.py
- Create: backend/src/deep_research/application/context_builder.py
- Create: backend/src/deep_research/prompts/literature.py
- Test: backend/tests/unit/test_literature_retrieval.py

**Interfaces:**
- Consumes StructuredModel, EmbeddingProvider, LiteratureIndex, and CandidateReranker.
- Produces QueryRouter.route, QueryEnhancer.expand, LiteratureRetriever.search, and ContextBuilder.build.

- [x] **Step 1: Write failing route and retrieval tests**

~~~python
@pytest.mark.asyncio
async def test_direct_route_embeds_original_query_once() -> None:
    router.result = QueryDecision(mode="direct", reason="simple")
    results = await retriever.search(LiteratureSearchRequest(query="RAG是什么"))
    assert embedder.query_texts == ["RAG是什么"]
    assert results[0].unit.unit_id == expected_unit.unit_id

@pytest.mark.asyncio
async def test_mqe_uses_at_most_three_queries_and_deduplicates() -> None:
    router.result = QueryDecision(mode="mqe", reason="multi-aspect")
    enhancer.queries = ["问题一", "问题二", "问题三"]
    results = await retriever.search(request)
    assert embedder.query_texts == ["问题一", "问题二", "问题三"]
    assert len({item.unit.unit_id for item in results}) == len(results)

@pytest.mark.asyncio
async def test_context_adds_existing_neighbors_once() -> None:
    context = await builder.build([primary_result])
    assert context.text.count(str(primary_result.unit.unit_id)) == 1
    assert str(neighbor.unit_id) in context.text
~~~

- [x] **Step 2: Run RED**

Run: python -m pytest tests/unit/test_literature_retrieval.py -q

Expected: FAIL because application retrieval modules are absent.

- [x] **Step 3: Implement structured routing outputs**

~~~python
class QueryDecision(BaseModel, frozen=True):
    mode: Literal["direct", "mqe", "hyde"]
    reason: str = Field(min_length=1)

class ExpandedQueries(BaseModel, frozen=True):
    queries: list[str] = Field(min_length=1, max_length=3)

class HypotheticalPassage(BaseModel, frozen=True):
    text: str = Field(min_length=1)
~~~

The prompt states generated queries and hypothetical passages are retrieval keys only.

- [x] **Step 4: Implement retrieval**

For every routed query, call embed_query and Qdrant search with candidate_limit. Deduplicate by unit_id while retaining the highest similarity score. Rerank at most candidate_limit items and return top_k. Direct route uses the original query; MQE uses no more than three outputs; HyDE uses one generated passage.

- [x] **Step 5: Implement context construction**

Fetch previous and next unit IDs for selected units, preserve primary rank before neighbors, deduplicate unit IDs, and stop before rag_context_max_chars. Serialize each block with unit ID, title, section, pages, and text.

- [x] **Step 6: Run GREEN**

Run: python -m pytest tests/unit/test_literature_retrieval.py -q

Expected: PASS.

- [x] **Step 7: Commit**

~~~text
git add backend/src/deep_research/application backend/src/deep_research/prompts/literature.py backend/tests/unit/test_literature_retrieval.py
git commit -m "feat: add literature retrieval pipeline"
~~~

---

### Task 5: Upload, search, delete, and production wiring

**Files:**
- Create: backend/src/deep_research/api/literature_routes.py
- Modify: backend/src/deep_research/api/main.py
- Modify: backend/src/deep_research/api/schemas.py
- Test: backend/tests/integration/test_literature_api.py
- Modify: backend/tests/integration/test_api.py

**Interfaces:**
- Consumes DocumentProcessor and LiteratureRetriever.
- Produces POST documents, POST search, and DELETE documents by document ID.
- Produces application.state.literature_application with injectable test support.

- [x] **Step 1: Write failing API tests**

~~~python
@pytest.mark.asyncio
async def test_upload_indexes_document(async_client) -> None:
    response = await async_client.post(
        "/api/v1/literature/documents",
        files={"file": ("paper.pdf", b"%PDF", "application/pdf")},
        data={"metadata_json": '{"title":"RAG论文","authors":["张三"],"tags":["RAG"]}'},
    )
    assert response.status_code == 201
    assert response.json()["units_indexed"] == 2

@pytest.mark.asyncio
async def test_search_returns_units(async_client) -> None:
    response = await async_client.post(
        "/api/v1/literature/search",
        json={"query": "混合检索", "limit": 5},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["text"]

@pytest.mark.asyncio
async def test_oversized_upload_stops_before_parsing(async_client) -> None:
    response = await async_client.post(
        "/api/v1/literature/documents",
        files={"file": ("large.pdf", b"x" * 101, "application/pdf")},
    )
    assert response.status_code == 413
    assert fake_parser.calls == []
~~~

- [x] **Step 2: Run RED**

Run: python -m pytest tests/integration/test_literature_api.py tests/integration/test_api.py -q

Expected: FAIL because literature routes are absent.

- [x] **Step 3: Add request and response contracts**

Upload accepts a file and optional metadata_json validated as LiteratureMetadata. Search accepts query, limit, document IDs, tags, language, and year range. Map unsupported input to 415, empty documents to 422, missing RAG application to 503, and infrastructure failure to 502.

- [x] **Step 4: Wire production adapters**

When rag_enabled is true, the lifespan creates one shared embedding provider for Docling tokenization, ingestion, and queries; one AsyncQdrantClient; one index; one reranker; and the application services. Include the router unconditionally so disabled mode returns 503 instead of removing endpoints.

- [x] **Step 5: Run GREEN**

Run: python -m pytest tests/integration/test_literature_api.py tests/integration/test_api.py -q

Expected: PASS.

- [x] **Step 6: Commit**

~~~text
git add backend/src/deep_research/api backend/tests/integration/test_api.py backend/tests/integration/test_literature_api.py
git commit -m "feat: expose literature ingestion and search APIs"
~~~

---

### Task 6: Grounded literature answers

**Files:**
- Create: backend/src/deep_research/application/answer_service.py
- Modify: backend/src/deep_research/api/literature_routes.py
- Modify: backend/src/deep_research/api/main.py
- Modify: backend/src/deep_research/prompts/literature.py
- Test: backend/tests/unit/test_literature_answers.py
- Test: backend/tests/integration/test_literature_api.py

**Interfaces:**
- Consumes LiteratureRetriever, ContextBuilder, and StructuredModel.
- Produces AnswerService.answer and POST /api/v1/literature/answer.

- [x] **Step 1: Write failing citation tests**

~~~python
@pytest.mark.asyncio
async def test_answer_accepts_selected_unit_citations() -> None:
    model.output = {
        "answer": "该文献支持混合检索。",
        "citation_unit_ids": [str(selected.unit.unit_id)],
    }
    answer = await service.answer(request)
    assert answer.citations[0].page_start == 12

@pytest.mark.asyncio
async def test_answer_rejects_unknown_unit_citation() -> None:
    model.output = {
        "answer": "没有依据的回答。",
        "citation_unit_ids": ["33333333-3333-4333-8333-333333333333"],
    }
    with pytest.raises(InvalidLiteratureCitation):
        await service.answer(request)

@pytest.mark.asyncio
async def test_answer_reports_insufficient_evidence() -> None:
    retriever.results = []
    with pytest.raises(InsufficientLiteratureEvidence):
        await service.answer(request)
~~~

- [x] **Step 2: Run RED**

Run: python -m pytest tests/unit/test_literature_answers.py tests/integration/test_literature_api.py -q

Expected: FAIL because AnswerService and the endpoint are absent.

- [x] **Step 3: Implement grounded generation**

The prompt contains only ContextBuilder output and requires cited unit IDs. Parse LiteratureAnswerDraft, derive allowed IDs from the actual context, reject any unknown ID, and build LiteratureCitation values from cited payloads. Do not return generated text after citation validation fails.

- [x] **Step 4: Add the endpoint**

Map insufficient evidence to HTTP 409 and invalid model citations to HTTP 502.

- [x] **Step 5: Run GREEN**

Run: python -m pytest tests/unit/test_literature_answers.py tests/integration/test_literature_api.py -q

Expected: PASS.

- [x] **Step 6: Commit**

~~~text
git add backend/src/deep_research/application/answer_service.py backend/src/deep_research/api/literature_routes.py backend/src/deep_research/api/main.py backend/src/deep_research/prompts/literature.py backend/tests/unit/test_literature_answers.py backend/tests/integration/test_literature_api.py
git commit -m "feat: add grounded literature answers"
~~~

---

### Task 7: Deep Research evidence integration

**Files:**
- Create: backend/src/deep_research/application/research_adapter.py
- Modify: backend/src/deep_research/domain/evidence.py
- Modify: backend/src/deep_research/services/evidence_store.py
- Modify: backend/src/deep_research/state/models.py
- Modify: backend/src/deep_research/state/reducers.py
- Modify: backend/src/deep_research/graph/builder.py
- Modify: backend/src/deep_research/nodes/researcher.py
- Modify: backend/src/deep_research/services/citations.py
- Modify: backend/src/deep_research/persistence/memory_store.py
- Modify: backend/src/deep_research/services/runtime.py
- Modify: backend/src/deep_research/api/schemas.py
- Modify: backend/src/deep_research/api/routes.py
- Modify: backend/src/deep_research/api/main.py
- Modify: backend/tests/fakes.py
- Test: backend/tests/integration/test_literature_research.py
- Test: backend/tests/unit/test_security.py
- Test: backend/tests/unit/test_citations.py

**Interfaces:**
- Consumes LiteratureRetriever and the existing evidence-extraction model.
- Produces LiteratureSource, EvidenceSource, ResearchAdapter.search, and use_literature request/state flow.

- [x] **Step 1: Write failing source and integration tests**

~~~python
def test_literature_source_needs_no_url() -> None:
    source = LiteratureSource(
        source_id="lit-source-1",
        document_id=document_id,
        unit_id=unit_id,
        title="RAG论文",
        authors=["张三"],
        publication_year=2025,
        page_start=12,
        page_end=13,
        retrieved_at=datetime.now(UTC),
    )
    assert source.source_kind == "literature"

def test_web_source_still_rejects_localhost() -> None:
    with pytest.raises(ValidationError):
        make_web_source("http://localhost/private")

@pytest.mark.asyncio
async def test_researcher_admits_literature_as_current_run_evidence() -> None:
    result = await graph.ainvoke(input_with_use_literature)
    assert any(
        source.source_kind == "literature"
        for source in result["sources"].values()
    )
    assert all(
        item.source_id in result["sources"]
        for item in result["evidence"].values()
    )
~~~

- [x] **Step 2: Run RED**

Run: python -m pytest tests/integration/test_literature_research.py tests/unit/test_security.py tests/unit/test_citations.py -q

Expected: FAIL because literature sources and graph wiring are absent.

- [x] **Step 3: Add the source union**

Add source_kind with default web to the existing Source for checkpoint compatibility. Add LiteratureSource with document ID, unit ID, title, authors, year, DOI, heading, pages, and retrieval time, with no URL. Define EvidenceSource as Source or LiteratureSource. Update reducers, state, snapshots, memory archives, and citation rendering to accept the union.

- [x] **Step 4: Implement ResearchAdapter**

For each Researcher query, retrieve local units, create LiteratureSource values, run the existing evidence extraction model over unit text, and build EvidenceItem values with title, heading, and page context. Only these current-run evidence items enter Writer.

- [x] **Step 5: Wire use_literature**

Add use_literature to start request, runtime initial state, WorkflowDependencies, Researcher input, and frontend request. Default it to false. When true, retrieve literature before web search. If RAG is unavailable, return a visible literature_unavailable ResearchError rather than pretending it was searched.

- [x] **Step 6: Run focused and graph regression tests**

Run: python -m pytest tests/integration/test_literature_research.py tests/integration/test_research_graph.py tests/integration/test_researcher_graph.py tests/unit/test_security.py tests/unit/test_citations.py tests/unit/test_reducers.py -q

Expected: PASS.

- [x] **Step 7: Commit**

~~~text
git add backend/src/deep_research/application/research_adapter.py backend/src/deep_research/domain/evidence.py backend/src/deep_research/services/evidence_store.py backend/src/deep_research/state backend/src/deep_research/graph/builder.py backend/src/deep_research/nodes/researcher.py backend/src/deep_research/services/citations.py backend/src/deep_research/persistence/memory_store.py backend/src/deep_research/services/runtime.py backend/src/deep_research/api backend/tests
git commit -m "feat: use literature evidence in deep research"
~~~

---

### Task 8: Literature frontend

**Files:**
- Create: frontend/src/types/literature.ts
- Create: frontend/src/api/literature.ts
- Create: frontend/src/components/LiteraturePanel.vue
- Create: frontend/src/components/LiteraturePanel.test.ts
- Modify: frontend/src/App.vue
- Modify: frontend/src/App.test.ts
- Modify: frontend/src/components/ResearchForm.vue
- Modify: frontend/src/api/research.ts
- Modify: frontend/src/stores/research.ts
- Modify: frontend/src/types/research.ts
- Modify: frontend/src/style.css

**Interfaces:**
- Consumes Task 5 and Task 6 HTTP contracts.
- Produces upload, search, answer, citations, delete, and use_literature controls.

- [x] **Step 1: Write failing UI tests**

~~~typescript
it("uploads a document and shows indexed unit count", async () => {
  const wrapper = mount(LiteraturePanel, { props: { api: fakeApi } });
  await wrapper.get('input[type="file"]').setValue(pdfFile);
  await wrapper.get('[data-action="upload"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("2 searchable units");
});

it("renders answer citations with pages", async () => {
  const wrapper = mount(LiteraturePanel, { props: { api: fakeApi } });
  await wrapper.get('[data-field="question"]').setValue("什么是RAG？");
  await wrapper.get('[data-action="answer"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("RAG论文");
  expect(wrapper.text()).toContain("第 12–13 页");
});
~~~

Add a ResearchForm test proving use_literature is emitted and sent.

- [x] **Step 2: Run RED**

Run: npm run test:run -- src/components/LiteraturePanel.test.ts src/App.test.ts

Expected: FAIL because the new UI and API are absent.

- [x] **Step 3: Implement typed API and compact panel**

The panel contains file upload with metadata, semantic search, result snippets, question answering, citation display, delete, busy states, and explicit errors. It has no ingestion-progress UI because processing is synchronous.

- [x] **Step 4: Add the research checkbox**

Add Use literature to ResearchForm and send use_literature from startResearch. Keep the default false.

- [x] **Step 5: Run GREEN and build**

Run: npm run test:run

Expected: PASS.

Run: npm run build

Expected: PASS.

- [x] **Step 6: Commit**

~~~text
git add frontend/src
git commit -m "feat: add literature RAG interface"
~~~

---

### Task 9: Documentation and full verification

**Files:**
- Modify: README.md
- Modify: docs/superpowers/specs/2026-09-23-literature-rag-design.md
- Modify: docs/superpowers/plans/2026-09-23-literature-rag-implementation.md

**Interfaces:**
- Consumes all shipped settings and commands.
- Produces reproducible setup and verification instructions.

- [x] **Step 1: Document setup**

Add installation with the rag extra, a pinned Qdrant container command, environment variables, model download behavior, upload/search/answer examples, use_literature, and the fact that a failed synchronous import must be submitted again.

- [x] **Step 2: Run backend quality gates**

Run: python -m ruff check src tests

Expected: PASS.

Run: python -m pytest -q

Expected: PASS.

- [x] **Step 3: Run frontend quality gates**

Run: npm run test:run

Expected: PASS.

Run: npm run build

Expected: PASS.

- [x] **Step 4: Verify architecture constraints**

Run:

~~~powershell
Get-ChildItem backend/src/deep_research -Recurse -File |
  Select-String -Pattern 'literature_versions|ingestion_jobs|sparse_vector|active_generation'
~~~

Expected: no matches in production RAG code.

Inspect one integration-test Qdrant point and confirm it has exactly one vector and a payload containing title, authors, publication year, DOI, language, tags, heading path, pages, content type, neighbor IDs, and text.

- [x] **Step 5: Commit**

~~~text
git add README.md docs/superpowers/specs/2026-09-23-literature-rag-design.md docs/superpowers/plans/2026-09-23-literature-rag-implementation.md
git commit -m "docs: document literature RAG setup"
~~~



## Verification result

Completed on 2026-09-23:

- Backend: `python -m ruff check src tests evals` passed.
- Backend: `python -m pytest -q` passed with 236 tests.
- Frontend: `npm run test:run` passed with 31 tests.
- Frontend: `npm run build` passed.
- Production RAG code contains no sparse vectors, ingestion-job tables, version tables, or index generations.
