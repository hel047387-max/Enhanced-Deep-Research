# Literature RAG System Design

- Date: 2026-09-23
- Status: Architecture option B selected; specification pending user review
- Scope: Design only; no production implementation in this change
- Target: Existing single-instance FastAPI, SQLite, and LangGraph application

## 1. Decision

Add a literature RAG subsystem with this storage split:

- SQLite is the source of truth for document identity, versions, ingestion jobs, chunk metadata, and active index state.
- Local storage holds immutable original files and normalized parser artifacts.
- Qdrant stores dense and sparse retrieval vectors plus a denormalized filter payload.
- Docling parses PDFs and preserves headings, pages, tables, reading order, and OCR provenance.
- One configured multilingual embedding profile is shared by ingestion and queries. A multilingual cross-encoder reranks fused candidates.

Qdrant is a derived index. The application can rebuild it from SQLite and local parser artifacts. A Qdrant write alone never marks a document ready.

## 2. Goals

The first production version must:

1. Import existing PDF, DOCX, Markdown, HTML, and plain-text literature.
2. Preserve document, version, page, section, and chunk provenance.
3. Support Chinese, English, and mixed-language retrieval.
4. Combine semantic retrieval with exact-term retrieval.
5. Answer direct literature questions with traceable page-level citations.
6. Make selected literature available to the existing deep-research workflow.
7. Convert retrieved passages into current-run evidence before Writer can cite them.
8. Recover interrupted ingestion and rebuild the vector index without losing the catalog.
9. Let users inspect, reindex, disable, and delete literature.

## 3. Non-goals for the first version

- Multi-user authorization and tenant isolation.
- Cloud object storage or a distributed ingestion queue.
- Knowledge graphs and entity-relation extraction.
- Automatic interpretation of charts, diagrams, or scanned figures.
- Academic citation-style management.
- Treating retrieved text as a verified fact without evidence admission.

Scanned documents may use OCR, but the system exposes OCR provenance and confidence. Figure understanding can follow after text and table retrieval have real evaluation data.

## 4. Architectural context

The application already has FastAPI and SSE, a resumable LangGraph workflow with SQLite checkpoints, Source and EvidenceItem models, deterministic citation validation, and research memory.

Literature RAG is a separate knowledge source:

- Research memory recalls previous reports, conclusions, limitations, and open questions.
- Literature RAG retrieves passages from user-managed source documents.
- Web search retrieves current external material.

All three may inform planning. Only evidence admitted into the current run may appear as citations in that run.

## 5. System architecture

~~~mermaid
flowchart LR
    subgraph Ingestion[Document ingestion]
        U[Upload or managed import] --> V[Validate and hash]
        V --> F[Store original file]
        F --> P[Docling parse and OCR]
        P --> C[Structure-aware chunking]
        C --> E[Dense and sparse encoding]
        E --> QW[Write inactive Qdrant generation]
        QW --> A[Activate generation in SQLite]
    end

    subgraph Storage[Persistent storage]
        S[(SQLite catalog)]
        L[(Local files and artifacts)]
        Q[(Qdrant literature_chunks_v1)]
    end

    V --> S
    F --> L
    P --> L
    C --> S
    QW --> Q
    A --> S

    subgraph Retrieval[Query and generation]
        RQ[User query or research task] --> QR[Query router]
        QR --> QE[Bounded query expansion]
        QE --> HR[Dense plus sparse retrieval]
        HR --> FU[RRF fusion and document grouping]
        FU --> RR[Cross-encoder reranking]
        RR --> NE[Neighbor expansion and context packing]
        NE --> EV[Current-run evidence admission]
        EV --> AN[Answer or research Writer]
        AN --> CV[Citation validation and rendering]
    end

    HR --> Q
    NE --> S
    NE --> L
~~~

## 6. Component boundaries

### 6.1 Literature catalog

Owns document identity, version history, metadata, visibility, lifecycle state, and deletion. SQLite is authoritative.

### 6.2 Ingestion service

Validates uploads, stores immutable originals, invokes parsing, builds chunks, generates vectors, updates Qdrant, and changes the active index generation through an explicit state machine. It runs outside the research graph, so document processing does not consume research budgets or block checkpoint recovery.

### 6.3 Retrieval service

Accepts a typed query and metadata filters, executes hybrid retrieval, fuses and reranks candidates, expands adjacent context, and returns typed RetrievedPassage values. It does not generate answers and does not silently fall back to the web.

### 6.4 Literature answer service

Handles direct questions scoped to the library. It builds context from retrieved passages, generates an answer, validates cited passage IDs, and renders literature citations.

### 6.5 Deep-research adapter

Exposes retrieval through a LiteratureSearchProvider protocol. It converts selected passages into current-run sources and evidence. Planner decides whether a task uses literature, web, or both; Researcher remains responsible for evidence sufficiency.

## 7. Data model

### 7.1 SQLite tables

#### literature_documents

| Field | Purpose |
| --- | --- |
| document_id | Stable UUID for the logical work |
| title | Display title |
| authors_json | Ordered author names |
| publication_year | Optional publication year |
| doi | Normalized DOI when available |
| language | Detected or user-supplied language |
| tags_json | User-managed tags |
| status | active, disabled, or deleted |
| created_at, updated_at | Catalog timestamps |

#### literature_versions

| Field | Purpose |
| --- | --- |
| version_id | Immutable UUID for one file version |
| document_id | Parent document |
| content_hash | SHA-256 of original bytes; unique for active imports |
| original_name | Sanitized display filename |
| media_type, byte_size | File validation fields |
| source_kind | upload or managed_path |
| original_path | Server-generated relative path |
| artifact_path | Relative path to normalized parser output |
| parser_name, parser_version | Reproducibility |
| page_count | Parsed page count when available |
| status | Ingestion state |
| active_generation | Qdrant generation visible to retrieval |
| index_profile | Parser, chunker, embedding, sparse, and reranker versions |
| error_code, error_message | Actionable terminal failure |
| created_at, indexed_at | Lifecycle timestamps |

#### ingestion_jobs

Stores job_id, version_id, stage, attempt number, progress counts, timestamps, cancellation state, and structured errors. One active job is allowed per version.

#### literature_chunks

| Field | Purpose |
| --- | --- |
| chunk_id | Deterministic ID derived from version and structural location |
| version_id, document_id | Provenance |
| generation | Index generation |
| ordinal | Stable reading order |
| heading_path_json | Section hierarchy |
| page_start, page_end | Page range |
| token_count | Packing and diagnostics |
| text | Normalized chunk text |
| text_hash | Deduplication and integrity |
| previous_chunk_id, next_chunk_id | Neighbor expansion |
| content_kind | paragraph, table, list, bibliography, or ocr_text |
| parser_metadata_json | Bounding boxes and parser provenance |

SQLite indices cover DOI, content hash, status, publication year, language, tags, and the tuple of version, generation, and ordinal.

### 7.2 Local storage

~~~text
data/literature/
  originals/{document_id}/{version_id}/source.ext
  artifacts/{document_id}/{version_id}/document.json
  artifacts/{document_id}/{version_id}/tables/
~~~

Paths are generated from validated UUIDs. API input never becomes a filesystem path. Originals are immutable; changed bytes create a new version.

### 7.3 Qdrant collection

Use collection literature_chunks_v1 with named vectors:

- dense: cosine vector from the configured multilingual embedding model.
- sparse: sparse BM25-style vector for exact terms, names, formulas, and identifiers.

Each point represents one chunk. Its ID is deterministic from chunk_id and generation. Payload contains filter and display fields: document and version IDs, chunk ID, generation, status, title, authors, year, language, tags, page range, heading path, and content kind.

Full chunk text remains authoritative in SQLite. It may also be stored in Qdrant for diagnostics, but results are hydrated and checked against SQLite before use. Payload indexes exist only for fields used in filters.

## 8. Identity, deduplication, and versioning

- Exact duplicate bytes reuse the existing version and do not enqueue a new job.
- DOI may suggest that files belong to the same logical document, but a DOI match never discards different bytes.
- A new file for the same work creates a new immutable version.
- Only one version is active by default; users may explicitly search older versions.
- chunk_id is based on version ID, heading path, page range, ordinal, and text hash.
- Embedding model, sparse encoder, reranker, chunker, and parser versions form the index profile.
- Changing a retrieval-critical component creates a new generation instead of mutating the active one.

## 9. Ingestion workflow

~~~text
queued -> validating -> parsing -> chunking -> embedding -> indexing -> ready
                                                          \-> failed
Any nonterminal state -> cancelling -> cancelled
ready -> reindexing -> ready
~~~

Processing rules:

1. Validate extension, detected media type, byte size, and file hash.
2. Write to a temporary managed file, flush it, then atomically rename it.
3. Parse with Docling. Record OCR use, page mapping, hierarchy, tables, and warnings.
4. Normalize whitespace without removing section boundaries, table labels, references, units, or formulas.
5. Build chunks using document structure first and token size second.
6. Persist the inactive chunk generation to SQLite.
7. Batch-generate dense and sparse vectors with the query index profile.
8. Upsert Qdrant points with the inactive generation.
9. Verify expected point count and sample IDs.
10. Atomically switch active_generation and mark the version ready in SQLite.
11. Remove the previous Qdrant generation after a configurable grace period.

If the process stops before activation, retrieval keeps using the previous generation. Startup recovery scans nonterminal jobs and resumes from the last durable stage. A failed document is never reported as ready.

## 10. Chunking strategy

- Use Docling hybrid chunking as the base.
- Target 400 to 800 tokens per prose chunk, with a hard 1,000-token maximum before encoding.
- Preserve the heading path and keep paragraphs intact when possible.
- Keep small tables with captions and headers.
- Split large tables by row groups while repeating headers and captions.
- Preserve page ranges and ordinal neighbors.
- Use 10 to 15 percent overlap only when splitting a long logical section.
- Keep bibliography entries separate from surrounding prose.

At retrieval time, one adjacent chunk may be added before or after a selected chunk when it shares the heading path and fits the context budget. Each neighbor retains its own passage ID.

## 11. Retrieval workflow

### 11.1 Typed request

LiteratureQuery contains query text; optional document IDs, tags, language, year range, authors, and content kinds; a purpose of direct_answer, research_task, or library_search; and result and token budgets.

### 11.2 Query routing

The default route uses the original query:

- Direct factual or definitional query: no expansion.
- Comparison, multi-aspect, or ambiguous task: at most three focused subqueries.
- HyDE: one hypothetical passage only when original and expanded queries have weak scores or likely terminology mismatch.

Generated queries are retrieval inputs and never evidence.

### 11.3 Candidate retrieval

For each query:

1. Apply visibility and version filters in Qdrant.
2. Retrieve up to 40 dense candidates.
3. Retrieve up to 40 sparse candidates.
4. Fuse rankings with reciprocal-rank fusion.
5. Deduplicate identical chunk IDs and near-identical text hashes.
6. Limit early dominance to five candidates per document.

Dense and sparse rankings start with equal influence. Tune only after evaluation data supports a change.

### 11.4 Reranking and packing

- Rerank at most 30 fused candidates with a multilingual cross-encoder.
- Select 8 to 12 final passages within the token budget.
- Use at most three primary passages from one document unless the query scopes to it.
- Add compatible neighbors after primary selection.
- Hydrate text from SQLite and reject missing, disabled, deleted, or generation-mismatched chunks.
- Return stage scores for diagnostics without treating them as calibrated confidence.

If no passage meets the threshold, return insufficient_literature_evidence. Direct Q&A asks the user to broaden filters or add material. Deep research may continue with web search only when its source policy allows it.

## 12. Evidence and citation integration

### 12.1 Source model change

The existing Source requires public HTTP URLs. That remains correct for web fetching but cannot represent managed literature. URL validation must not be weakened, and the system must not invent file or localhost URLs.

Introduce a discriminated union:

~~~text
EvidenceSource = WebSource | LiteratureSource

WebSource
  source_kind = web
  existing public URL fields and validation

LiteratureSource
  source_kind = literature
  source_id, document_id, version_id, title
  authors, publication_year, doi
  content_hash, retrieved_at
~~~

Reducers, state, archive persistence, citation validation, and rendering accept EvidenceSource. Network tools accept only WebSource. This keeps SSRF policy attached to the web boundary.

### 12.2 Current-run evidence admission

Each admitted passage becomes an EvidenceItem with a run-scoped ID, its literature source ID, a claim produced by the evidence extraction step, a bounded verbatim excerpt, heading and page context, task ID, relevance, and a label such as Zhang et al. (2025), pp. 12-13.

The adapter records version_id, chunk_id, and page range in typed provenance instead of only free text. Writer sees the same current-run evidence map used for web evidence. Finalizer validates every cited evidence ID before rendering.

Retrieved chunks not admitted as evidence may guide query refinement but cannot be cited. Memory-card evidence from older research also stays outside the current-run evidence set.

### 12.3 Direct literature answers

Direct answers use passage IDs during generation. The service rejects unknown IDs and renders a source list with title, authors, year, version, and pages. A document-view endpoint resolves citations; raw filesystem paths are never exposed.

## 13. LangGraph integration

Add literature_retriever to WorkflowDependencies behind a protocol. Add state fields for use_literature, literature_scope, compact literature_inventory, cited literature_references, and bounded retrieval_diagnostics.

The top-level flow becomes:

~~~text
clarify -> research_brief -> memory_recall -> literature_inventory -> planner
        -> supervisor/researchers -> writer -> reviewer -> finalizer
~~~

literature_inventory returns compact metadata and coverage hints, not full chunks. Planner assigns each task one source policy:

- literature_only
- web_only
- literature_then_web
- literature_and_web

Researcher executes that policy with separate literature and web query budgets. Literature retrieval does not consume the web query counter. Supervisor measures evidence coverage and source diversity across both types.

Graph checkpoints hold compact evidence and identifiers. Parser artifacts, vectors, and full candidate lists stay outside graph state.

## 14. APIs and SSE

### 14.1 Library management

- POST /api/v1/literature/documents: upload and return document, version, and job IDs.
- POST /api/v1/literature/import: import from an explicitly configured managed directory.
- GET /api/v1/literature/documents: list and filter.
- GET /api/v1/literature/documents/{document_id}: metadata and versions.
- GET /api/v1/literature/documents/{document_id}/content: authorized original or rendered page.
- PATCH /api/v1/literature/documents/{document_id}: metadata, active version, or disabled state.
- POST /api/v1/literature/documents/{document_id}/reindex: create a generation.
- DELETE /api/v1/literature/documents/{document_id}: delete catalog, files, chunks, and Qdrant points.
- GET /api/v1/literature/jobs/{job_id}: ingestion status.

Deletion is explicit and idempotent. SQLite hides the record before cleanup; retrying cleanup never restores visibility.

### 14.2 Search and answering

- POST /api/v1/literature/search: ranked passages and allowed diagnostics.
- POST /api/v1/literature/answer: grounded answer and literature citations.
- Research requests add use_literature and optional document, tag, author, language, and year filters.

### 14.3 SSE events

Add literature_ingestion_started, literature_ingestion_progress, literature_ingestion_completed, literature_ingestion_failed, literature_retrieved, and literature_retrieval_insufficient. Events expose counts, source IDs, and outcomes, not chain-of-thought or document text.

## 15. Frontend

Add a Literature Library area with upload and batch progress, catalog filters, document details and versions, parser warnings, page preview, reindex, disable and delete actions, hybrid search results, direct Q&A with clickable citations, research-scope controls, plan source policies, and report citations that open the relevant page.

The UI displays separate uploaded, processing, ready, failed, disabled, and deleting states. It never implies that an upload is searchable before activation.

## 16. Configuration and deployment

Configuration covers the literature data directory, formats and upload size, Qdrant connection and collection, pinned dense, sparse, and reranker models, device and batch settings, chunk targets, retrieval budgets and thresholds, OCR languages, job concurrency, and feature flags.

Local deployment adds Qdrant as a pinned container with a persistent volume. Model artifacts are downloaded during an explicit setup step or mounted from a cache. Startup reports RAG ready only after SQLite migrations, model loading, Qdrant health, and collection-profile checks succeed.

## 17. Failure handling

- Parser failure marks the version failed and retains the original for retry.
- Model-loading failure disables RAG boundaries while unrelated web research remains available.
- Qdrant outage leaves the catalog readable and returns a typed service-unavailable error for search.
- Partial batches remain inactive and can be overwritten safely.
- Profile mismatch refuses activation and requires reindexing.
- Missing artifacts make the version unavailable and emit an integrity error.
- Cancellation stops at a durable boundary and records cleanup needs.
- Recovery is bounded and visible; exceptions are recorded rather than swallowed.

## 18. Security

- Enforce file-size, page-count, and format limits before parsing.
- Detect media type from content and reject mismatches.
- Generate storage paths server-side and prevent archive traversal.
- Run parsers with bounded CPU, memory, and time.
- Treat document text as untrusted and delimit it clearly in prompts.
- Escape UI snippets and apply a restrictive content security policy.
- Keep Qdrant private and authenticate it outside local development.
- Preserve current public-URL and redirect validation for web sources.
- Redact configured sensitive metadata from logs and traces.

## 19. Observability and evaluation

Record candidate counts per stage, stage and model latency, filter selectivity, document diversity, insufficient-evidence outcomes, cited passage validity, and all index-profile versions.

Build a versioned evaluation set with Chinese, English, mixed-language, identifier, paraphrase, multi-document, unanswerable, table, and OCR queries. Measure recall at 10, mean reciprocal rank, nDCG at 10, citation precision and completeness, unsupported-claim rate, latency, and diversity. Compare dense-only, sparse-only, fused, and fused-plus-reranker pipelines. Release gates prioritize citation correctness and unsupported claims over fluency.

## 20. Implementation modules

~~~text
backend/src/deep_research/
  domain/literature.py
  persistence/literature_store.py
  services/literature_ingestion.py
  services/literature_retrieval.py
  services/literature_answers.py
  tools/literature_search.py
  api/literature_routes.py
~~~

Existing evidence, citations, archives, state, graph builder, runtime, and API modules change through typed interfaces. Qdrant and Docling types remain inside adapters.

## 21. Delivery phases

### Phase 1: Reliable ingestion and catalog

Add migrations, local storage, parser adapter, chunking, recovery, Qdrant setup, library APIs, catalog UI, job progress, reindex, disable, and delete.

Acceptance: supported documents become searchable exactly once; interrupted jobs recover; active generations remain consistent; deletion removes a document from results immediately.

### Phase 2: Hybrid search and direct answers

Add dense and sparse retrieval, RRF, reranking, packing, direct Q&A, citations, and the evaluation harness.

Acceptance: every citation resolves to the stored version, chunk, and pages; unknown IDs cannot pass finalization; unanswerable questions return insufficient evidence.

### Phase 3: Deep-research integration

Add literature inventory, Planner policies, Researcher adapter, combined coverage, SSE events, and research-scope controls.

Acceptance: local passages become current-run evidence; citations validate across web and literature sources; historical memory cannot bypass current-run verification.

### Phase 4: Quality expansion

Tune routing, budgets, models, and chunking from evaluation results. Add figure understanding, citation export, caching, or advanced multi-vector retrieval only when measured failures justify them.

## 22. Test strategy

- Unit tests: validation, IDs, chunks, source unions, filters, fusion, packing, citations, and state transitions.
- Contract tests: parser and Qdrant adapters with minimal fixtures.
- Integration tests: ingest, crash before activation, retry, reindex switch, disable, delete, and rebuild.
- Graph tests: every source policy, empty retrieval, mixed evidence, cancellation, and resume.
- API tests: limits, traversal, jobs, filters, document access, and SSE shapes.
- Frontend tests: ingestion states, filters, citation navigation, and service unavailability.
- Evaluation regressions: fixed corpus and judgments; model upgrades require baseline comparison.

## 23. Risks and tradeoffs

- Qdrant adds an operational service but gives mature hybrid retrieval and filtering while SQLite remains the recoverable authority.
- Local embedding and reranking reduce data exposure but add model setup, memory use, and cold-start time.
- Docling improves layout provenance but adds parser cost and dependency size.
- Hybrid retrieval and reranking improve recall and precision but add latency; fixed budgets bound it.
- Two source types require an evidence-model migration. A discriminated union preserves web security rules and makes citation behavior explicit.

## 24. References

- Qdrant hybrid queries: https://qdrant.tech/documentation/search/hybrid-queries/
- Qdrant payload indexing: https://qdrant.tech/documentation/manage-data/indexing/
- Qdrant multi-representation search: https://qdrant.tech/documentation/tutorials-search-engineering/multi-representation-search/
- Docling chunking: https://docling-project.github.io/docling/concepts/chunking/
- Docling hybrid chunking: https://docling-project.github.io/docling/_generated/examples/hybrid_chunking/
- Sentence Transformers retrieve and rerank: https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html
