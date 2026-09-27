from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

#不保存完整研究内容，只保存轻量的运行记录。

class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunMetadata(BaseModel, frozen=True):
    run_id: str
    thread_id: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None = None
    last_error: str | None = None
    memory_status: str | None = None
    memory_error: str | None = None


def _aiosqlite() -> Any:
    try:
        import aiosqlite
    except ImportError as exc:  # pragma: no cover - exercised only without extras
        raise RuntimeError(
            "Run metadata persistence requires 'aiosqlite'. Install the project "
            "runtime dependencies."
        ) from exc
    return aiosqlite


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _metadata(row: Any) -> RunMetadata:
    return RunMetadata(
        run_id=row["run_id"],
        thread_id=row["thread_id"],
        status=RunStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        cancelled_at=(
            datetime.fromisoformat(row["cancelled_at"])
            if row["cancelled_at"]
            else None
        ),
        last_error=row["last_error"],
        memory_status=row["memory_status"],
        memory_error=row["memory_error"],
    )


class RunStore:
    """SQLite repository for lightweight run lifecycle metadata."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sqlite = _aiosqlite()
        async with sqlite.connect(self.path) as connection:
            await connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_runs (
                    run_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    cancelled_at TEXT,
                    last_error TEXT,
                    memory_status TEXT,
                    memory_error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_research_runs_thread_updated
                ON research_runs(thread_id, updated_at DESC);
                """
            )
            cursor = await connection.execute("PRAGMA table_info(research_runs)")
            columns = {row[1] for row in await cursor.fetchall()}
            if "memory_status" not in columns:
                await connection.execute("ALTER TABLE research_runs ADD COLUMN memory_status TEXT")
            if "memory_error" not in columns:
                await connection.execute("ALTER TABLE research_runs ADD COLUMN memory_error TEXT")
            await connection.commit()

    async def create_run(self, run_id: str, thread_id: str) -> RunMetadata:
        timestamp = _utc_now()
        sqlite = _aiosqlite()
        async with sqlite.connect(self.path) as connection:
            await connection.execute(
                """
                INSERT INTO research_runs (
                    run_id, thread_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, thread_id, RunStatus.CREATED.value, timestamp, timestamp),
            )
            await connection.commit()
        created = await self.get_run(run_id)
        if created is None:  # pragma: no cover - SQLite insert contract
            raise RuntimeError("run metadata was not persisted")
        return created

    async def update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        last_error: str | None = None,
    ) -> RunMetadata:
        timestamp = _utc_now()
        cancelled_at = timestamp if status is RunStatus.CANCELLED else None
        sqlite = _aiosqlite()
        async with sqlite.connect(self.path) as connection:
            cursor = await connection.execute(
                """
                UPDATE research_runs
                SET status = ?, updated_at = ?, cancelled_at = ?, last_error = ?
                WHERE run_id = ?
                """,
                (status.value, timestamp, cancelled_at, last_error, run_id),
            )
            await connection.commit()
            if cursor.rowcount != 1:
                raise KeyError(f"unknown run_id: {run_id}")
        updated = await self.get_run(run_id)
        if updated is None:  # pragma: no cover - SQLite update contract
            raise RuntimeError("run metadata disappeared after update")
        return updated

    async def update_memory_status(
        self, run_id: str, status: str, error: str | None = None
    ) -> None:
        sqlite = _aiosqlite()
        async with sqlite.connect(self.path) as connection:
            await connection.execute(
                "UPDATE research_runs SET memory_status = ?, memory_error = ? WHERE run_id = ?",
                (status, error, run_id),
            )
            await connection.commit()

    async def list_unarchived_completed(self) -> list[RunMetadata]:
        sqlite = _aiosqlite()
        async with sqlite.connect(self.path) as connection:
            connection.row_factory = sqlite.Row
            cursor = await connection.execute(
                """SELECT * FROM research_runs
                   WHERE status = 'completed'
                     AND COALESCE(memory_status, 'pending') <> 'saved'
                   ORDER BY updated_at DESC"""
            )
            rows = await cursor.fetchall()
        return [_metadata(row) for row in rows]

    async def get_run(self, run_id: str) -> RunMetadata | None:
        return await self._fetch_one(
            "SELECT * FROM research_runs WHERE run_id = ?",
            (run_id,),
        )

    async def get_latest_for_thread(self, thread_id: str) -> RunMetadata | None:
        return await self._fetch_one(
            """
            SELECT * FROM research_runs
            WHERE thread_id = ?
            ORDER BY updated_at DESC, rowid DESC
            LIMIT 1
            """,
            (thread_id,),
        )
#执行一条带参数的 SQL 查询，读取第一行结果，将其转换成 RunMetadata；如果没查到则返回 None。
    async def _fetch_one(
        self,
        statement: str,
        parameters: tuple[str, ...],
    ) -> RunMetadata | None:
        sqlite = _aiosqlite()
        async with sqlite.connect(self.path) as connection:
            connection.row_factory = sqlite.Row
            cursor = await connection.execute(statement, parameters)
            row = await cursor.fetchone()
        return _metadata(row) if row is not None else None
