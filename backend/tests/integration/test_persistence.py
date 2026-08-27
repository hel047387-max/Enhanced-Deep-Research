from pathlib import Path

import pytest

from deep_research.persistence.run_store import RunStatus, RunStore


@pytest.mark.asyncio
async def test_run_store_persists_status_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "research.sqlite"
    first = RunStore(db)
    await first.initialize()
    await first.create_run("run-1", "thread-1")
    await first.update_status("run-1", RunStatus.WAITING_FOR_USER)

    second = RunStore(db)
    await second.initialize()
    restored = await second.get_run("run-1")

    assert restored is not None
    assert restored.status is RunStatus.WAITING_FOR_USER


@pytest.mark.asyncio
async def test_latest_run_is_selected_by_updated_time(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "research.sqlite")
    await store.initialize()
    await store.create_run("run-1", "thread-1")
    await store.create_run("run-2", "thread-1")

    latest = await store.get_latest_for_thread("thread-1")

    assert latest is not None
    assert latest.run_id == "run-2"
