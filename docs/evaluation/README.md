# Evaluation evidence

This directory publishes reproducible evaluation evidence for Enhanced Deep Research. It deliberately separates deterministic regression checks from provider-backed quality examples.

## Offline regression

The versioned dataset contains 50 cases across eight categories. The offline runner uses scripted model and search adapters, so it makes no network calls and consumes no provider quota. It verifies dataset, CLI, routing, metric, recovery, and serialization contracts; it does **not** measure real search or report quality.

Run it from `backend`:

```powershell
.\.venv\Scripts\python.exe -m evals.run --mode fake --output evals\results\offline-50.json
```

The checked-in [offline result](../../backend/evals/results/offline-50.json) contains all 50 cases. Its aggregate deterministic metrics are:

| Metric | Result |
| --- | ---: |
| Plan coverage | 1.00 |
| Task overlap | 0.00 |
| Citation-ID validity | 1.00 |
| Evidence grounding | 1.00 |
| Source diversity | 3.00 |
| Budget compliance | 1.00 |
| Recovery success | 1.00 |
| Failure transparency | 1.00 |

The reported latency is `0 ms` because the adapters are scripted. These values are contract checks, not claims about production answer quality.

## Provider-backed case studies

A live run on 2026-10-07 completed 10 technical-comparison cases before the configured model account returned `402 Insufficient Balance`. The remaining 30 attempted cases were excluded from the examples. Because all 10 valid cases belong to one category, they are a technical-comparison subset rather than a representative score for the entire 50-case benchmark.

Two cases were selected because they completed without runtime errors or failed-task notices and directly exercise portfolio-relevant design decisions:

- [SSE vs. WebSocket for long-running AI jobs](case-studies/eval-003-sse-vs-websocket.md)
- [Qdrant vs. pgvector for a small literature RAG service](case-studies/eval-008-qdrant-vs-pgvector.md)

Both examples preserve unfavorable signals: each exceeded its case-specific search budget and received a Reviewer verdict of `revise`. Citation-ID validity means every rendered citation points to a source collected in that run; it does not prove that every cited source semantically supports every claim.

## Interpretation boundary

- Offline results prove deterministic software contracts only.
- Live examples demonstrate the end-to-end Agent path, not statistical model quality.
- Atomic semantic rubric items remain `not_scored`; no LLM-as-judge score is presented.
- Reports depend on time-sensitive public web sources and should be re-run before treating factual details as current.
