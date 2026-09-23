# Literature RAG System Design

- Date: 2026-09-23
- Status: Implemented
- Scope: Single-vector literature ingestion, retrieval, question answering, and Deep Research integration

## 1. Architecture decision

The RAG subsystem uses:

- Docling for document parsing and OCR.
- Structure-aware chunking for headings, paragraphs, tables, pages, and neighboring chunks.
- One configurable multilingual embedding model for both document units and queries.
- Qdrant as the only RAG data store.
- One Qdrant point per searchable unit, containing the vector and the complete searchable payload.
- Optional direct query, multi-query expansion, or HyDE before retrieval.
- Candidate reranking, Top-K context construction, answer generation, and citation validation.

The RAG subsystem does not create SQLite tables. Existing SQLite checkpoint and research-memory storage remains unchanged and is outside this subsystem.

## 2. Data preparation

~~~text
Raw document
-> preprocessing
-> Docling parsing and OCR when required
-> structure-aware chunking
-> metadata extraction
-> searchable-unit construction
-> single embedding model
-> Qdrant
~~~

A searchable unit contains:

- unit ID and document ID;
- title, authors, publication year, DOI, language, and tags;
- heading path, page range, content type, and neighboring unit IDs;
- the complete chunk text.

The embedding input contains the semantically useful fields: title, authors, year, tags, heading path, and chunk text. Page numbers and technical IDs remain in the payload but are not added to the embedding text.

Each Qdrant point has:

~~~text
id: unit_id
vector: one embedding vector
payload:
  document_id
  title
  authors
  publication_year
  doi
  language
  tags
  heading_path
  page_start
  page_end
  content_type
  previous_unit_id
  next_unit_id
  text
~~~

The first version does not persist file versions, hashes, storage locations, parser status, index generations, ingestion progress, retry state, or separate metadata records. A failed import returns an explicit error and the document can be imported again.

## 3. Retrieval and generation

~~~text
User query
-> query-type decision
-> direct query, MQE, or HyDE
-> query embedding with the same model
-> Qdrant similarity search
-> candidate reranking
-> Top-K passages
-> neighboring-passage expansion
-> context construction
-> LLM generation
-> citation validation
-> final answer
~~~

Query routing rules:

- Basic search and direct factual questions use the original query.
- Multi-aspect questions may generate at most three focused subqueries.
- HyDE generates one hypothetical passage only for terminology mismatch or weak direct retrieval.

Generated queries and hypothetical text are retrieval aids and cannot be cited.

## 4. Application structure

~~~text
api/
  literature_routes.py

application/
  document_processor.py
  query_router.py
  query_enhancer.py
  retriever.py
  reranker.py
  context_builder.py
  answer_service.py
  research_adapter.py

domain/
  literature.py

infrastructure/
  docling_parser.py
  embedding_provider.py
  qdrant_index.py
  cross_encoder_reranker.py
~~~

Responsibilities:

- DocumentProcessor parses documents, builds searchable units, embeds them, and writes Qdrant points.
- QueryRouter selects direct, MQE, or HyDE retrieval.
- QueryEnhancer produces bounded retrieval queries.
- Retriever embeds queries and searches Qdrant.
- Reranker orders candidates.
- ContextBuilder selects Top-K units and compatible neighbors.
- AnswerService generates answers and validates unit citations.
- ResearchAdapter turns retrieved units into current-run evidence for the existing research graph.

## 5. API

~~~text
POST /api/v1/literature/documents
POST /api/v1/literature/search
POST /api/v1/literature/answer
DELETE /api/v1/literature/documents/{document_id}
~~~

The upload endpoint processes a document synchronously in the first version and returns document ID, unit count, and extracted metadata.

Search returns ranked searchable units with pages and headings. Answer returns grounded text and validated unit citations. Delete removes every Qdrant point with the document ID.

## 6. Deep Research integration

Research requests add use_literature. Researcher may search local literature before web search. A selected unit becomes a LiteratureSource plus an EvidenceItem in the current run. Writer and finalizer may cite it only after this conversion.

Web sources retain public HTTP URL validation. Literature sources use document and unit identifiers and never use file or localhost URLs.

## 7. Acceptance criteria

- A supported document produces searchable Qdrant units containing all required metadata and text.
- The same embedding provider is used for document and query vectors.
- No sparse vector or second RAG database is created.
- Search results retain document, heading, and page provenance.
- Direct answers contain only citations returned by retrieval.
- Invalid unit citations are rejected.
- Deep Research citations still pass the existing current-run evidence validator.
- Parser, embedding, Qdrant, reranking, and generation failures remain explicit.
