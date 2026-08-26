# Evaluation and Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the completed vertical slice against unsafe URLs, secret leakage, provider failures, and budget overruns; add reproducible evaluation and final portfolio documentation.

**Architecture:** Deterministic guards wrap untrusted boundaries before Agent logic. A fake-backed acceptance suite proves workflow invariants, while a versioned evaluation dataset and runner report quality/cost/latency without making live-provider tests part of default verification.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, HTTPX, Pydantic 2, JSON Lines, Vue/Vitest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-26-deep-research-agent-design.md`

## Global Constraints

- Complete all previous plans first.
- HTTP/HTTPS only; reject localhost, loopback, private/link-local/reserved IPs, file URLs, and unsafe redirects.
- Do not execute page scripts or follow instructions embedded in web content.
- No API keys, raw pages, or provider payloads in logs, SSE, snapshots, or errors.
- All task, round, query, concurrency, Supervisor, Reviewer, Source, and Evidence limits must be proven by tests.
- Zero valid Evidence means failed run, never an unsupported report.
- Partial valid Evidence permits a report only with explicit limitations.
- Default verification uses fake LLM/search only; live evaluation is opt-in.
- No cloud deployment, multi-instance runtime, vector database, academic retrieval, or event replay work.

---

## File map

- `backend/src/deep_research/security/urls.py`: URL and resolved-IP validation.
- `backend/src/deep_research/security/redaction.py`: recursive secret/raw-content redaction.
- `backend/src/deep_research/services/retry.py`: bounded provider retry helper.
- `backend/tests/unit/test_security.py`: SSRF, redaction, and retry tests.
- `backend/tests/acceptance/test_mvp_invariants.py`: fake-backed complete workflow acceptance suite.
- `backend/evals/__init__.py`: marks the evaluation runner as an importable package.
- `backend/evals/cases.jsonl`: fixed versioned research cases.
- `backend/evals/run.py`: evaluation runner.
- `backend/evals/metrics.py`: deterministic metrics and optional judge boundary.
- `backend/tests/unit/test_eval_metrics.py`: metric tests.
- `README.md`: architecture, setup, demo, boundaries, and resume narrative.

### Task 1: URL guard, redaction, and bounded retry

**Files:**
- Create: `backend/src/deep_research/security/__init__.py`
- Create: `backend/src/deep_research/security/urls.py`
- Create: `backend/src/deep_research/security/redaction.py`
- Create: `backend/src/deep_research/services/retry.py`
- Create: `backend/tests/unit/test_security.py`

**Interfaces:**
- Consumes: candidate URL, DNS resolver, nested payload, known secret values, async provider operation.
- Produces: `validate_public_http_url`, `redact_payload`, and `retry_async`.

- [ ] **Step 1: Write failing SSRF, redaction, and retry tests**

```python
import pytest

from deep_research.security.redaction import redact_payload
from deep_research.security.urls import UnsafeUrlError, validate_public_http_url
from deep_research.services.retry import retry_async


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "http://localhost/admin",
    "http://127.0.0.1/private",
    "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.2/internal",
    "http://192.168.1.10/internal",
])
def test_private_and_non_http_urls_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url(url, resolved_ips=[])


def test_nested_payload_redacts_known_secret_and_raw_content() -> None:
    payload = {"token": "secret-value", "nested": {"raw_content": "full page", "message": "secret-value"}}
    assert redact_payload(payload, secrets={"secret-value"}) == {
        "token": "[REDACTED]",
        "nested": {"raw_content": "[OMITTED]", "message": "[REDACTED]"},
    }


@pytest.mark.asyncio
async def test_retry_stops_after_two_retries() -> None:
    attempts = 0
    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("provider timeout")
    with pytest.raises(TimeoutError):
        await retry_async(operation, retries=2, base_delay_seconds=0)
    assert attempts == 3
```

- [ ] **Step 2: Run security tests**

Run: `cd backend && pytest tests/unit/test_security.py -v`

Expected: FAIL because security services do not exist.

- [ ] **Step 3: Implement deterministic boundary guards**

Parse URLs with `urllib.parse`; require `http` or `https`, a hostname, and no embedded credentials. Reject hostname `localhost`. Resolve through an injected async resolver before fetching and reject any `ipaddress.ip_address` that is private, loopback, link-local, multicast, reserved, or unspecified. Revalidate every redirect target.

Redaction recursively traverses dictionaries/lists/strings, replaces exact secret substrings, and replaces keys `raw_content`, `page_body`, `api_key`, `authorization`, and `token` with fixed markers. Retry catches only configured transient exceptions, uses delays `base * 2**attempt`, and re-raises the final exception.

- [ ] **Step 4: Run security tests and lint**

Run: `cd backend && pytest tests/unit/test_security.py -v && ruff check src/deep_research/security src/deep_research/services/retry.py`

Expected: PASS.

- [ ] **Step 5: Commit hardening guards**

```bash
git add backend/src/deep_research/security backend/src/deep_research/services/retry.py backend/tests/unit/test_security.py
git commit -m "feat: harden untrusted research boundaries"
```

### Task 2: Fake-backed MVP invariant acceptance suite

**Files:**
- Create: `backend/tests/acceptance/test_mvp_invariants.py`
- Modify: `backend/tests/fakes.py`
- Modify: `backend/src/deep_research/services/runtime.py`

**Interfaces:**
- Consumes: complete fake-backed application and instrumentation counters.
- Produces: executable proof of every budget, recovery, failure, citation, and cancellation invariant.

- [ ] **Step 1: Write the failing acceptance matrix**

```python
import pytest


@pytest.mark.asyncio
async def test_complete_run_obeys_all_hard_limits(acceptance_harness) -> None:
    result = await acceptance_harness.run_complex_case()
    assert acceptance_harness.initial_task_count <= 5
    assert acceptance_harness.supervisor_task_count <= 2
    assert acceptance_harness.reviewer_task_count <= 1
    assert acceptance_harness.peak_concurrency <= 3
    assert acceptance_harness.total_queries <= 20
    assert max(acceptance_harness.rounds_by_task.values()) <= 2
    assert max(acceptance_harness.queries_by_round.values()) <= 2
    assert acceptance_harness.reviewer_calls == 1
    assert result.status == "completed"
    assert acceptance_harness.invalid_citation_ids == []


@pytest.mark.asyncio
async def test_partial_failure_generates_named_limitation(acceptance_harness) -> None:
    result = await acceptance_harness.run_with_one_failed_task()
    assert result.status == "completed"
    assert "failed task" in result.final_report.lower()


@pytest.mark.asyncio
async def test_zero_evidence_fails_without_report(acceptance_harness) -> None:
    result = await acceptance_harness.run_with_zero_evidence()
    assert result.status == "failed"
    assert result.final_report == ""


@pytest.mark.asyncio
async def test_cancel_prevents_later_nodes(acceptance_harness) -> None:
    result = await acceptance_harness.cancel_after_first_search()
    assert result.status == "cancelled"
    assert acceptance_harness.writer_calls == 0
    assert acceptance_harness.reviewer_calls == 0
```

- [ ] **Step 2: Run the acceptance suite and record violated invariants**

Run: `cd backend && pytest tests/acceptance/test_mvp_invariants.py -v`

Expected: FAIL on any enforcement or instrumentation not yet wired.

- [ ] **Step 3: Connect deterministic guards at orchestration boundaries**

Add counters to state/runtime updates, not prompts. Enforce the global query cap before dispatch, truncate sources/evidence before reducer merge, stop after one coverage decision, stop after one review action, and call cancellation checks immediately before each expensive node. Convert partial failure summaries into explicit report limitations; block Writer when the evidence dictionary is empty.

Implement `AcceptanceHarness` in `tests/fakes.py` with counters `initial_task_count`, `supervisor_task_count`, `reviewer_task_count`, `peak_concurrency`, `total_queries`, `rounds_by_task`, `queries_by_round`, `reviewer_calls`, `writer_calls`, and `invalid_citation_ids`. Provide async methods `run_complex_case()`, `run_with_one_failed_task()`, `run_with_zero_evidence()`, and `cancel_after_first_search()`, each invoking the real graph/runtime with scripted providers. The `acceptance_harness` fixture constructs a fresh instance per test and closes background tasks after use.

- [ ] **Step 4: Run all backend tests**

Run: `cd backend && pytest tests/unit tests/integration tests/acceptance -q && ruff check src tests`

Expected: PASS with no network access.

- [ ] **Step 5: Commit invariant enforcement**

```bash
git add backend/src/deep_research/services/runtime.py backend/tests/fakes.py backend/tests/acceptance/test_mvp_invariants.py
git commit -m "test: enforce deep research MVP invariants"
```

### Task 3: Versioned evaluation dataset and deterministic metrics

**Files:**
- Create: `backend/evals/__init__.py`
- Create: `backend/evals/cases.jsonl`
- Create: `backend/evals/metrics.py`
- Create: `backend/evals/run.py`
- Create: `backend/tests/unit/test_eval_metrics.py`

**Interfaces:**
- Consumes: EvaluationCase, completed snapshot, trace counters, rendered report.
- Produces: per-case JSON result and aggregate metrics for coverage, overlap, citations, budgets, latency, recovery, and transparency.

- [ ] **Step 1: Write failing deterministic metric tests**

```python
from evals.metrics import citation_validity, task_overlap


def test_citation_validity_counts_only_resolvable_ids() -> None:
    assert citation_validity(used_ids={"ev-1", "ev-missing"}, known_ids={"ev-1", "ev-2"}) == 0.5


def test_task_overlap_detects_duplicate_query_sets() -> None:
    tasks = [["langgraph checkpoint"], ["langgraph checkpoint"], ["sse cancellation"]]
    assert task_overlap(tasks) == 1 / 3
```

- [ ] **Step 2: Run metric tests**

Run: `cd backend && pytest tests/unit/test_eval_metrics.py -v`

Expected: FAIL because evaluation modules do not exist.

- [ ] **Step 3: Add the fixed dataset and runner**

Create exactly these 15 versioned cases in JSON Lines with fields `case_id`, `query`, `category`, `requires_clarification`, and `expected_dimensions`:

1. Compare LangGraph and CrewAI for production Agent orchestration in 2026.
2. Compare PostgreSQL and SQLite checkpoint storage for a single-instance AI research service.
3. Analyze current approaches to reducing hallucinated citations in web research agents.
4. Compare OpenAI-compatible local model serving with hosted APIs for an internship portfolio project.
5. Assess the advantages and limitations of SSE versus WebSocket for long-running AI tasks.
6. Explain how bounded reflection differs from unrestricted autonomous Agent loops.
7. Compare three common web-search APIs for evidence-oriented AI research.
8. Analyze the engineering risks of parallel LLM tool calls.
9. Evaluate whether vector memory is necessary for a single-session research agent.
10. Compare deterministic citation rendering with LLM-generated citation formatting.
11. Research the market growth. (clarification required)
12. Compare these two systems. (clarification required)
13. Analyze conflicting public claims about the reliability of LLM-as-Judge evaluation.
14. Identify best practices for preventing prompt injection from retrieved web pages.
15. Assess when a research agent should return insufficient evidence instead of a report.

The runner defaults to fake mode and accepts `--live` explicitly. It writes JSON results outside the repository under a caller-provided output path. It records model/search configuration names without credentials. `citation_validity` and budget compliance are deterministic; optional judge metrics are kept behind a protocol and never required for the default run.

- [ ] **Step 4: Run metric tests and fake evaluation**

Run: `cd backend && pytest tests/unit/test_eval_metrics.py -v && python -m evals.run --mode fake --output ../tmp/eval-results.json`

Expected: PASS and a JSON result containing 15 cases plus aggregate metrics.

- [ ] **Step 5: Commit evaluation assets**

```bash
git add backend/evals backend/tests/unit/test_eval_metrics.py
git commit -m "feat: add reproducible research evaluation"
```

### Task 4: Portfolio README and final verification instructions

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Create: `backend/tests/acceptance/test_readme_commands.py`

**Interfaces:**
- Consumes: actual backend/frontend commands and verified architecture.
- Produces: reproducible setup, demo, architecture explanation, limitations, evaluation instructions, and resume-ready engineering narrative.

- [ ] **Step 1: Write a failing documentation-command test**

```python
from pathlib import Path


def test_readme_contains_verified_commands_and_boundaries() -> None:
    readme = Path("../README.md").read_text(encoding="utf-8")
    required = [
        "pytest tests/unit tests/integration tests/acceptance -q",
        "npm run test:run",
        "npm run build",
        "MAX_TOTAL_SEARCH_QUERIES=20",
        "SSE history replay is not supported",
        "single FastAPI instance",
    ]
    assert all(item in readme for item in required)
```

- [ ] **Step 2: Run the documentation test**

Run: `cd backend && pytest tests/acceptance/test_readme_commands.py -v`

Expected: FAIL because README is empty.

- [ ] **Step 3: Write the portfolio README**

Include: problem statement, architecture diagram, module responsibilities, evidence model, bounded loops, deterministic citations, SSE event examples, local setup, environment variables, backend/frontend commands, fake evaluation, optional live evaluation warning, screenshots section with no fabricated images, known limitations, non-goals, and a concise “What I redesigned” section comparing the two source projects without claiming their original work as newly authored.

Document exact local commands and state that SQLite/single-instance semantics do not support horizontal scaling. Explain that live evaluation incurs provider cost and is never run by default.

- [ ] **Step 4: Run final project verification**

Run:

```bash
cd backend
pytest tests/unit tests/integration tests/acceptance -q
ruff check src tests evals
python -m evals.run --mode fake --output ../tmp/eval-results.json
cd ../frontend
npm run test:run
npm run build
```

Expected: every command exits 0, fake evaluation reports 15 cases, no live API is called, and no credentials appear in output.

- [ ] **Step 5: Commit documentation and acceptance command checks**

```bash
git add README.md .env.example backend/tests/acceptance/test_readme_commands.py
git commit -m "docs: document deep research architecture and demo"
```

## Final acceptance gate

Run the exact verification block from Task 4, then manually demonstrate one clear query, one clarification/resume query, one cancellation, one partial-task failure, one Reviewer revision, one Reviewer research-gap repair, and one page refresh restoration. Record observed task/query/concurrency counters and confirm every value remains within the approved budgets.

Do not claim the MVP complete until automated verification exits 0 and the manual scenarios match `docs/superpowers/specs/2026-08-26-deep-research-agent-design.md`.
