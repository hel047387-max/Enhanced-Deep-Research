# Case study: Qdrant vs. pgvector

## Research question

> Compare Qdrant and pgvector for a small literature RAG service.

This case was selected because it corresponds to the project's literature-RAG storage decision and completed the full Agent workflow without a runtime error or failed-task notice.

## Execution trace

| Signal | Observed value |
| --- | ---: |
| Initial action | `research` (expected) |
| Planner/Reviewer tasks | 6 |
| Search queries | 20 |
| Collected sources | 36 |
| Evidence items | 100 |
| Streamed events | 57 |
| End-to-end latency | 189.8 s |
| Citation-ID validity | 1.00 |
| Source requirement | 1.00 |
| Case-budget compliance | 0.00 |
| Reviewer verdict | `revise` |

## Report outcome

The generated report avoided treating one database as universally superior:

- pgvector is attractive when PostgreSQL is already the system of record and avoiding another service matters more than specialized vector features.
- Qdrant is attractive when the project benefits from a dedicated vector engine, built-in hybrid-search capabilities, and vector-focused operational tooling.
- The recommendation for a small RAG service depends on data locality, existing infrastructure, tuning effort, and expected scale.
- The report proposed a workload-specific proof of concept instead of relying entirely on published benchmark numbers.

The project currently uses Qdrant behind an application boundary, allowing the ingestion, retrieval, and evidence layers to remain conceptually separate from the storage client.

## What the evaluation demonstrated

1. Planning covered performance, operational burden, data locality, cost, and feature trade-offs.
2. The research stage collected 36 sources and normalized 100 evidence items.
3. The writer produced a conditional recommendation instead of a one-size-fits-all answer.
4. Deterministic citation validation found no references to unknown source IDs.
5. The reviewer returned `revise`, preserving a visible quality-control signal.

## Honest limitations

- The run exhausted the 20-query global allowance and exceeded its lower case-specific search budget.
- Vendor and third-party benchmarks use different datasets, hardware, index parameters, and recall targets, so their raw numbers are not directly comparable.
- Pricing and free-tier details are time-sensitive and must be checked again before making a purchasing decision.
- Citation-ID validity does not replace claim-level semantic verification.
- The `revise` verdict means the report is evidence for the Agent workflow, not a definitive database benchmark.

## Interview discussion

This case demonstrates that the project treats RAG as an engineering system rather than only an embedding demo: storage selection depends on operational constraints, retrieval features, evidence traceability, and cost. It also provides a natural explanation for keeping vector-store access behind an adapter so a later pgvector implementation would not require rewriting the Agent graph.
