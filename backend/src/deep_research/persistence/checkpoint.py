from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any


@asynccontextmanager
async def checkpoint_context(path: str | Path) -> AsyncIterator[Any]:
    """Open and initialize one LangGraph SQLite checkpointer."""

    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    except ImportError as exc:  # pragma: no cover - exercised only without extras
        raise RuntimeError(
            "SQLite checkpoints require the 'langgraph-checkpoint-sqlite' and "
            "'aiosqlite' packages. Install the project runtime dependencies."
        ) from exc

    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(database_path)) as saver:
        await saver.setup()
        yield saver
