import pytest


@pytest.mark.asyncio
async def test_researcher_runs_second_round_only_for_actionable_gap(
    researcher_factory, partial_gap, sufficient_gap
) -> None:
    researcher = researcher_factory(gaps=[partial_gap, sufficient_gap])

    output = await researcher.ainvoke(
        {"task": researcher.task, "research_brief": researcher.brief}
    )

    assert output["updated_task"].current_round == 2
    assert output["updated_task"].status.value == "completed"
    assert researcher.search.queries == ["initial query", "targeted query"]
    assert output["queries_used"] == 2


@pytest.mark.asyncio
async def test_researcher_stops_at_global_query_cap(
    researcher_factory, partial_gap
) -> None:
    researcher = researcher_factory(gaps=[partial_gap], total_queries=20)

    output = await researcher.ainvoke(
        {"task": researcher.task, "research_brief": researcher.brief}
    )

    assert output["updated_task"].status.value == "insufficient"
    assert researcher.search.queries == []
    assert output["queries_used"] == 0


@pytest.mark.asyncio
async def test_researcher_returns_normalized_state_without_raw_pages(
    researcher_factory, sufficient_gap
) -> None:
    researcher = researcher_factory(gaps=[sufficient_gap])

    output = await researcher.ainvoke(
        {"task": researcher.task, "research_brief": researcher.brief}
    )

    assert "raw_results" not in output
    assert "queries" not in output
    assert all(key == source.source_id for key, source in output["sources"].items())
    assert all(item.task_id == "task-1" for item in output["evidence"].values())
