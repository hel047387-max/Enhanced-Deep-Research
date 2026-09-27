from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

InitialTasks = Annotated[int, Field(ge=3, le=5)]
SupervisorTasks = Annotated[int, Field(ge=0, le=2)]
ReviewerTasks = Annotated[int, Field(ge=0, le=1)]
ResearchRounds = Annotated[int, Field(ge=1, le=2)]
QueriesPerRound = Annotated[int, Field(ge=1, le=2)]
ConcurrentResearchers = Annotated[int, Field(ge=1, le=3)]
TotalSearchQueries = Annotated[int, Field(ge=1, le=20)]
SourcesPerTask = Annotated[int, Field(ge=1, le=8)]
EvidencePerTask = Annotated[int, Field(ge=1, le=20)]
RagChunkTokens = Annotated[int, Field(ge=64, le=4096)]
RagCandidateLimit = Annotated[int, Field(ge=1, le=200)]
RagTopK = Annotated[int, Field(ge=1, le=50)]
RagContextChars = Annotated[int, Field(ge=1000, le=200_000)]
RagUploadBytes = Annotated[int, Field(ge=1, le=1_073_741_824)]
EmbeddingModelType = Literal["dashscope", "local"]
QdrantDistance = Literal["cosine", "dot", "euclid"]


class ResearchBudgets(BaseModel, frozen=True):
    max_initial_tasks: InitialTasks = 5
    max_supervisor_tasks: SupervisorTasks = 2
    max_reviewer_tasks: ReviewerTasks = 1
    max_research_rounds: ResearchRounds = 2
    max_queries_per_round: QueriesPerRound = 2
    max_concurrent_researchers: ConcurrentResearchers = 3
    max_total_search_queries: TotalSearchQueries = 20
    max_sources_per_task: SourcesPerTask = 8
    max_evidence_per_task: EvidencePerTask = 20


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "openai"
    llm_model: str = "gpt-4.1-mini"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    tavily_api_key: str | None = None
    checkpoint_db_path: Path = Path("./data/checkpoints.sqlite")
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"
    max_initial_tasks: InitialTasks = 5
    max_supervisor_tasks: SupervisorTasks = 2
    max_reviewer_tasks: ReviewerTasks = 1
    max_research_rounds: ResearchRounds = 2
    max_queries_per_round: QueriesPerRound = 2
    max_concurrent_researchers: ConcurrentResearchers = 3
    max_total_search_queries: TotalSearchQueries = 20
    max_sources_per_task: SourcesPerTask = 8
    max_evidence_per_task: EvidencePerTask = 20
    rag_enabled: bool = False
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "hello_agents_vectors"
    qdrant_vector_size: int | None = Field(default=None, ge=1)
    qdrant_distance: QdrantDistance = "cosine"
    qdrant_timeout: float = Field(default=30, gt=0)
    embed_model_type: EmbeddingModelType = "dashscope"
    embed_model_name: str = ""
    embed_api_key: str | None = None
    embed_base_url: str | None = None
    rag_chunk_tokenizer_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rag_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rag_chunk_max_tokens: RagChunkTokens = 800
    rag_candidate_limit: RagCandidateLimit = 30
    rag_top_k: RagTopK = 3
    rag_context_max_chars: RagContextChars = 20_000
    rag_max_upload_bytes: RagUploadBytes = 52_428_800

    @model_validator(mode="after")
    def validate_rag_limits(self) -> "Settings":
        if self.rag_top_k > self.rag_candidate_limit:
            raise ValueError("rag_top_k cannot exceed rag_candidate_limit")
        return self

    @property
    def embedding_model_name(self) -> str:
        if self.embed_model_name.strip():
            return self.embed_model_name.strip()
        if self.embed_model_type == "dashscope":
            return "text-embedding-v3"
        return "sentence-transformers/all-MiniLM-L6-v2"

    @property
    def budgets(self) -> ResearchBudgets:
        return ResearchBudgets.model_validate(
            self.model_dump(include=set(ResearchBudgets.model_fields))
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()