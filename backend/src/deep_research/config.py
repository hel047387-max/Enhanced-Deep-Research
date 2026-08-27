from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field
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

    @property
    def budgets(self) -> ResearchBudgets:
        return ResearchBudgets.model_validate(
            self.model_dump(include=set(ResearchBudgets.model_fields))
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
