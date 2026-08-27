from pydantic import BaseModel, Field


class ResearchError(BaseModel, frozen=True):
    """A sanitized, structured error safe to retain in graph state."""

    error_code: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    message: str = Field(min_length=1)
    task_id: str | None = None
    retryable: bool = False
    attempt: int = Field(default=1, ge=1)
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
