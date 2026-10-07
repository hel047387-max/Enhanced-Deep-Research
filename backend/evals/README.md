# Evaluation dataset

`cases.jsonl` is the versioned project benchmark for Enhanced Deep Research. It contains 50 cases. The fake runner is an offline contract smoke test; the live runner starts the production application lifecycle and executes the real Agent with the configured model and Tavily provider.

## Distribution

| Category | Cases | Primary capability |
| --- | ---: | --- |
| `technical_comparison` | 10 | Planning, comparison, decision support |
| `time_sensitive` | 8 | Fresh sources and explicit cutoff dates |
| `ambiguous_input` | 6 | Clarification before research |
| `conflicting_sources` | 6 | Balanced synthesis and uncertainty |
| `weak_evidence` | 5 | Insufficient-evidence behavior |
| `security` | 5 | Threat modeling and trustworthy controls |
| `memory` | 5 | Useful recall without evidence leakage |
| `literature_rag` | 5 | Retrieval from fixed indexed documents |

## Case contract

Every JSONL row contains:

- identity and query: `case_id`, `query`, `category`;
- routing labels: `requires_clarification`, `expected_initial_action`, `expected_outcome`;
- evaluation scope: `as_of_date`, `expected_dimensions`, `required_facts`, `known_conflicts`, `required_limitations`;
- at least three atomic `rubric_items`;
- `evidence_requirements`, including source count, freshness, primary-source, conflict, and citation expectations;
- `max_search_queries`, capped by the production budget of 20;
- `fixture_refs` for controlled Memory and RAG cases.

`expected_outcome=insufficient_evidence` means the system should not fabricate a supported report. `citation_required=false` is used only when the expected result is an evidence-insufficiency response with no usable source.

## Fixture use

Memory cases reference one record in `fixtures/memory/prior-research.jsonl` with `path#fixture_id`. Fixture seeding is not part of the current live MVP, so these cases should not yet be treated as controlled memory scores.

Literature RAG cases reference Markdown files under `fixtures/literature`. The live runner enables literature mode for these cases but does not ingest fixtures; controlled RAG scoring still requires a fixture-ingestion step.

Cases without fixtures are intended for live-web evaluation. Their factual grading must honor `as_of_date`, source requirements, and rubric items rather than compare report wording with a single reference answer.

## Live Agent evaluation

Live mode requires configured model and Tavily credentials and an explicit cost boundary:

```powershell
cd backend
.\.venv\Scripts\python.exe -m evals.run --mode live --case-id eval-001 --output "$env:TEMP/deep-research-live-eval.json"
```

Use repeated `--case-id`, `--limit N`, or the explicit `--all` flag. The runner executes cases sequentially and records the real terminal state, report, clarification, review verdict, event/task/query/source/evidence counts, citation validity, budget compliance, source requirement, and latency. Atomic rubric items are preserved as `not_scored`; the MVP does not claim semantic quality scores without a separate judge.

## Intended scoring layers

1. Deterministic: routing, budget compliance, citation-ID validity, recovery, and cost traces.
2. Retrieval: relevant-source or relevant-unit recall, MRR, and nDCG where labels exist.
3. Evidence: excerpt fidelity, claim support, citation correctness, and citation completeness.
4. Report: atomic rubric pass rate across coverage, analysis, decision quality, and limitations.
5. Reliability: repeated-run success, latency, token usage, search count, and score variance.

The dataset does not assign a synthetic overall score. A live runner should retain the layer scores and apply hard gates for fabricated identifiers, budget violations, and Memory-to-current-evidence leakage.
