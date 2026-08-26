# Enhanced Deep Research Agent Design

- Date: 2026-08-26
- Status: Design approved; written spec pending user review
- Scope: Architectural design only
- Target: General web deep research portfolio project

## 1. Purpose

Build a portfolio-ready Deep Research Agent that combines the strongest ideas from the two reference projects without simply merging them. The system uses LangGraph for explicit stateful orchestration and adopts the second project's observable task execution, SSE progress stream, and user-facing workflow.

The differentiating design is an evidence-driven research loop: planning, bounded parallel research, structured evidence extraction, explicit gap analysis, limited re-search, deterministic citation rendering, and one bounded Writer–Reviewer repair action.

## 2. MVP success definition

Given a user question, the system must:

1. Ask at most one clarification question when essential scope is missing.
2. Resume the same thread after the user answers.
3. Create three to five complementary research tasks.
4. Execute at most three Researcher workers concurrently.
5. Search, normalize sources, and extract structured evidence.
6. Perform task-level gap analysis and at most one additional search round per task.
7. Perform one global coverage check and add at most two targeted tasks.
8. Generate an evidence-grounded report.
9. Run one Reviewer pass that may trigger at most one revision or one targeted re-search task.
10. Stream the observable workflow to the frontend through SSE.
11. Persist graph checkpoints in SQLite and export the final report as Markdown.

The system is autonomous within explicit budgets; it is not an unbounded autonomous loop.

## 3. Architecture

```text
START
  |
  v
Clarifier --------------------> interrupt / wait for user
  |                                      |
  |                                   resume
  |                                      |
  +--------------------------------------+
  |
  v
Research Brief
  |
  v
Planner: 3-5 ResearchTasks
  |
  v
Supervisor Dispatch: concurrency <= 3
  |
  +--> Researcher 1: Search -> Evidence -> Gap Analysis --+
  +--> Researcher 2: Search -> Evidence -> Gap Analysis --+--> Merge
  +--> Researcher 3: Search -> Evidence -> Gap Analysis --+
  |
  v
Supervisor Coverage Check
  |
  +--> sufficient -------------------------------+
  +--> add at most 2 targeted tasks -> Research --+
                                                   |
                                                   v
                                                 Writer
                                                   |
                                                   v
                                                Reviewer
                                      +------------+------------+
                                      |            |            |
                                    pass         revise    research_gap
                                      |        once only     once only
                                      +------------+------------+
                                                   |
                                                   v
                                      Citation Validator/Renderer
                                                   |
                                                   v
                                             Final Report -> END
```

Every graph node may publish typed progress events through the Event Stream service. Events expose decisions and results, never private chain-of-thought.

## 4. Component boundaries

### 4.1 Clarifier

Determines whether the question lacks essential subject, time range, or comparison criteria. It may interrupt once. After one clarification, remaining ambiguity becomes an explicit assumption rather than another question.

### 4.2 Research Brief

Converts the conversation into a stable brief containing the main question, scope, time range, comparison dimensions, expected output, source preferences, assumptions, and exclusions.

### 4.3 Planner

Runs exactly once. It creates three to five standalone, non-overlapping tasks with clear objectives, completion criteria, and one or two initial queries. It does not search, write the report, or re-plan later.

### 4.4 Supervisor

Controls dispatch, concurrency, and one global coverage decision. It does not search directly and does not recreate the plan. After initial tasks finish, it may add at most two tasks tied to explicit global evidence gaps. It cannot add another generation of tasks afterward.

### 4.5 Researcher

Owns one task. It prepares queries, calls the search provider, normalizes sources, extracts evidence, and runs a structured gap assessment. A task may execute at most two search rounds with at most two queries per round.

### 4.6 Writer

Produces a structured report draft from the Research Brief, completed task summaries, Sources, and EvidenceItems. It cannot search or invent source identifiers.

### 4.7 Reviewer

Checks coverage, grounding, citation completeness, contradictions, overclaiming, and clarity. It may return `pass`, `revise`, or `research_gap`. Only one Reviewer action is allowed.

### 4.8 Finalizer

Validates evidence references, renders deterministic citations and Markdown, records limitations, freezes the report, and ends the graph.

### 4.9 Cross-cutting services

- Event Stream publishes typed SSE events without influencing Agent decisions.
- Checkpoint persistence stores committed Graph State and interrupt state.
- Evidence Store provides normalized state access; it is not a separate vector database in the MVP.
- SearchProvider isolates Tavily behind a replaceable interface, but only Tavily is implemented initially.

## 5. Domain model

Domain objects use Pydantic models for validation and serialization. LangGraph state uses a TypedDict with annotated reducers. Domain validation and graph merge behavior remain separate concerns.

### 5.1 ResearchTask

```text
ResearchTask
- task_id
- title
- objective
- completion_criteria
- search_queries[]
- status: pending | running | completed | insufficient | failed
- current_round: 0..2
- parent_task_id: optional
- gap_reason: optional
- error: optional
```

### 5.2 Source

```text
Source
- source_id
- url
- canonical_url
- title
- domain
- published_at: optional
- retrieved_at
- content_hash
- source_type: web | official | news
```

Sources are deduplicated by canonical URL. Content hashes identify changed content. The MVP does not expose a pseudo-precise LLM credibility score.

### 5.3 EvidenceItem

```text
EvidenceItem
- evidence_id
- task_id
- source_id
- claim
- excerpt
- context
- relevance: high | medium | low
- discovered_in_round
- citation_label
```

A Source may produce multiple EvidenceItems. Evidence remains traceable to a task and source. Raw webpage bodies are transient and never stored in checkpoints.

### 5.4 GapAssessment

```text
GapAssessment
- task_id
- coverage: sufficient | partial | insufficient
- covered_questions[]
- missing_questions[]
- evidence_issues[]
- next_queries[]
- should_continue
- reason
```

Re-search occurs only when `should_continue` is true, the current round is below two, queries remain, and the global search budget is available.

### 5.5 ReviewResult

```text
ReviewResult
- verdict: pass | revise | research_gap
- blocking_issues[]
- unsupported_claims[]
- conflicting_evidence[]
- missing_sections[]
- revision_instructions[]
- follow_up_tasks[]
```

Review issues reference section, paragraph, and evidence identifiers. The Reviewer cannot modify Evidence directly.

### 5.6 ResearchState

```text
ResearchState
- run_id
- thread_id
- messages[]
- clarification_count
- research_brief
- tasks{}
- sources{}
- evidence{}
- gap_assessments{}
- supervisor_added_tasks
- draft_report
- review_result
- review_action_count
- final_report
- status
- errors[]
```

Reducers merge tasks by task ID, sources by canonical URL, evidence by evidence ID, append errors, and use LangGraph message reducers for messages. Parallel workers return isolated patches rather than mutating shared lists.

SSE events are not stored in ResearchState. A refreshed client restores the current projection through the state API; MVP SSE history replay is out of scope.

## 6. Planning and research flow

Planner tasks must be independently executable, cover one subproblem each, avoid overlap, and exclude report-writing work. Each Researcher receives only the brief, its task, and its budget. Researcher message histories remain isolated.

Researcher output is a local patch:

```text
ResearcherOutput
- updated_task
- sources{}
- evidence{}
- gap_assessment
- errors[]
```

The Supervisor coverage decision receives the brief, task statuses, gap assessments, and evidence metadata. It does not receive raw pages or recreate the original plan.

At most five initial plus two Supervisor tasks may exist before writing. A Reviewer may add one final targeted task, producing an absolute maximum of eight tasks in a run.

## 7. Writer, citations, and review

The Writer returns a structured ReportDraft instead of free-form Markdown:

```text
ReportDraft
- title
- executive_summary[]
- sections[]
  - heading
  - paragraphs[]
    - text
    - evidence_ids[]
- limitations[]
- suggested_actions[]
```

The deterministic renderer validates Evidence IDs, maps Evidence to Source, assigns source numbers by first appearance, and generates Markdown links and a references section. Evidence from the same Source shares one source number.

Before the LLM Reviewer runs, deterministic validation checks that Evidence and Source IDs exist, belong to the current run, contain usable URLs, and are not attached to failed results.

Reviewer routing is bounded:

- `pass`: render and finalize.
- `revise`: Writer revises once using existing Evidence, then validation and finalization run.
- `research_gap`: create at most one targeted task, research it within normal task budgets, revise once, then validate and finalize.

The revised report never returns to the Reviewer. If final validation still finds unsupported material, the finalizer marks it as insufficient evidence and records the limitation instead of starting another loop.

## 8. FastAPI and SSE

`thread_id` identifies a resumable conversation and LangGraph checkpoint. `run_id` identifies one execution attempt, so clarification resume receives a new run ID within the same thread.

MVP endpoints:

```text
POST /api/v1/research/stream
POST /api/v1/research/{thread_id}/resume/stream
GET  /api/v1/research/{thread_id}
GET  /api/v1/research/{thread_id}/report
POST /api/v1/research/{thread_id}/cancel
GET  /health
```

There is no separate synchronous research implementation. Both initial and resumed runs use the same graph and SSE execution path.

SSE events share one envelope:

```json
{
  "type": "task_started",
  "run_id": "run-002",
  "thread_id": "thread-123",
  "sequence": 12,
  "timestamp": "2026-08-26T00:00:00Z",
  "payload": {}
}
```

Event types include:

- run_started
- clarification_required
- research_brief_created
- plan_created
- task_started
- search_started
- search_completed
- evidence_added
- gap_assessed
- task_completed
- task_failed
- coverage_assessed
- additional_tasks_created
- draft_created
- review_completed
- revision_started
- report_finalized
- run_cancelled
- error
- done

The frontend sends both an AbortController cancellation and an explicit cancel request. The backend checks cancellation around search, extraction, re-search, writing, and review boundaries. In-flight external requests may finish, but no later node may start after cancellation is observed.

## 9. Persistence and recovery

SQLite stores LangGraph checkpoints and lightweight run metadata:

```text
RunMetadata
- run_id
- thread_id
- status: created | running | waiting_for_user | completed | failed | cancelled
- created_at
- updated_at
- cancelled_at: optional
- last_error: optional
```

State is committed at graph node boundaries. If the process stops during an external search, resumption may repeat that search. The MVP does not promise exactly-once external calls; canonical URL deduplication and deterministic evidence identifiers prevent duplicate state.

## 10. Frontend projection

The Vue frontend keeps a lightweight reactive store without adding Pinia in the MVP:

```text
ResearchUIState
- threadId
- runId
- status
- clarification
- researchBrief
- tasks{}
- sources{}
- evidence{}
- review
- report
- progressEvents[]
- error
```

All SSE events pass through one `applyResearchEvent` reducer. Components have isolated responsibilities:

- ResearchForm handles initial input, clarification, and cancellation.
- ResearchPlan displays the brief and task plan.
- TaskProgress displays task status and search rounds.
- EvidencePanel displays sources and evidence.
- ReviewPanel displays review findings and the selected repair action.
- ReportViewer renders the final Markdown report.

Page refresh uses the state snapshot endpoint. Historical SSE replay is not included.

## 11. Errors and degradation

Errors use a structured ResearchError containing code, stage, message, task ID, retryability, attempt count, and sanitized details.

- Search failures retry at most twice.
- LLM transport errors retry at most once.
- Invalid structured output receives one repair attempt.
- Checkpoint write failure stops the run immediately.
- One task failure does not stop independent tasks.
- Partial valid evidence permits a report with explicit limitations.
- No valid evidence across all tasks fails the run instead of generating an unsupported report.
- Reviewer failure preserves the draft, performs deterministic citation validation, and marks review as incomplete.

## 12. Budgets

Hard server-side limits:

```text
initial tasks                 <= 5
Supervisor-added tasks       <= 2
Reviewer-added tasks         <= 1
research rounds per task     <= 2
queries per round            <= 2
concurrent Researchers       <= 3
total search queries         <= 20
Reviewer repair actions      <= 1
Sources per task             <= 8
EvidenceItems per task       <= 20
```

The global search cap overrides remaining local budgets. Clients cannot increase these limits through request parameters.

## 13. Security

- Only HTTP and HTTPS sources are accepted.
- Localhost, loopback, private IP ranges, and file protocols are rejected.
- Response size, redirects, and timeouts are bounded.
- Web content is treated as untrusted data and cannot provide Agent instructions.
- Scripts from fetched content are never executed.
- API keys, full raw pages, and sensitive provider responses never enter logs or SSE.
- Production CORS uses an explicit allowlist.
- Tavily-provided content is preferred; a general-purpose crawler is outside the MVP.

## 14. Testing and evaluation

### 14.1 Unit tests

Unit coverage includes URL canonicalization, source deduplication, evidence merging, parallel reducers, budget routing, second-round routing, Supervisor limits, Reviewer limits, citation validation/rendering, event reduction, and cancellation transitions.

### 14.2 Graph tests

Fake LLM and Fake Search implementations cover clear queries, one clarification interrupt and resume, parallel merge, evidence-insufficient re-search, global coverage tasks, `pass`, `revise`, `research_gap`, cancellation, and every hard budget.

### 14.3 API and integration tests

Tests cover SSE envelopes and ordering, resume endpoints, errors, cancellation, SQLite checkpoint recovery, state snapshot consistency, restart from committed nodes, and frontend handling of interleaved task events.

Default CI never calls a real LLM or Tavily. Live tests are explicitly marked and run manually or on a controlled schedule.

### 14.4 Evaluation set

Maintain 15-20 fixed questions spanning technical comparison, product/company comparison, industry trends, time-sensitive topics, multi-dimensional questions, ambiguous inputs, conflicting sources, and weak-evidence topics.

Metrics include plan coverage, task overlap, citation validity, evidence grounding, source diversity, completion within budget, recovery success, latency, and failure transparency. Deterministic metrics are preferred; LLM-as-Judge is secondary and versioned.

## 15. Configuration and deployment boundary

Environment configuration includes LLM provider/model credentials, Tavily credentials, SQLite path, allowed CORS origins, and log level. Server configuration owns every hard research budget.

The MVP supports a local or single-instance deployment:

```text
Vue/Vite frontend
        |
Single FastAPI instance
        +-- LangGraph
        +-- SQLite checkpoint
        +-- Tavily and LLM APIs
```

Multiple FastAPI workers, distributed queues, and horizontally scaled SSE are excluded because SQLite and non-persistent live events do not provide the required coordination semantics.

## 16. Non-goals

- User accounts, authorization, or multi-tenancy
- Long-term user profile memory
- Vector databases
- Full claim or knowledge graphs
- Academic-paper-specific retrieval
- PDF or file upload
- Multiple implemented search providers
- SSE history replay
- Distributed workers or multi-instance deployment
- Unbounded Agent loops
- Automatic publication, email delivery, or administration UI
- Cloud deployment and CI/CD in the Agent-core MVP

These may appear in a roadmap but cannot enter the MVP implementation scope without a new design cycle.

## 17. Acceptance criteria

The MVP is accepted only when all of the following are demonstrable:

- An ambiguous question interrupts at most once and resumes under the same thread ID.
- A clear question creates three to five complementary tasks.
- Researcher concurrency never exceeds three.
- Each task executes at most two research rounds.
- Search results become traceable Sources and EvidenceItems.
- Gap Analysis triggers re-search only when both local and global budgets permit it.
- Supervisor adds at most two tasks.
- Writer uses only known Evidence IDs.
- Final citations are rendered deterministically and resolve to real Sources.
- Reviewer triggers at most one revision or targeted research action.
- Total search queries never exceed twenty.
- SSE displays planning, task, evidence, gap, review, and report progress.
- Users can cancel a run.
- Page refresh restores the current state projection.
- Process restart resumes from the latest committed checkpoint.
- A failed task does not erase successful independent work.
- A run with no valid evidence does not fabricate a report.
- Fake-based workflow tests are deterministic.
- The evaluation set reports comparable quality, budget, and latency results.

## 18. Resolved decisions

- LangGraph is the orchestration backbone.
- The product targets general web research, not academic research in the MVP.
- The repository is a backend/frontend/docs/tests monorepo.
- Clarification is limited to one interrupt.
- Planner creates the initial plan; Supervisor performs only bounded adaptation.
- Research is evidence-driven and bounded to two rounds per task.
- Evidence uses Source plus EvidenceItem rather than raw note strings or a full claim graph.
- Writer output is structured and citations are rendered by code.
- Reviewer has one repair action.
- SQLite provides checkpoint persistence.
- Tavily is the only initial search implementation behind an interface.
- SSE exposes observable workflow events and supports cancellation, but not event replay.

This document defines architecture and behavior. It intentionally contains no implementation task ordering or implementation plan.
