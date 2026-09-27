from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from deep_research.api.main import create_app
from deep_research.auth.passwords import Argon2PasswordHasher
from deep_research.auth.rate_limit import LoginRateLimiter
from deep_research.auth.service import AuthService
from deep_research.config import Settings
from deep_research.persistence.auth_store import AuthStore


async def build_auth_app(runtime, database: Path, *, secure: bool = False):
    store = AuthStore(database)
    await store.initialize()
    service = AuthService(
        store,
        Argon2PasswordHasher(),
        LoginRateLimiter(max_attempts=5, window_seconds=900),
    )
    settings = Settings(
        checkpoint_db_path=database,
        auth_cookie_secure=secure,
        auth_login_attempts=5,
        auth_login_window_seconds=900,
    )
    return create_app(runtime, settings=settings, auth_service=service), service


@pytest.fixture
async def auth_client(runtime_harness, tmp_path):
    app, service = await build_auth_app(
        runtime_harness.runtime,
        tmp_path / "auth-api.sqlite",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client, service


async def register(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "owner", "password": "correct password"},
    )
    assert response.status_code == 201
    body = response.json()
    assert "token" not in body
    return body["csrf_token"]


@pytest.mark.asyncio
async def test_status_registration_session_and_duplicate_registration(
    auth_client,
) -> None:
    client, _ = auth_client

    initial = await client.get("/api/v1/auth/status")
    csrf_token = await register(client)
    current = await client.get("/api/v1/auth/status")
    me = await client.get("/api/v1/auth/me")
    duplicate = await client.post(
        "/api/v1/auth/register",
        json={"username": "other", "password": "another password"},
    )

    assert initial.json() == {"registration_open": True, "authenticated": False}
    assert current.json() == {"registration_open": False, "authenticated": True}
    assert me.json() == {
        "user_id": me.json()["user_id"],
        "username": "owner",
        "role": "owner",
        "csrf_token": csrf_token,
    }
    assert duplicate.status_code == 403


@pytest.mark.asyncio
async def test_cookie_flags_for_local_and_secure_modes(
    runtime_harness, tmp_path
) -> None:
    local_app, _ = await build_auth_app(
        runtime_harness.runtime,
        tmp_path / "local.sqlite",
    )
    secure_app, _ = await build_auth_app(
        runtime_harness.runtime,
        tmp_path / "secure.sqlite",
        secure=True,
    )
    async with AsyncClient(
        transport=ASGITransport(app=local_app), base_url="http://test"
    ) as local_client:
        local = await local_client.post(
            "/api/v1/auth/register",
            json={"username": "owner", "password": "correct password"},
        )
    async with AsyncClient(
        transport=ASGITransport(app=secure_app), base_url="https://test"
    ) as secure_client:
        secure = await secure_client.post(
            "/api/v1/auth/register",
            json={"username": "owner", "password": "correct password"},
        )

    local_cookie = local.headers["set-cookie"]
    secure_cookie = secure.headers["set-cookie"]
    assert local_cookie.startswith("research_session_dev=")
    assert "HttpOnly" in local_cookie and "SameSite=lax" in local_cookie
    assert "Secure" not in local_cookie
    assert secure_cookie.startswith("__Host-research_session=")
    assert "HttpOnly" in secure_cookie and "Secure" in secure_cookie
    assert "Path=/" in secure_cookie


@pytest.mark.asyncio
async def test_login_error_is_generic_and_sixth_attempt_is_rate_limited(
    auth_client,
) -> None:
    client, _ = auth_client
    await register(client)
    client.cookies.clear()

    unknown = await client.post(
        "/api/v1/auth/login",
        json={"username": "missing", "password": "wrong password"},
    )
    wrong = await client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "wrong password"},
    )
    for _ in range(4):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "wrong password"},
        )
    limited = await client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "wrong password"},
    )

    assert unknown.status_code == wrong.status_code == response.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": "Invalid username or password."}
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "900"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("POST", "/api/v1/research/stream", {"json": {"query": "question"}}),
        (
            "POST",
            "/api/v1/research/thread/resume/stream",
            {"json": {"answer": "answer"}},
        ),
        ("GET", "/api/v1/research/thread", {}),
        ("GET", "/api/v1/research/thread/report", {}),
        ("POST", "/api/v1/research/thread/cancel", {}),
        ("GET", "/api/v1/memories/researches", {}),
        ("GET", "/api/v1/memories/search?q=topic", {}),
        ("GET", "/api/v1/memories/researches/thread", {}),
        ("GET", "/api/v1/literature/documents", {}),
        (
            "POST",
            "/api/v1/literature/documents",
            {"files": {"file": ("paper.pdf", b"%PDF")}},
        ),
        ("POST", "/api/v1/literature/search", {"json": {"query": "topic"}}),
        ("POST", "/api/v1/literature/answer", {"json": {"query": "topic"}}),
        ("DELETE", f"/api/v1/literature/documents/{UUID(int=0)}", {}),
    ],
)
async def test_all_business_routes_require_a_session(
    auth_client,
    method,
    path,
    kwargs,
) -> None:
    client, _ = auth_client

    response = await client.request(method, path, **kwargs)

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("POST", "/api/v1/research/stream", {"json": {"query": "question"}}),
        (
            "POST",
            "/api/v1/research/thread/resume/stream",
            {"json": {"answer": "answer"}},
        ),
        ("POST", "/api/v1/research/thread/cancel", {}),
        (
            "POST",
            "/api/v1/literature/documents",
            {"files": {"file": ("paper.pdf", b"%PDF")}},
        ),
        ("POST", "/api/v1/literature/search", {"json": {"query": "topic"}}),
        ("POST", "/api/v1/literature/answer", {"json": {"query": "topic"}}),
        ("DELETE", f"/api/v1/literature/documents/{UUID(int=0)}", {}),
        ("POST", "/api/v1/auth/logout", {}),
    ],
)
async def test_all_unsafe_authenticated_routes_require_matching_csrf(
    auth_client,
    method,
    path,
    kwargs,
) -> None:
    client, _ = auth_client
    await register(client)

    missing = await client.request(method, path, **kwargs)
    wrong = await client.request(
        method,
        path,
        headers={"X-CSRF-Token": "wrong"},
        **kwargs,
    )

    assert missing.status_code == wrong.status_code == 403


@pytest.mark.asyncio
async def test_logout_and_password_reset_revoke_old_cookie(auth_client) -> None:
    client, service = auth_client
    csrf_token = await register(client)

    logged_out = await client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    after_logout = await client.get("/api/v1/auth/me")
    assert logged_out.status_code == 204
    assert after_logout.status_code == 401

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "correct password"},
    )
    assert login.status_code == 200
    await service.reset_password("replacement password")
    after_reset = await client.get("/api/v1/auth/me")
    assert after_reset.status_code == 401


@pytest.mark.asyncio
async def test_health_and_auth_status_remain_public(auth_client) -> None:
    client, _ = auth_client

    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/api/v1/auth/status")).status_code == 200


@pytest.mark.asyncio
async def test_matching_csrf_allows_research_stream(auth_client) -> None:
    client, _ = auth_client
    csrf_token = await register(client)

    async with client.stream(
        "POST",
        "/api/v1/research/stream",
        headers={"X-CSRF-Token": csrf_token},
        json={"query": "A complete scoped question"},
    ) as response:
        lines = [
            line async for line in response.aiter_lines() if line.startswith("data: ")
        ]

    assert response.status_code == 200
    assert any('"type":"run_started"' in line for line in lines)
