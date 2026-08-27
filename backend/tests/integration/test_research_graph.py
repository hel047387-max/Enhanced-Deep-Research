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
