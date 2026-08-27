from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any


@asynccontextmanager
async def checkpoint_context(path: str | Path) -> AsyncIterator[Any]:
    """Open and initialize one LangGraph SQLite checkpointer."""

    try:
        import aiosqlite
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    except ImportError as exc:  # pragma: no cover - exercised only without extras
        raise RuntimeError(
            "SQLite checkpoints require the 'langgraph-checkpoint-sqlite' and "
            "'aiosqlite' packages. Install the project runtime dependencies."
        ) from exc

    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(database_path)) as connection:
        saver = AsyncSqliteSaver(
            connection,
            serde=JsonPlusSerializer(pickle_fallback=True),
        )
        await saver.setup()
        yield saver
