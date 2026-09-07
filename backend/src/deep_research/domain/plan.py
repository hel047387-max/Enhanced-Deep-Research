from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class TaskStatus(StrEnum):
    """研究任务状态枚举。"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    INSUFFICIENT = "insufficient"
    FAILED = "failed"


class CoverageLevel(StrEnum):
    """任务证据覆盖程度枚举。"""
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class ResearchBrief(BaseModel, frozen=True):
    """研究简报：定义问题范围、输出要求和来源偏好。"""
    main_question: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    time_range: str | None = None
    comparison_dimensions: list[str] = Field(default_factory=list)
    expected_output: str = "Structured Markdown research report"
    source_preferences: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)


class ResearchTask(BaseModel):
    """可执行研究任务及其搜索与完成状态。"""
    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    completion_criteria: list[str] = Field(min_length=1)
    search_queries: list[str] = Field(min_length=1, max_length=2)
    status: TaskStatus = TaskStatus.PENDING
    current_round: int = Field(default=0, ge=0, le=2)
    parent_task_id: str | None = None
    gap_reason: str | None = None
    error: str | None = None


class ResearchPlan(BaseModel, frozen=True):
    """研究计划：包含策略摘要和一组唯一任务。"""
    strategy_summary: str = Field(min_length=1)
    tasks: list[ResearchTask] = Field(min_length=3, max_length=5)

    @model_validator(mode="after")
    def unique_task_ids(self) -> "ResearchPlan":
        ids = [task.task_id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task_id values must be unique")
        return self


class GapAssessment(BaseModel, frozen=True):
    """单个任务的证据缺口评估结果。"""
    task_id: str
    coverage: CoverageLevel
    covered_questions: list[str] = Field(default_factory=list)
    missing_questions: list[str] = Field(default_factory=list)
    evidence_issues: list[str] = Field(default_factory=list)
    next_queries: list[str] = Field(default_factory=list, max_length=2)
    should_continue: bool
    reason: str


class CoverageDecision(BaseModel, frozen=True):
    """全局覆盖度判断及可选补充任务。"""
    sufficient: bool
    covered_dimensions: list[str] = Field(default_factory=list)
    global_gaps: list[str] = Field(default_factory=list)
    additional_tasks: list[ResearchTask] = Field(default_factory=list, max_length=2)
