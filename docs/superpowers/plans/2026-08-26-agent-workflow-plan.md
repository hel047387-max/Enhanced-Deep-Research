# Agent Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded LangGraph workflow from clarification through evidence-grounded writing and one Reviewer repair action.

**Architecture:** A top-level LangGraph owns conversational state and bounded orchestration. Researcher work is isolated behind a task runner that uses SearchProvider, evidence extraction, and explicit gap analysis; all routing limits are enforced in code rather than prompts.

**Tech Stack:** Python 3.11+, LangGraph, LangChain Core, langchain-openai, Tavily Python SDK, Pydantic 2, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-08-26-deep-research-agent-design.md`

## Global Constraints

- Complete `2026-08-26-foundation-evidence-model-plan.md` first.
- Clarifier may interrupt at most once.
- Planner runs once and returns 3-5 initial tasks.
- Researcher receives only ResearchBrief, its ResearchTask, and ResearchBudgets.
- Researcher performs at most 2 rounds and 2 queries per round.
- Supervisor performs one coverage assessment and adds at most 2 tasks.
- Reviewer performs one assessment and triggers at most 1 revision or targeted task.
- Global search queries never exceed 20 and concurrency never exceeds 3.
- Writer never receives raw pages or invents Evidence IDs.
- Agent events expose decisions/results, never private chain-of-thought.

---

## File map

- `backend/src/deep_research/llm.py`: model construction and structured-output protocol.
- `backend/src/deep_research/tools/search.py`: SearchProvider protocol, Tavily adapter, and normalized search result DTO.
- `backend/src/deep_research/prompts/*.py`: one prompt contract per Agent responsibility.
- `backend/src/deep_research/nodes/*.py`: node functions with narrow state inputs and patches.
- `backend/src/deep_research/graph/routing.py`: pure routing and budget predicates.
- `backend/src/deep_research/graph/builder.py`: Researcher and top-level graph assembly.
- `backend/tests/fakes.py`: deterministic fake LLM/search implementations.
- `backend/tests/conftest.py`: explicit brief, plan, model, and graph harness fixtures used by tests.
- `backend/tests/unit/test_routing.py`: budget and route tests.
- `backend/tests/integration/test_research_graph.py`: full fake-backed graph scenarios.

### Task 1: SearchProvider boundary and deterministic fake

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/deep_research/tools/search.py`
- Create: `backend/tests/fakes.py`
- Create: `backend/tests/unit/test_search_provider.py`

**Interfaces:**
- Consumes: `query: str`, `max_results: int`, and a cancellation-neutral request context.
- Produces: `SearchProvider.search(query: str, max_results: int) -> list[SearchHit]` and `TavilySearchProvider`.

- [ ] **Step 1: Write the failing provider-contract tests**

```python
import pytest

from deep_research.tools.search import SearchHit
from tests.fakes import FakeSearchProvider


@pytest.mark.asyncio
async def test_fake_search_records_queries_and_returns_scripted_hits() -> None:
    hit = SearchHit(title="Official docs", url="https://example.com/docs", content="Evidence text", raw_content=None)
    provider = FakeSearchProvider({"query": [hit]})
    assert await provider.search("query", max_results=5) == [hit]
    assert provider.queries == ["query"]


@pytest.mark.asyncio
async def test_fake_search_returns_empty_list_for_unknown_query() -> None:
    provider = FakeSearchProvider({})
    assert await provider.search("missing", max_results=5) == []
```

- [ ] **Step 2: Run the contract tests**

Run: `cd backend && pytest tests/unit/test_search_provider.py -v`

Expected: FAIL because SearchHit and FakeSearchProvider are absent.

- [ ] **Step 3: Implement the protocol and adapter**

```python
from typing import Protocol

from pydantic import AnyHttpUrl, BaseModel


class SearchHit(BaseModel, frozen=True):
    title: str
    url: AnyHttpUrl
    content: str
    raw_content: str | None = None


class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        raise NotImplementedError
```

Implement `TavilySearchProvider` with an injected `AsyncTavilyClient`. Call Tavily with `include_raw_content=True` and normalize only title, URL, content, and raw content. Do not place the SDK response in state. Add `tavily-python` and `langchain-openai` dependencies.

- [ ] **Step 4: Run provider tests**

Run: `cd backend && pytest tests/unit/test_search_provider.py -v && ruff check src/deep_research/tools/search.py tests/fakes.py`

Expected: PASS.

- [ ] **Step 5: Commit the provider boundary**

```bash
git add backend/pyproject.toml backend/src/deep_research/tools/search.py backend/tests/fakes.py backend/tests/unit/test_search_provider.py
git commit -m "feat: add search provider boundary"
```

### Task 2: Pure routing and budget enforcement

**Files:**
- Modify: `backend/src/deep_research/graph/routing.py`
- Create: `backend/tests/unit/test_routing.py`

**Interfaces:**
- Consumes: task counters, GapAssessment, ReviewResult, and ResearchBudgets.
- Produces: `may_research_again`, `may_add_supervisor_tasks`, `route_review`, and `take_dispatch_batch`.

- [ ] **Step 1: Write failing hard-limit tests**

```python
from deep_research.config import ResearchBudgets
from deep_research.domain.plan import CoverageLevel, GapAssessment
from deep_research.graph.routing import may_research_again, take_dispatch_batch


def test_research_again_requires_gap_queries_and_both_budgets() -> None:
    gap = GapAssessment(task_id="task-1", coverage=CoverageLevel.PARTIAL, next_queries=["next"], should_continue=True, reason="missing")
    budgets = ResearchBudgets()
    assert may_research_again(gap, current_round=1, total_queries=19, budgets=budgets)
    assert not may_research_again(gap, current_round=2, total_queries=19, budgets=budgets)
    assert not may_research_again(gap, current_round=1, total_queries=20, budgets=budgets)


def test_dispatch_batch_never_exceeds_three() -> None:
    assert take_dispatch_batch(["a", "b", "c", "d"], limit=3) == ["a", "b", "c"]
```

- [ ] **Step 2: Run tests to confirm missing predicates**

Run: `cd backend && pytest tests/unit/test_routing.py -v`

Expected: FAIL because routing predicates do not exist.

- [ ] **Step 3: Implement pure predicates without LLM calls**

```python
def may_research_again(gap: GapAssessment, current_round: int, total_queries: int, budgets: ResearchBudgets) -> bool:
    return (
        gap.should_continue
        and bool(gap.next_queries)
        and current_round < budgets.max_research_rounds
        and total_queries < budgets.max_total_search_queries
    )


def take_dispatch_batch(task_ids: list[str], limit: int) -> list[str]:
    return task_ids[: min(limit, 3)]


def may_add_supervisor_tasks(supervisor_added_tasks: int, coverage_checked: bool, budgets: ResearchBudgets) -> bool:
    return not coverage_checked and supervisor_added_tasks < budgets.max_supervisor_tasks


def route_review(verdict: ReviewVerdict, review_action_count: int) -> str:
    if review_action_count >= 1 or verdict is ReviewVerdict.PASS:
        return "finalize"
    return "revise" if verdict is ReviewVerdict.REVISE else "review_research"
```

- [ ] **Step 4: Run all routing tests**

Run: `cd backend && pytest tests/unit/test_routing.py -v`

Expected: PASS.

- [ ] **Step 5: Commit hard routing limits**

```bash
git add backend/src/deep_research/graph/routing.py backend/tests/unit/test_routing.py
git commit -m "feat: enforce bounded agent routing"
```

### Task 3: Clarifier, Research Brief, and Planner nodes

**Files:**
- Create: `backend/src/deep_research/llm.py`
- Modify: `backend/src/deep_research/prompts/scope.py`
- Modify: `backend/src/deep_research/prompts/planning.py`
- Modify: `backend/src/deep_research/nodes/clarify.py`
- Modify: `backend/src/deep_research/nodes/planner.py`
- Create: `backend/tests/unit/test_scope_and_planner_nodes.py`
- Create: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: state messages, clarification count, Settings-backed chat model.
- Produces: `ClarificationDecision`, `ResearchBrief`, `ResearchPlan`, and state patches.

- [ ] **Step 1: Write failing node tests with scripted structured outputs**

```python
import pytest

from deep_research.nodes.clarify import clarify_request
from deep_research.nodes.planner import plan_research
from tests.fakes import ScriptedStructuredModel


@pytest.mark.asyncio
async def test_clarifier_requests_only_one_answer() -> None:
    model = ScriptedStructuredModel([{"needs_clarification": True, "question": "Which time range?", "reason": "Missing range"}])
    result = await clarify_request({"messages": ["Research market growth"], "clarification_count": 0}, model)
    assert result["interrupt_question"] == "Which time range?"


@pytest.mark.asyncio
async def test_planner_returns_three_to_five_unique_tasks(brief, three_task_plan, model_factory) -> None:
    result = await plan_research({"research_brief": brief}, model_factory(three_task_plan))
    assert len(result["tasks"]) == 3
    assert len(set(result["tasks"])) == 3
```

- [ ] **Step 2: Run tests to establish missing node behavior**

Run: `cd backend && pytest tests/unit/test_scope_and_planner_nodes.py -v`

Expected: FAIL because nodes and fake structured model are incomplete.

- [ ] **Step 3: Implement injected structured-model calls**

Define a `StructuredModel` protocol with `ainvoke(input: list[BaseMessage]) -> BaseModel`. Define `ClarificationDecision(BaseModel)` with `needs_clarification: bool`, `question: str | None`, and `reason: str`; validate that a required clarification has a non-empty question. Model creation belongs in `llm.py`; node tests inject fakes directly. `clarify_request` returns an interrupt question only when `clarification_count == 0`; otherwise it records an assumption and proceeds to `write_research_brief`. Planner validates ResearchPlan and returns `{task_id: task}`.

Prompts must state exact schemas, current date, source preferences, no invented user constraints, no overlapping tasks, and no report-writing tasks. Prompts must not request hidden reasoning.

Add fixtures with these exact return contracts to `tests/conftest.py`: `brief() -> ResearchBrief`, `three_task_plan() -> ResearchPlan`, and `model_factory() -> Callable[[BaseModel | dict[str, object]], ScriptedStructuredModel]`. `ScriptedStructuredModel` stores a FIFO list of Pydantic results or dictionaries, appends every input to `calls`, and raises `AssertionError("No scripted structured output remains")` if invoked more times than scripted.

- [ ] **Step 4: Run node tests and lint prompts**

Run: `cd backend && pytest tests/unit/test_scope_and_planner_nodes.py -v && ruff check src/deep_research/nodes src/deep_research/prompts src/deep_research/llm.py`

Expected: PASS.

- [ ] **Step 5: Commit scope and planning nodes**

```bash
git add backend/src/deep_research/llm.py backend/src/deep_research/prompts/scope.py backend/src/deep_research/prompts/planning.py backend/src/deep_research/nodes/clarify.py backend/src/deep_research/nodes/planner.py backend/tests/unit/test_scope_and_planner_nodes.py backend/tests/fakes.py
git commit -m "feat: add clarification and planning nodes"
```

### Task 4: Researcher search, evidence extraction, and gap loop

**Files:**
- Modify: `backend/src/deep_research/prompts/research.py`
- Modify: `backend/src/deep_research/nodes/researcher.py`
- Modify: `backend/src/deep_research/nodes/gap_analyzer.py`
- Modify: `backend/src/deep_research/graph/builder.py`
- Create: `backend/tests/integration/test_researcher_graph.py`

**Interfaces:**
- Consumes: `ResearcherInput(brief, task, budgets)`, SearchProvider, evidence extractor model, and gap model.
- Produces: `ResearcherOutput(updated_task, sources, evidence, gap_assessment, errors, queries_used)`.

- [ ] **Step 1: Write failing two-round and stop-condition tests**

```python
@pytest.mark.asyncio
async def test_researcher_runs_second_round_only_for_actionable_gap(researcher_factory, partial_gap, sufficient_gap) -> None:
    researcher = researcher_factory(gaps=[partial_gap, sufficient_gap])
    output = await researcher.ainvoke({"task": researcher.task, "research_brief": researcher.brief})
    assert output["updated_task"].current_round == 2
    assert researcher.search.queries == ["initial query", "targeted query"]


@pytest.mark.asyncio
async def test_researcher_stops_at_global_query_cap(researcher_factory, partial_gap) -> None:
    researcher = researcher_factory(gaps=[partial_gap], total_queries=20)
    output = await researcher.ainvoke({"task": researcher.task, "research_brief": researcher.brief})
    assert output["updated_task"].status.value == "insufficient"
    assert researcher.search.queries == []
```

- [ ] **Step 2: Run tests to verify the Researcher graph is absent**

Run: `cd backend && pytest tests/integration/test_researcher_graph.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement the Researcher subgraph**

Define `ResearcherInput(TypedDict)` with `task`, `research_brief`, and `total_queries`; `ResearcherState` extends it with private `queries`, `raw_results`, `sources`, `evidence`, `gap_assessment`, and `current_round`; `ResearcherOutput(TypedDict)` contains only `updated_task`, normalized `sources`, normalized `evidence`, `gap_assessment`, `errors`, and `queries_used`. Create nodes `prepare_queries`, `execute_search`, `extract_evidence`, `assess_gap`, and `complete_task`. Search results remain local until normalized. Evidence extraction returns a validated list of claim/excerpt/context/relevance objects, then `build_source` and `build_evidence` assign stable IDs. Cap Sources and EvidenceItems before returning the state patch.

Add `ResearcherHarness` to `tests/fakes.py` with attributes `task`, `brief`, `search`, `total_queries`, method `ainvoke(input_state: dict[str, object]) -> Awaitable[ResearcherOutput]`, and factory `researcher_factory(gaps: list[GapAssessment], total_queries: int = 0) -> ResearcherHarness`. The harness injects FakeSearchProvider and scripted evidence/gap models into the real compiled Researcher graph.

Assemble:

```python
researcher = StateGraph(ResearcherState)
researcher.add_edge(START, "prepare_queries")
researcher.add_edge("prepare_queries", "execute_search")
researcher.add_edge("execute_search", "extract_evidence")
researcher.add_edge("extract_evidence", "assess_gap")
researcher.add_conditional_edges("assess_gap", route_researcher, {"search": "prepare_queries", "done": "complete_task"})
researcher.add_edge("complete_task", END)
```

- [ ] **Step 4: Run Researcher integration tests**

Run: `cd backend && pytest tests/integration/test_researcher_graph.py -v`

Expected: PASS with exactly the scripted query counts.

- [ ] **Step 5: Commit the bounded Researcher loop**

```bash
git add backend/src/deep_research/prompts/research.py backend/src/deep_research/nodes/researcher.py backend/src/deep_research/nodes/gap_analyzer.py backend/src/deep_research/graph/builder.py backend/tests/integration/test_researcher_graph.py
git commit -m "feat: add bounded researcher loop"
```

### Task 5: Supervisor dispatch and global coverage

**Files:**
- Modify: `backend/src/deep_research/nodes/supervisor.py`
- Modify: `backend/src/deep_research/graph/builder.py`
- Create: `backend/tests/integration/test_supervisor_flow.py`

**Interfaces:**
- Consumes: pending tasks, merged task outputs, coverage model, budgets.
- Produces: batches of LangGraph `Send`, one `CoverageDecision`, and at most two additional tasks.

- [ ] **Step 1: Write failing concurrency and one-generation tests**

```python
@pytest.mark.asyncio
async def test_supervisor_never_runs_more_than_three_workers(supervisor_harness) -> None:
    await supervisor_harness.run_with_tasks(5)
    assert supervisor_harness.peak_concurrency == 3


@pytest.mark.asyncio
async def test_supervisor_adds_only_one_generation_and_two_tasks(supervisor_harness) -> None:
    result = await supervisor_harness.run_with_coverage(additional_task_count=3)
    added = [task for task in result["tasks"].values() if task.parent_task_id]
    assert len(added) == 2
    assert result["coverage_checked"] is True
    assert supervisor_harness.coverage_calls == 1
```

- [ ] **Step 2: Run tests to verify missing fan-out behavior**

Run: `cd backend && pytest tests/integration/test_supervisor_flow.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement batched dynamic Send and coverage guard**

Dispatch only pending task IDs, slice each batch to `max_concurrent_researchers`, and create one `Send("research_task", payload)` per task. After all initial tasks settle, call coverage once. Truncate validated additional tasks to two, require a non-empty `gap_reason`, mark `coverage_checked=True`, and never call coverage again.

Add `SupervisorHarness` to `tests/fakes.py` with counters `active_workers`, `peak_concurrency`, and `coverage_calls`; async methods `run_with_tasks(task_count: int) -> ResearchState` and `run_with_coverage(additional_task_count: int) -> ResearchState`; and property access to the injected scripted coverage model. Worker entry increments active/peak counters under an asyncio lock and decrements active workers in `finally`.

- [ ] **Step 4: Run Supervisor integration tests**

Run: `cd backend && pytest tests/integration/test_supervisor_flow.py -v`

Expected: PASS; peak concurrency equals three or less.

- [ ] **Step 5: Commit Supervisor orchestration**

```bash
git add backend/src/deep_research/nodes/supervisor.py backend/src/deep_research/graph/builder.py backend/tests/integration/test_supervisor_flow.py
git commit -m "feat: add bounded supervisor orchestration"
```

### Task 6: Writer, Reviewer, finalizer, and complete graph

**Files:**
- Modify: `backend/src/deep_research/prompts/writing.py`
- Modify: `backend/src/deep_research/prompts/review.py`
- Modify: `backend/src/deep_research/nodes/writer.py`
- Modify: `backend/src/deep_research/nodes/reviewer.py`
- Create: `backend/src/deep_research/nodes/finalizer.py`
- Modify: `backend/src/deep_research/graph/builder.py`
- Create: `backend/tests/integration/test_research_graph.py`

**Interfaces:**
- Consumes: brief, task summaries, Source/Evidence dictionaries, ReportDraft, ReviewResult.
- Produces: validated `draft_report`, bounded review patch, deterministic `final_report`, and `build_research_graph(deps: WorkflowDependencies, checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph`.

- [ ] **Step 1: Write failing end-to-end route tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("verdict,expected_writer_calls,expected_review_tasks", [
    ("pass", 1, 0),
    ("revise", 2, 0),
    ("research_gap", 2, 1),
])
async def test_review_routes_are_bounded(graph_harness, verdict, expected_writer_calls, expected_review_tasks) -> None:
    result = await graph_harness.run(verdict=verdict)
    assert result["status"] == "completed"
    assert graph_harness.writer_calls == expected_writer_calls
    assert graph_harness.review_task_count == expected_review_tasks
    assert graph_harness.reviewer_calls == 1
    assert result["review_action_count"] <= 1


@pytest.mark.asyncio
async def test_no_evidence_fails_without_writer_call(graph_harness) -> None:
    result = await graph_harness.run_without_evidence()
    assert result["status"] == "failed"
    assert graph_harness.writer_calls == 0
```

- [ ] **Step 2: Run the complete graph tests**

Run: `cd backend && pytest tests/integration/test_research_graph.py -v`

Expected: FAIL because Writer/Reviewer/finalizer routing is incomplete.

- [ ] **Step 3: Implement structured writing, review, and finalization**

Writer invokes structured output for `ReportDraft` and receives only evidence packets. Reviewer invokes structured output for `ReviewResult`, references exact IDs, and cannot return more than one follow-up task. `route_review` enforces the single action. Finalizer calls `render_report`; if validation fails after the repair budget is spent, remove the invalid evidence association, append a named limitation, render again, and end without another LLM call.

Expose:

```python
from langgraph.checkpoint.base import BaseCheckpointSaver


def build_research_graph(
    deps: WorkflowDependencies,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    builder = build_research_graph_builder(deps)
    return builder.compile(checkpointer=checkpointer)
```

Define `WorkflowDependencies` as a frozen dataclass in `graph/builder.py` with exact fields `clarifier_model`, `planner_model`, `evidence_model`, `gap_model`, `writer_model`, `reviewer_model`, `search_provider: SearchProvider`, `budgets: ResearchBudgets`, `event_sink: EventSink`, and `cancellation_checker: CancellationChecker`. `EventSink.emit(event_type, payload)` and `CancellationChecker.raise_if_cancelled()` are narrow protocols so the graph does not import FastAPI services. Tests must never construct live providers.

Add `GraphHarness` to `tests/fakes.py` with counters `writer_calls`, `reviewer_calls`, and `review_task_count`; async methods `run(verdict: str) -> ResearchState` and `run_without_evidence() -> ResearchState`; and a compiled real graph using only scripted models and FakeSearchProvider. The `graph_harness` fixture returns a new GraphHarness for each test so counters cannot leak between cases.

- [ ] **Step 4: Run the complete backend graph suite**

Run: `cd backend && pytest tests/unit tests/integration/test_researcher_graph.py tests/integration/test_supervisor_flow.py tests/integration/test_research_graph.py -q && ruff check src tests`

Expected: PASS; no live network calls occur.

- [ ] **Step 5: Commit the complete Agent workflow**

```bash
git add backend/src/deep_research/prompts backend/src/deep_research/nodes backend/src/deep_research/graph backend/tests/integration/test_research_graph.py
git commit -m "feat: complete evidence-driven research graph"
```

## Plan completion gate

Run:

```bash
cd backend
pytest tests/unit tests/integration/test_researcher_graph.py tests/integration/test_supervisor_flow.py tests/integration/test_research_graph.py -q
ruff check src tests
```

Expected: every fake-backed route passes; no run exceeds any task, round, query, concurrency, Supervisor, or Reviewer limit. Do not begin API/persistence work until this gate passes.
