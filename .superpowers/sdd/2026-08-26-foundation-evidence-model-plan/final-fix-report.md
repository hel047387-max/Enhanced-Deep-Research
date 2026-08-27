# Foundation final review fix report

Base reviewed head: `38044647b88d521c032a1d5b5cc50b85bcf00068`

Worktree: `D:\科研助手\enhanced-deep-research\.worktrees\deep-research-mvp`

## Baseline and method

- The worktree was clean, on `feature/deep-research-mvp`, and exactly at the reviewed head.
- Baseline command: `backend\.venv\Scripts\python.exe -m pytest tests\unit -q`
- Baseline output: `41 passed in 1.25s`.
- Strict TDD was used: all focused regressions were added before production changes, each suite was run to capture an expected behavior failure, and only then were production contracts changed.
- The standard patch helper failed with `windows sandbox failed: helper_unknown_error: setup refresh had errors`; the task-provided `codex.exe --codex-run-as-apply-patch` fallback was used successfully.

## 1. Critical URL normalization and policy mismatch

### RED

Command:

```text
backend\.venv\Scripts\python.exe -m pytest tests\unit\test_evidence_store.py -q
```

Output summary: `11 failed, 22 passed in 0.82s`.

Expected failures demonstrated that Unicode-dot loopback, percent-encoded numeric loopback, and userinfo were accepted; Unicode/punycode and trailing-dot aliases produced different canonical strings/IDs; direct `Source` construction accepted the unsafe aliases; and multicast was not rejected as non-global-unicast.

### Implementation

- Added one shared authority normalization/policy boundary that percent-decodes the host, maps Unicode dot forms, strips a trailing root dot, case-folds, IDNA-encodes names, normalizes IP literals, rejects userinfo, and rejects localhost and non-global-unicast literal addresses.
- `canonicalize_url` now consumes that normalized authority before query/path normalization and hashing.
- `Source` field validation returns the normalized URL, so direct construction is revalidated and stores the same authority form.
- Added a single canonical-URL source-ID helper used by `build_source` and the source reducer.
- No DNS, redirect, or rebinding behavior was added.

### GREEN

Command: same focused command as RED.

Output: `33 passed in 0.18s`.

Files:

- `backend/src/deep_research/domain/evidence.py`
- `backend/src/deep_research/services/evidence_store.py`
- `backend/tests/unit/test_evidence_store.py`

## 2. Important failed-task citation validation

### RED

Command:

```text
backend\.venv\Scripts\python.exe -m pytest tests\unit\test_citations.py -q
```

Output summary: `12 failed, 1 passed in 1.20s`.

Expected failures showed that `validate_draft`/`render_report` had no run-scoped task parameter, could not reject missing or failed task references, and did not yet enforce the new review semantics described below.

### Implementation

- Extended `validate_draft` and `render_report` with a required run-scoped `Mapping[str, ResearchTask]`.
- Cited evidence now produces deterministic issues when `task_id` is absent from the run or belongs to `TaskStatus.FAILED`.
- Completed and insufficient known tasks remain eligible.
- Source numbering and first-appearance ordering were left unchanged.

### GREEN

Command: same focused command as RED.

Output: `13 passed in 0.16s`.

Files:

- `backend/src/deep_research/services/citations.py`
- `backend/tests/unit/test_citations.py`

## 3. Important deterministic source reducer

### RED

Command:

```text
backend\.venv\Scripts\python.exe -m pytest tests\unit\test_reducers.py -q
```

Output summary: `7 failed, 11 passed in 1.58s`.

Expected source failures showed that the generic mapping alias accepted key/value ID mismatches and noncanonical IDs, failed to deduplicate Unicode/punycode aliases, and selected conflicting metadata/content according to operand order.

### Implementation

- Replaced the `merge_sources = merge_mapping` alias with a Source-specific reducer.
- Every input entry must have a mapping key equal to `Source.source_id`, and the ID must be derived from the normalized canonical URL.
- Canonical aliases therefore share one identity and one mapping entry.
- Conflicting snapshots select the newest retrieval; ties use the complete serialized Source as a stable total-order tiebreak. The whole Source snapshot wins, so metadata is never mixed with another content hash.
- Result keys are sorted, and the reducer is commutative, associative, and non-mutating for valid patches.

### GREEN

Command: same focused command as RED.

Output: `18 passed in 0.95s`.

Files:

- `backend/src/deep_research/state/reducers.py`
- `backend/tests/unit/test_reducers.py`

## 4. Important Settings budget caps

### RED

Command:

```text
backend\.venv\Scripts\python.exe -m pytest tests\unit\test_config.py -q
```

Output summary: `18 failed, 3 passed in 0.96s`.

Each direct and environment-loaded over-cap value constructed a `Settings` object instead of failing immediately.

### Implementation

- Defined reusable annotated integer constraints for all nine research budgets.
- Applied the same lower and upper bounds to both `ResearchBudgets` and `Settings`, so direct arguments and environment loading validate during `Settings` construction.

### GREEN

Command: same focused command as RED.

Output: `21 passed in 0.28s`.

Files:

- `backend/src/deep_research/config.py`
- `backend/tests/unit/test_config.py`

## 5. Minor ReviewResult semantics

### RED

The citation focused RED command above showed three contract failures: `research_gap` accepted zero follow-up tasks, while `pass` and `revise` accepted a follow-up task.

### Implementation

- Added a local model validator: `RESEARCH_GAP` requires exactly one follow-up task; `PASS` and `REVISE` forbid follow-up tasks.
- The existing field maximum of one continues to reject multiple follow-up tasks.
- The optional PASS/blocking-issue restriction was not added because it was not required for the verdict/follow-up contract.

### GREEN

Covered by `13 passed in 0.16s` for `tests\unit\test_citations.py`.

Files:

- `backend/src/deep_research/domain/review.py`
- `backend/tests/unit/test_citations.py`

## 6. Minor recursive JSON compatibility

### RED

The reducer focused RED command above showed three non-finite cases (`NaN`, positive infinity, negative infinity) accepted at both direct and nested payload positions.

### Implementation

- Float validation now requires `math.isfinite`.
- Existing recursive list/dict validation therefore rejects non-finite values at any payload depth.

### GREEN

Covered by `18 passed in 0.95s` for `tests\unit\test_reducers.py`.

Files:

- `backend/src/deep_research/domain/events.py`
- `backend/tests/unit/test_reducers.py`

## Combined GREEN and completion gates

- Focused combined command:
  `backend\.venv\Scripts\python.exe -m pytest tests\unit\test_evidence_store.py tests\unit\test_config.py tests\unit\test_citations.py tests\unit\test_reducers.py -q`
- Focused combined output: `85 passed in 1.24s`.
- Full Foundation command:
  `backend\.venv\Scripts\python.exe -m pytest tests\unit -v --cov=deep_research --cov-report=term-missing`
- Full Foundation output: `88 passed in 2.37s`; total coverage `96%`.
- Ruff command: `backend\.venv\Scripts\ruff.exe check src tests`
- Ruff output: `All checks passed!`
- Import gate:
  `backend\.venv\Scripts\python.exe -c "from deep_research.state.models import ResearchState; print(ResearchState.__name__)"`
- Import output: `ResearchState`.
- `git diff --check`: exit 0; only Git's existing LF-to-CRLF working-copy warnings were emitted.

## Self-review

- Re-read the binding URL security, citation, reviewer, reducer, budget, and event requirements against the final diff.
- Confirmed all citation callers in the current Foundation tree pass run-scoped tasks and source numbering logic is unchanged.
- Confirmed the source reducer validates both operands before conflict resolution, selects whole snapshots, does not mutate inputs, and passes permutation plus parallel grouping tests.
- Confirmed every Settings budget reuses the same bounds as `ResearchBudgets`, including environment construction.
- Confirmed raw bodies remain excluded from Source/state, and no DNS, redirect, network, Agent, API, or frontend scope entered this wave.
- Mutation check: removing authority normalization, task-status checks, source identity checks, deterministic conflict ordering, Settings field constraints, verdict validator, or `isfinite` makes at least one focused regression fail.

## Concerns

- No product-code concerns remain within the Foundation scope.
- Environment note only: commands must use `backend\.venv`; the system Python lacks `langchain_core`. The standard patch helper also had the known Windows refresh failure, successfully handled with the supplied fallback.
