# Foundation and Evidence Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the validated backend foundation: configuration, research domain models, normalized evidence, deterministic citations, and concurrency-safe LangGraph state reducers.

**Architecture:** Pydantic models define stable domain contracts while LangGraph state and custom reducers remain isolated in `state/`. Evidence is normalized as `Source` plus `EvidenceItem`; citations are rendered deterministically from structured report paragraphs rather than generated as free-form Markdown.

**Tech Stack:** Python 3.11+, Pydantic 2, pydantic-settings, LangGraph, pytest, pytest-cov, pytest-asyncio, Ruff

**Spec:** `docs/superpowers/specs/2026-08-26-deep-research-agent-design.md`

## Global Constraints

- Initial tasks: 3-5; hard maximum 5.
- Supervisor-added tasks: maximum 2.
- Reviewer-added tasks: maximum 1.
- Research rounds per task: maximum 2.
- Queries per round: maximum 2.
- Concurrent Researchers: maximum 3.
- Total search queries: maximum 20.
- Sources per task: maximum 8.
- EvidenceItems per task: maximum 20.
- Raw webpage bodies must never enter Graph State or SQLite checkpoints.
- Only HTTP/HTTPS source URLs are valid; local, loopback, private-network, and file URLs are rejected.
- No task in this plan implements Agent nodes, FastAPI endpoints, SSE, frontend behavior, or live provider calls.

---

## File map

- `backend/pyproject.toml`: backend package metadata, runtime dependencies, and test/lint configuration.
- `.env.example`: names and safe defaults for supported environment variables; no secrets.
- `.gitignore`: Python, Node, SQLite, environment, coverage, and editor artifacts.
- `backend/src/deep_research/config.py`: validated settings and immutable research budgets.
- `backend/src/deep_research/domain/plan.py`: brief, task, plan, gap, and coverage contracts.
- `backend/src/deep_research/domain/evidence.py`: Source and EvidenceItem contracts and enums.
- `backend/src/deep_research/domain/review.py`: report draft and review contracts.
- `backend/src/deep_research/domain/events.py`: typed progress-event envelope shared with later API/frontend plans.
- `backend/src/deep_research/domain/errors.py`: structured sanitized workflow error contract.
- `backend/src/deep_research/services/evidence_store.py`: canonical URL, stable identifiers, and merge helpers.
- `backend/src/deep_research/services/citations.py`: deterministic validation and Markdown rendering.
- `backend/src/deep_research/state/models.py`: ResearchState TypedDict.
- `backend/src/deep_research/state/reducers.py`: deterministic parallel-state merge functions.
- `backend/tests/unit/`: isolated tests for every contract and deterministic service.

### Task 1: Package configuration and immutable budgets

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `.env.example`
- Modify: `.gitignore`
- Create: `backend/src/deep_research/config.py`
- Create: `backend/tests/unit/test_config.py`

**Interfaces:**
- Consumes: environment variables listed in `.env.example`.
- Produces: `Settings`, `ResearchBudgets`, and `get_settings() -> Settings`.

- [ ] **Step 1: Write the failing budget-validation tests**

```python
from pydantic import ValidationError
import pytest

from deep_research.config import ResearchBudgets, Settings


def test_default_budgets_match_the_approved_spec() -> None:
    budgets = ResearchBudgets()
    assert budgets.max_initial_tasks == 5
    assert budgets.max_supervisor_tasks == 2
    assert budgets.max_reviewer_tasks == 1
    assert budgets.max_research_rounds == 2
    assert budgets.max_queries_per_round == 2
    assert budgets.max_concurrent_researchers == 3
    assert budgets.max_total_search_queries == 20
    assert budgets.max_sources_per_task == 8
    assert budgets.max_evidence_per_task == 20


def test_client_cannot_construct_an_unbounded_budget() -> None:
    with pytest.raises(ValidationError):
        ResearchBudgets(max_total_search_queries=21)


def test_settings_require_provider_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm_api_key is None
    assert settings.tavily_api_key is None
```

- [ ] **Step 2: Run the tests and verify the import failure**

Run: `cd backend && pytest tests/unit/test_config.py -v`

Expected: FAIL because `deep_research.config` does not exist.

- [ ] **Step 3: Populate package metadata and minimal settings implementation**

Use Python `>=3.11` and add exact dependencies: `pydantic>=2.8`, `pydantic-settings>=2.4`, `langgraph>=0.2`, `langchain-core>=0.3`, `pytest>=8.3`, `pytest-asyncio>=0.24`, `pytest-cov>=5.0`, and `ruff>=0.6`. Configure pytest with `pythonpath = ["src"]` and asyncio mode `auto`.

```python
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
```

- [ ] **Step 4: Run configuration tests and lint**

Run: `cd backend && pytest tests/unit/test_config.py -v && ruff check src/deep_research/config.py tests/unit/test_config.py`

Expected: all tests PASS and Ruff reports no errors.

- [ ] **Step 5: Commit the foundation configuration**

```bash
git add .env.example .gitignore backend/pyproject.toml backend/src/deep_research/config.py backend/tests/unit/test_config.py
git commit -m "chore: configure backend and research budgets"
```

### Task 2: Research brief, task, and coverage contracts

**Files:**
- Modify: `backend/src/deep_research/domain/plan.py`
- Modify: `backend/src/deep_research/domain/__init__.py`
- Create: `backend/tests/unit/test_plan_models.py`

**Interfaces:**
- Consumes: `ResearchBudgets` from Task 1 for orchestration validation in later plans.
- Produces: `ResearchBrief`, `ResearchTask`, `ResearchPlan`, `GapAssessment`, `CoverageDecision`, `TaskStatus`, and `CoverageLevel`.

- [ ] **Step 1: Write failing domain-model tests**

```python
from pydantic import ValidationError
import pytest

from deep_research.domain.plan import ResearchBrief, ResearchPlan, ResearchTask, TaskStatus


def make_task(index: int) -> ResearchTask:
    return ResearchTask(
        task_id=f"task-{index}",
        title=f"Task {index}",
        objective=f"Answer sub-question {index}",
        completion_criteria=["At least two independent evidence items"],
        search_queries=[f"query {index}"],
    )


def test_plan_accepts_three_to_five_tasks() -> None:
    assert len(ResearchPlan(strategy_summary="Coverage", tasks=[make_task(i) for i in range(3)]).tasks) == 3
    assert len(ResearchPlan(strategy_summary="Coverage", tasks=[make_task(i) for i in range(5)]).tasks) == 5


def test_plan_rejects_duplicate_task_ids() -> None:
    with pytest.raises(ValidationError):
        ResearchPlan(strategy_summary="Bad", tasks=[make_task(1), make_task(1), make_task(2)])


def test_task_defaults_to_pending_round_zero() -> None:
    task = make_task(1)
    assert task.status is TaskStatus.PENDING
    assert task.current_round == 0
```

- [ ] **Step 2: Run tests to verify missing models**

Run: `cd backend && pytest tests/unit/test_plan_models.py -v`

Expected: FAIL because the named contracts are not implemented.

- [ ] **Step 3: Implement the validated contracts**

```python
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    INSUFFICIENT = "insufficient"
    FAILED = "failed"


class CoverageLevel(StrEnum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class ResearchBrief(BaseModel, frozen=True):
    main_question: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    time_range: str | None = None
    comparison_dimensions: list[str] = Field(default_factory=list)
    expected_output: str = "Structured Markdown research report"
    source_preferences: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)


class ResearchTask(BaseModel):
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
    strategy_summary: str = Field(min_length=1)
    tasks: list[ResearchTask] = Field(min_length=3, max_length=5)

    @model_validator(mode="after")
    def unique_task_ids(self) -> "ResearchPlan":
        ids = [task.task_id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task_id values must be unique")
        return self


class GapAssessment(BaseModel, frozen=True):
    task_id: str
    coverage: CoverageLevel
    covered_questions: list[str] = Field(default_factory=list)
    missing_questions: list[str] = Field(default_factory=list)
    evidence_issues: list[str] = Field(default_factory=list)
    next_queries: list[str] = Field(default_factory=list, max_length=2)
    should_continue: bool
    reason: str


class CoverageDecision(BaseModel, frozen=True):
    sufficient: bool
    covered_dimensions: list[str] = Field(default_factory=list)
    global_gaps: list[str] = Field(default_factory=list)
    additional_tasks: list[ResearchTask] = Field(default_factory=list, max_length=2)
```

- [ ] **Step 4: Run model tests**

Run: `cd backend && pytest tests/unit/test_plan_models.py -v`

Expected: PASS.

- [ ] **Step 5: Commit domain planning contracts**

```bash
git add backend/src/deep_research/domain/plan.py backend/src/deep_research/domain/__init__.py backend/tests/unit/test_plan_models.py
git commit -m "feat: define research planning contracts"
```

### Task 3: Source and EvidenceItem normalization

**Files:**
- Modify: `backend/src/deep_research/domain/evidence.py`
- Modify: `backend/src/deep_research/services/evidence_store.py`
- Create: `backend/tests/unit/test_evidence_store.py`

**Interfaces:**
- Consumes: raw URL, title, source metadata, and task-scoped extracted claim data.
- Produces: `canonicalize_url(url: str) -> str`, `build_source(url: str, title: str, body: str, retrieved_at: datetime, source_type: SourceType, published_at: datetime | None = None) -> Source`, `build_evidence(task_id: str, source_id: str, claim: str, excerpt: str, context: str, relevance: Relevance, discovered_in_round: int) -> EvidenceItem`, and `merge_evidence_batches(*batches: Mapping[str, EvidenceItem]) -> dict[str, EvidenceItem]`.

- [ ] **Step 1: Write failing normalization and deduplication tests**

```python
from datetime import UTC, datetime

from deep_research.domain.evidence import Relevance, SourceType
from deep_research.services.evidence_store import build_evidence, build_source, canonicalize_url


def test_canonicalize_url_removes_fragment_and_tracking_parameters() -> None:
    url = "https://Example.com/path/?utm_source=test&b=2&a=1#section"
    assert canonicalize_url(url) == "https://example.com/path?a=1&b=2"


def test_same_canonical_url_produces_same_source_id() -> None:
    retrieved_at = datetime(2026, 8, 26, tzinfo=UTC)
    first = build_source("https://example.com/a?utm_campaign=x", "A", "body", retrieved_at, SourceType.WEB)
    second = build_source("https://EXAMPLE.com/a#top", "A2", "body", retrieved_at, SourceType.WEB)
    assert first.source_id == second.source_id


def test_evidence_id_is_stable_for_same_task_source_claim() -> None:
    first = build_evidence("task-1", "source-1", "A claim", "Exact excerpt", "Context", Relevance.HIGH, 1)
    second = build_evidence("task-1", "source-1", "A claim", "Exact excerpt", "Context", Relevance.HIGH, 1)
    assert first.evidence_id == second.evidence_id
```

- [ ] **Step 2: Run tests to establish the failure**

Run: `cd backend && pytest tests/unit/test_evidence_store.py -v`

Expected: FAIL because evidence services are empty.

- [ ] **Step 3: Implement stable models and identifiers**

```python
from datetime import datetime
from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, Field


class SourceType(StrEnum):
    WEB = "web"
    OFFICIAL = "official"
    NEWS = "news"


class Relevance(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Source(BaseModel, frozen=True):
    source_id: str
    url: AnyHttpUrl
    canonical_url: AnyHttpUrl
    title: str
    domain: str
    published_at: datetime | None = None
    retrieved_at: datetime
    content_hash: str
    source_type: SourceType


class EvidenceItem(BaseModel, frozen=True):
    evidence_id: str
    task_id: str
    source_id: str
    claim: str = Field(min_length=1)
    excerpt: str = Field(min_length=1, max_length=1000)
    context: str = Field(min_length=1)
    relevance: Relevance
    discovered_in_round: int = Field(ge=1, le=2)
    citation_label: str
```

Implement canonicalization with `urllib.parse`: lowercase scheme/host, remove fragments, remove `utm_*`, `gclid`, and `fbclid`, sort remaining query pairs, and remove a root trailing slash. Use SHA-256 of canonical URL for `source_id`, SHA-256 of raw body for `content_hash`, and SHA-256 of `task_id|source_id|normalized_claim` for `evidence_id`. Prefix IDs with `src-` and `ev-` using the first 16 hex characters.

- [ ] **Step 4: Run evidence tests and the full unit suite**

Run: `cd backend && pytest tests/unit/test_evidence_store.py -v && pytest tests/unit -q`

Expected: PASS.

- [ ] **Step 5: Commit evidence normalization**

```bash
git add backend/src/deep_research/domain/evidence.py backend/src/deep_research/services/evidence_store.py backend/tests/unit/test_evidence_store.py
git commit -m "feat: normalize sources and evidence"
```

### Task 4: Structured report, review contracts, and deterministic citations

**Files:**
- Modify: `backend/src/deep_research/domain/review.py`
- Create: `backend/src/deep_research/services/citations.py`
- Create: `backend/tests/unit/test_citations.py`

**Interfaces:**
- Consumes: `ReportDraft`, `dict[str, EvidenceItem]`, and `dict[str, Source]`.
- Produces: `validate_draft(draft: ReportDraft, evidence: Mapping[str, EvidenceItem], sources: Mapping[str, Source]) -> list[CitationIssue]` and `render_report(draft: ReportDraft, evidence: Mapping[str, EvidenceItem], sources: Mapping[str, Source]) -> str`.

- [ ] **Step 1: Write failing citation tests**

```python
from datetime import UTC, datetime

import pytest

from deep_research.domain.evidence import EvidenceItem, Relevance, Source, SourceType
from deep_research.domain.review import ReportDraft, ReportParagraph, ReportSection
from deep_research.services.citations import CitationValidationError, render_report


@pytest.fixture
def source_map() -> dict[str, Source]:
    return {"src-1": Source(
        source_id="src-1",
        url="https://example.com/source",
        canonical_url="https://example.com/source",
        title="Example Source",
        domain="example.com",
        retrieved_at=datetime(2026, 8, 26, tzinfo=UTC),
        content_hash="hash",
        source_type=SourceType.WEB,
    )}


@pytest.fixture
def evidence_map() -> dict[str, EvidenceItem]:
    return {
        evidence_id: EvidenceItem(
            evidence_id=evidence_id,
            task_id="task-1",
            source_id="src-1",
            claim=claim,
            excerpt=claim,
            context="Research context",
            relevance=Relevance.HIGH,
            discovered_in_round=1,
            citation_label=evidence_id.upper(),
        )
        for evidence_id, claim in (("ev-1", "First fact"), ("ev-2", "Second fact"))
    }


def test_renderer_reuses_one_number_for_evidence_from_same_source(source_map, evidence_map) -> None:
    draft = ReportDraft(
        title="Report",
        executive_summary=[],
        sections=[ReportSection(section_id="findings", heading="Findings", paragraphs=[
            ReportParagraph(paragraph_id="p-1", text="First fact.", evidence_ids=["ev-1"]),
            ReportParagraph(paragraph_id="p-2", text="Second fact.", evidence_ids=["ev-2"]),
        ])],
        limitations=[],
        suggested_actions=[],
    )
    markdown = render_report(draft, evidence_map, source_map)
    assert markdown.count("[1]") >= 2
    assert markdown.count("https://example.com/source") == 1


def test_renderer_rejects_unknown_evidence_id(source_map, evidence_map) -> None:
    draft = ReportDraft(title="Report", executive_summary=[], sections=[
        ReportSection(section_id="findings", heading="Findings", paragraphs=[ReportParagraph(paragraph_id="p-1", text="Fact.", evidence_ids=["ev-missing"])])
    ], limitations=[], suggested_actions=[])
    with pytest.raises(CitationValidationError):
        render_report(draft, evidence_map, source_map)
```

- [ ] **Step 2: Run tests and confirm missing report contracts**

Run: `cd backend && pytest tests/unit/test_citations.py -v`

Expected: FAIL because report and citation contracts are absent.

- [ ] **Step 3: Implement report/review contracts and renderer**

```python
from enum import StrEnum

from pydantic import BaseModel, Field

from deep_research.domain.plan import ResearchTask


class ReviewVerdict(StrEnum):
    PASS = "pass"
    REVISE = "revise"
    RESEARCH_GAP = "research_gap"


class ReportParagraph(BaseModel, frozen=True):
    paragraph_id: str
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ReportSection(BaseModel, frozen=True):
    section_id: str
    heading: str
    paragraphs: list[ReportParagraph]


class ReportDraft(BaseModel, frozen=True):
    title: str
    executive_summary: list[ReportParagraph]
    sections: list[ReportSection]
    limitations: list[str]
    suggested_actions: list[str]


class ReviewIssue(BaseModel, frozen=True):
    section_id: str | None = None
    paragraph_id: str | None = None
    evidence_id: str | None = None
    message: str


class ReviewResult(BaseModel, frozen=True):
    verdict: ReviewVerdict
    blocking_issues: list[ReviewIssue] = Field(default_factory=list)
    unsupported_claims: list[ReviewIssue] = Field(default_factory=list)
    conflicting_evidence: list[ReviewIssue] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    follow_up_tasks: list[ResearchTask] = Field(default_factory=list, max_length=1)
```

The renderer must validate every Evidence ID, resolve its Source, allocate source numbers in first-use order, append `[n]` markers to paragraphs, and render each used Source exactly once under `## References` as `[n] Title — URL`.

- [ ] **Step 4: Run citation and model tests**

Run: `cd backend && pytest tests/unit/test_citations.py tests/unit/test_plan_models.py -v`

Expected: PASS.

- [ ] **Step 5: Commit deterministic reporting contracts**

```bash
git add backend/src/deep_research/domain/review.py backend/src/deep_research/services/citations.py backend/tests/unit/test_citations.py
git commit -m "feat: add deterministic citation rendering"
```

### Task 5: ResearchState and concurrency-safe reducers

**Files:**
- Modify: `backend/src/deep_research/state/models.py`
- Modify: `backend/src/deep_research/state/reducers.py`
- Modify: `backend/src/deep_research/state/__init__.py`
- Modify: `backend/src/deep_research/domain/events.py`
- Create: `backend/src/deep_research/domain/errors.py`
- Create: `backend/tests/unit/test_reducers.py`

**Interfaces:**
- Consumes: domain objects from Tasks 2-4.
- Produces: `ResearchState`, `ResearchError`, `merge_tasks`, `merge_sources`, `merge_evidence`, `merge_gap_assessments`, `append_errors`, `ResearchEvent`, and `EventType`.

- [ ] **Step 1: Write failing parallel-merge tests**

```python
from deep_research.domain.plan import ResearchTask, TaskStatus
from deep_research.state.reducers import merge_tasks


def task(task_id: str, status: TaskStatus) -> ResearchTask:
    return ResearchTask(
        task_id=task_id,
        title=task_id,
        objective="objective",
        completion_criteria=["criterion"],
        search_queries=["query"],
        status=status,
    )


def test_merge_tasks_updates_matching_ids_without_losing_parallel_results() -> None:
    existing = {"task-1": task("task-1", TaskStatus.RUNNING)}
    incoming = {
        "task-1": task("task-1", TaskStatus.COMPLETED),
        "task-2": task("task-2", TaskStatus.COMPLETED),
    }
    merged = merge_tasks(existing, incoming)
    assert merged["task-1"].status is TaskStatus.COMPLETED
    assert merged["task-2"].status is TaskStatus.COMPLETED
    assert existing["task-1"].status is TaskStatus.RUNNING
```

- [ ] **Step 2: Run tests and verify reducers are absent**

Run: `cd backend && pytest tests/unit/test_reducers.py -v`

Expected: FAIL because reducer functions are not implemented.

- [ ] **Step 3: Implement immutable dictionary merges and ResearchState annotations**

```python
from collections.abc import Mapping
from typing import TypeVar

K = TypeVar("K")
V = TypeVar("V")


def merge_mapping(left: Mapping[K, V] | None, right: Mapping[K, V] | None) -> dict[K, V]:
    return {**(left or {}), **(right or {})}


merge_tasks = merge_mapping
merge_sources = merge_mapping
merge_evidence = merge_mapping
merge_gap_assessments = merge_mapping


def append_errors(left: list[ResearchError] | None, right: list[ResearchError] | None) -> list[ResearchError]:
    return [*(left or []), *(right or [])]
```

Define `ResearchState` with `Annotated` reducers for `messages`, `tasks`, `sources`, `evidence`, `gap_assessments`, and `errors`. Scalar fields include IDs, counters, brief, draft, review, final report, and status. Define the event envelope with `type`, `run_id`, `thread_id`, monotonically increasing `sequence`, UTC `timestamp`, and JSON-compatible `payload`.

Define the error contract before importing it into reducers:

```python
from pydantic import BaseModel, Field


class ResearchError(BaseModel, frozen=True):
    error_code: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    message: str = Field(min_length=1)
    task_id: str | None = None
    retryable: bool = False
    attempt: int = Field(default=1, ge=1)
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
```

- [ ] **Step 4: Run every foundation test**

Run: `cd backend && pytest tests/unit -v --cov=deep_research --cov-report=term-missing && ruff check src tests`

Expected: PASS; coverage report is produced; Ruff reports no errors.

- [ ] **Step 5: Commit state and event contracts**

```bash
git add backend/src/deep_research/state backend/src/deep_research/domain/events.py backend/src/deep_research/domain/errors.py backend/tests/unit/test_reducers.py
git commit -m "feat: add research state reducers and events"
```

## Plan completion gate

Run:

```bash
cd backend
pytest tests/unit -q
ruff check src tests
python -c "from deep_research.state.models import ResearchState; print(ResearchState.__name__)"
```

Expected: all unit tests pass, Ruff is clean, and the import prints `ResearchState`. Do not begin the Agent workflow plan until this gate passes.
