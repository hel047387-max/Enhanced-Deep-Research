# Case study: SSE vs. WebSocket

## Research question

> Compare Server-Sent Events and WebSocket for streaming progress from long-running AI jobs.

This case was selected because it maps directly to the project's FastAPI/SSE delivery path and completed the full Planner → Researcher → evidence → Writer → Reviewer workflow without a runtime error or failed-task notice.

## Execution trace

| Signal | Observed value |
| --- | ---: |
| Initial action | `research` (expected) |
| Planner/Reviewer tasks | 7 |
| Search queries | 20 |
| Collected sources | 26 |
| Evidence items | 120 |
| Streamed events | 60 |
| End-to-end latency | 186.4 s |
| Citation-ID validity | 1.00 |
| Source requirement | 1.00 |
| Case-budget compliance | 0.00 |
| Reviewer verdict | `revise` |

## Report outcome

The generated report distinguished the protocols by communication direction and operational behavior:

- SSE keeps an ordinary HTTP response open and is naturally suited to one-way server-to-browser progress updates.
- WebSocket provides bidirectional communication and is justified when the client must send interactive messages over the same persistent channel.
- For this project's progress stream, the report recommended SSE, with ordinary HTTP endpoints handling commands such as cancellation.
- It also discussed reconnect behavior, proxy/load-balancer compatibility, authentication, and scaling trade-offs.

This recommendation matches the implemented architecture: FastAPI streams observable progress to the browser over SSE while control operations remain explicit HTTP requests.

## What the evaluation demonstrated

1. The planner decomposed one architecture question into multiple research tasks.
2. Researchers issued bounded searches and normalized findings into evidence records.
3. The writer used only source identifiers present in the current run; deterministic validation found no dangling citation IDs.
4. The reviewer did not blindly approve the report and returned `revise`.

## Honest limitations

- The run used all 20 globally available searches and exceeded the lower case-specific budget, so cost control failed for this case.
- Citation-ID validity checks referential integrity, not whether a citation fully entails the surrounding claim.
- Several performance claims came from third-party benchmarks rather than a controlled benchmark executed in this repository.
- The `revise` verdict means the report should not be presented as a final, independently verified protocol study.

## Interview discussion

This case supports a concrete explanation of why SSE was selected for the project: the data flow is mainly server-to-browser, reconnect semantics are useful for long jobs, and HTTP endpoints already cover client-to-server commands. It also exposes a real improvement target—enforcing the per-case budget instead of relying only on the global cap.
