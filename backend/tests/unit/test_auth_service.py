from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import cycle

import aiosqlite
import pytest

from deep_research.auth.rate_limit import LoginRateLimiter
from deep_research.auth.service import AuthService, InvalidCredentials, LoginRateLimited
from deep_research.persistence.auth_store import AuthStore, RegistrationClosed

NOW = datetime(2026, 9, 27, 3, 0, tzinfo=UTC)


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"hash:{password}"

    def verify(self, hash_value: str, password: str) -> bool:
        return hash_value == f"hash:{password}"


async def make_service(tmp_path, *, attempts: int = 5):
    store = AuthStore(tmp_path / "auth.sqlite")
    await store.initialize()
    now = [NOW]
    tokens = cycle(["raw-session-token", "csrf-token", "raw-token-2", "csrf-2"])
    service = AuthService(
        store,
        FakeHasher(),
        LoginRateLimiter(max_attempts=attempts, window_seconds=900, clock=lambda: 0.0),
        session_days=7,
        now=lambda: now[0],
        token_factory=lambda: next(tokens),
    )
    return service, store, now


@pytest.mark.asyncio
async def test_register_trims_username_and_never_persists_raw_token(tmp_path) -> None:
    service, store, _ = await make_service(tmp_path)

    issued = await service.register("  owner  ", "long enough password")

    assert issued.user.username == "owner"
    assert await service.authenticate(issued.raw_token) is not None
    async with aiosqlite.connect(store._database_path) as connection:
        values = await connection.execute_fetchall(
            "SELECT token_hash, csrf_token FROM auth_sessions"
        )
    assert values == [(service.hash_session_token("raw-session-token"), "csrf-token")]
    assert "raw-session-token" not in repr(values)
    with pytest.raises(RegistrationClosed):
        await service.register("another", "long enough password")


@pytest.mark.asyncio
async def test_login_uses_one_generic_error_and_enforces_failure_limit(tmp_path) -> None:
    service, _, _ = await make_service(tmp_path)
    await service.register("owner", "correct password")

    for username, password in [
        ("missing", "wrong password"),
        ("owner", "wrong password"),
    ]:
        with pytest.raises(InvalidCredentials, match="Invalid username or password"):
            await service.login(username, password, "203.0.113.8")

    for _ in range(4):
        with pytest.raises(InvalidCredentials):
            await service.login("owner", "wrong password", "203.0.113.8")
    with pytest.raises(LoginRateLimited):
        await service.login("OWNER", "wrong password", "203.0.113.8")


@pytest.mark.asyncio
async def test_successful_login_clears_failures_and_logout_revokes_session(tmp_path) -> None:
    service, _, _ = await make_service(tmp_path, attempts=2)
    await service.register("owner", "correct password")
    with pytest.raises(InvalidCredentials):
        await service.login("owner", "wrong password", "198.51.100.1")

    issued = await service.login("owner", "correct password", "198.51.100.1")
    assert await service.authenticate(issued.raw_token) is not None

    await service.logout(issued.raw_token)
    assert await service.authenticate(issued.raw_token) is None


@pytest.mark.asyncio
async def test_expiry_and_password_reset_revoke_sessions(tmp_path) -> None:
    service, store, now = await make_service(tmp_path)
    first = await service.register("owner", "correct password")
    second = await service.login("owner", "correct password", "192.0.2.1")

    now[0] += timedelta(days=8)
    assert await service.authenticate(first.raw_token) is None

    now[0] = NOW
    assert await service.authenticate(second.raw_token) is not None
    await service.reset_password("replacement password")

    assert await service.authenticate(second.raw_token) is None
    owner = await store.find_owner_by_username("owner")
    assert owner is not None
    assert owner.password_hash == "hash:replacement password"
