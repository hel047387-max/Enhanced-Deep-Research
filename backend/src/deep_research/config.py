from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ResearchBudgets(BaseModel, frozen=True):
    max_initial_tasks: int = Field(default=5, ge=3, le=5)
    max_supervisor_tasks: int = Field(default=2, ge=0, le=2)
    max_reviewer_tasks: int = Field(default=1, ge=0, le=1)
    max_research_rounds: int = Field(default=2, ge=1, le=2)
    max_queries_per_round: int = Field(default=2, ge=1, le=2)
    max_concurrent_researchers: int = Field(default=3, ge=1, le=3)
    max_total_search_queries: int = Field(default=20, ge=1, le=20)
    max_sources_per_task: int = Field(default=8, ge=1, le=8)
    max_evidence_per_task: int = Field(default=20, ge=1, le=20)


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
    max_initial_tasks: int = 5
    max_supervisor_tasks: int = 2
    max_reviewer_tasks: int = 1
    max_research_rounds: int = 2
    max_queries_per_round: int = 2
    max_concurrent_researchers: int = 3
    max_total_search_queries: int = 20
    max_sources_per_task: int = 8
    max_evidence_per_task: int = 20

    @property
    def budgets(self) -> ResearchBudgets:
        return ResearchBudgets.model_validate(
            self.model_dump(include=set(ResearchBudgets.model_fields))
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
