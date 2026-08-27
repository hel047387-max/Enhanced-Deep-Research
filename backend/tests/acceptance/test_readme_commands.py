from pathlib import Path

_ROOT = Path(__file__).parents[3]


def test_readme_contains_verified_commands_and_boundaries() -> None:
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    required = [
        "pytest tests/unit tests/integration tests/acceptance -q",
        "ruff check src tests evals",
        "python -m evals.run --mode fake",
        "npm run test:run",
        "npm run build",
        "MAX_TOTAL_SEARCH_QUERIES=20",
        "SSE history replay is not supported",
        "single FastAPI instance",
        "Live evaluation incurs provider cost",
        "What I redesigned",
    ]

    assert all(item in readme for item in required)


def test_environment_example_lists_all_server_owned_budgets() -> None:
    example = (_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "MAX_INITIAL_TASKS=5" in example
    assert "MAX_SUPERVISOR_TASKS=2" in example
    assert "MAX_REVIEWER_TASKS=1" in example
    assert "MAX_RESEARCH_ROUNDS=2" in example
    assert "MAX_QUERIES_PER_ROUND=2" in example
    assert "MAX_CONCURRENT_RESEARCHERS=3" in example
    assert "MAX_TOTAL_SEARCH_QUERIES=20" in example
    assert "MAX_SOURCES_PER_TASK=8" in example
    assert "MAX_EVIDENCE_PER_TASK=20" in example
