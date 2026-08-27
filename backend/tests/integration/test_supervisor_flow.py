import pytest


@pytest.mark.asyncio
async def test_supervisor_never_runs_more_than_three_workers(
    supervisor_harness,
) -> None:
    await supervisor_harness.run_with_tasks(5)

    assert supervisor_harness.peak_concurrency == 3


@pytest.mark.asyncio
async def test_supervisor_adds_only_one_generation_and_two_tasks(
    supervisor_harness,
) -> None:
    result = await supervisor_harness.run_with_coverage(additional_task_count=3)

    added = [task for task in result["tasks"].values() if task.parent_task_id]
    assert len(added) == 2
    assert result["coverage_checked"] is True
    assert supervisor_harness.coverage_calls == 1


@pytest.mark.asyncio
async def test_supervisor_reserves_global_query_capacity_before_parallel_dispatch(
    supervisor_harness,
) -> None:
    result = await supervisor_harness.run_with_tasks(5)

    assert sum(supervisor_harness.query_grants) == 20
    assert result["total_queries"] == 20
    assert max(supervisor_harness.query_grants) <= 4
