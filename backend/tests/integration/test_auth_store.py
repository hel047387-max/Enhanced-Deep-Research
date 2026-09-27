from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from deep_research.auth.models import SessionRecord
from deep_research.persistence.auth_store import AuthStore, RegistrationClosed

NOW = datetime(2026, 9, 27, 2, 30, tzinfo=UTC)


async def owner(store: AuthStore, username: str = "owner"):
    return await store.create_owner(username, "argon-hash", NOW)


@pytest.mark.asyncio
async def test_initialize_adds_auth_schema_without_touching_business_data(tmp_path) -> None:
    database = tmp_path / "app.sqlite"
    async with aiosqlite.connect(database) as connection:
        await connection.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
        await connection.execute("INSERT INTO sentinel(value) VALUES ('kept')")
        await connection.commit()

    store = AuthStore(database)
    await store.initialize()

    async with aiosqlite.connect(database) as connection:
        tables = {
            row[0]
            for row in await connection.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        indexes = {
            row[0]
            for row in await connection.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        sentinel = await connection.execute_fetchall("SELECT value FROM sentinel")

    assert {"users", "auth_sessions"}.issubset(tables)
    assert "idx_auth_sessions_user_expiry" in indexes
    assert sentinel == [("kept",)]


@pytest.mark.asyncio
async def test_concurrent_first_owner_creation_has_one_winner(tmp_path) -> None:
    store = AuthStore(tmp_path / "app.sqlite")
    await store.initialize()

    results = await asyncio.gather(
        store.create_owner("first", "hash-1", NOW),
        store.create_owner("second", "hash-2", NOW),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, RegistrationClosed) for result in results) == 1
    assert await store.registration_open() is False


@pytest.mark.asyncio
async def test_session_resolution_stores_only_hash_and_removes_expired_rows(tmp_path) -> None:
    database = tmp_path / "app.sqlite"
    store = AuthStore(database)
    await store.initialize()
    user = await owner(store)
    valid = SessionRecord(
        token_hash="hashed-valid-token",
        user_id=user.user_id,
        csrf_token="csrf",
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
        last_seen_at=NOW,
    )
    expired = SessionRecord(
        token_hash="hashed-expired-token",
        user_id=user.user_id,
        csrf_token="old-csrf",
        created_at=NOW - timedelta(days=8),
        expires_at=NOW - timedelta(days=1),
        last_seen_at=NOW - timedelta(days=8),
    )
    await store.create_session(valid)
    await store.create_session(expired)

    context = await store.resolve_session(valid.token_hash, NOW + timedelta(minutes=1))
    missing = await store.resolve_session(expired.token_hash, NOW)

    assert context is not None
    assert context.user.username == "owner"
    assert context.session.token_hash == valid.token_hash
    assert context.session.expires_at == valid.expires_at
    assert missing is None
    async with aiosqlite.connect(database) as connection:
        stored = await connection.execute_fetchall(
            "SELECT token_hash FROM auth_sessions ORDER BY token_hash"
        )
    assert stored == [("hashed-valid-token",)]
    assert all("raw" not in value for (value,) in stored)


@pytest.mark.asyncio
async def test_logout_and_password_replacement_revoke_expected_sessions(tmp_path) -> None:
    store = AuthStore(tmp_path / "app.sqlite")
    await store.initialize()
    user = await owner(store)
    for token in ("one", "two"):
        await store.create_session(
            SessionRecord(
                token_hash=token,
                user_id=user.user_id,
                csrf_token=f"csrf-{token}",
                created_at=NOW,
                expires_at=NOW + timedelta(days=7),
                last_seen_at=NOW,
            )
        )

    await store.delete_session("one")
    assert await store.resolve_session("one", NOW) is None
    assert await store.resolve_session("two", NOW) is not None

    await store.replace_owner_password("new-hash", NOW + timedelta(hours=1))

    updated = await store.find_owner_by_username("owner")
    assert updated is not None
    assert updated.password_hash == "new-hash"
    assert await store.resolve_session("two", NOW) is None


@pytest.mark.asyncio
async def test_foreign_keys_cascade_owner_deletion_to_sessions(tmp_path) -> None:
    database = tmp_path / "app.sqlite"
    store = AuthStore(database)
    await store.initialize()
    user = await owner(store)
    await store.create_session(
        SessionRecord(
            token_hash="session",
            user_id=user.user_id,
            csrf_token="csrf",
            created_at=NOW,
            expires_at=NOW + timedelta(days=7),
            last_seen_at=NOW,
        )
    )

    async with aiosqlite.connect(database) as connection:
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("DELETE FROM users WHERE user_id = ?", (user.user_id,))
        await connection.commit()
        sessions = await connection.execute_fetchall("SELECT token_hash FROM auth_sessions")

    assert sessions == []
