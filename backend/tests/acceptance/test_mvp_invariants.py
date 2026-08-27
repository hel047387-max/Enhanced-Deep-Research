import pytest

from tests.fakes import AcceptanceHarness


@pytest.fixture
def acceptance_harness() -> AcceptanceHarness:
    return AcceptanceHarness()


@pytest.mark.asyncio
async def test_complete_run_obeys_all_hard_limits(
    acceptance_harness: AcceptanceHarness,
) -> None:
    result = await acceptance_harness.run_complex_case()

    assert acceptance_harness.initial_task_count <= 5
    assert acceptance_harness.supervisor_task_count <= 2
    assert acceptance_harness.reviewer_task_count <= 1
    assert acceptance_harness.peak_concurrency <= 3
    assert acceptance_harness.total_queries <= 20
    assert max(acceptance_harness.rounds_by_task.values()) <= 2
    assert max(acceptance_harness.queries_by_round.values()) <= 2
    assert acceptance_harness.max_sources_per_task <= 8
    assert acceptance_harness.max_evidence_per_task <= 20
    assert acceptance_harness.reviewer_calls == 1
    assert result["status"] == "completed"
    assert acceptance_harness.invalid_citation_ids == []


@pytest.mark.asyncio
async def test_partial_failure_generates_named_limitation(
    acceptance_harness: AcceptanceHarness,
) -> None:
    result = await acceptance_harness.run_with_one_failed_task()

    assert result["status"] == "completed"
    assert result["tasks"]["task-2"].status == "failed"
    assert "failed task task-2" in result["final_report"].lower()
    assert result["evidence"]


@pytest.mark.asyncio
async def test_zero_evidence_fails_without_report(
    acceptance_harness: AcceptanceHarness,
) -> None:
    result = await acceptance_harness.run_with_zero_evidence()

    assert result["status"] == "failed"
    assert not result.get("final_report")
    assert acceptance_harness.writer_calls == 0


@pytest.mark.asyncio
async def test_cancel_prevents_later_nodes(
    acceptance_harness: AcceptanceHarness,
) -> None:
    result = await acceptance_harness.cancel_after_first_search()

    assert result["status"] == "cancelled"
    assert acceptance_harness.total_queries >= 1
    assert acceptance_harness.writer_calls == 0
    assert acceptance_harness.reviewer_calls == 0
