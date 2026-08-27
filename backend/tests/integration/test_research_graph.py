import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("verdict", "expected_writer_calls", "expected_review_tasks"),
    [
        ("pass", 1, 0),
        ("revise", 2, 0),
        ("research_gap", 2, 1),
    ],
)
async def test_review_routes_are_bounded(
    graph_harness,
    verdict,
    expected_writer_calls,
    expected_review_tasks,
) -> None:
    result = await graph_harness.run(verdict=verdict)

    assert result["status"] == "completed"
    assert graph_harness.writer_calls == expected_writer_calls
    assert graph_harness.review_task_count == expected_review_tasks
    assert graph_harness.reviewer_calls == 1
    assert result["review_action_count"] <= 1
    assert "https://example.com/result" in result["final_report"]


@pytest.mark.asyncio
async def test_no_evidence_fails_without_writer_call(graph_harness) -> None:
    result = await graph_harness.run_without_evidence()

    assert result["status"] == "failed"
    assert graph_harness.writer_calls == 0


@pytest.mark.asyncio
async def test_reviewer_failure_preserves_and_finalizes_draft(graph_harness) -> None:
    result = await graph_harness.run_with_reviewer_failure()

    assert result["status"] == "completed"
    assert graph_harness.writer_calls == 1
    assert graph_harness.reviewer_calls == 1
    assert "Review incomplete" in result["final_report"]
    assert result["errors"][-1].error_code == "review_failed"
    assert "SECRET_REVIEW_TOKEN" not in str(result)


@pytest.mark.asyncio
async def test_zero_reviewer_task_budget_finalizes_with_limitation(
    graph_harness,
) -> None:
    result = await graph_harness.run_with_reviewer_task_budget(0)

    assert result["status"] == "completed"
    assert graph_harness.review_task_count == 0
    assert graph_harness.writer_calls == 1
    assert "Reviewer research was skipped" in result["final_report"]
