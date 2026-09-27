from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from deep_research.auth.models import (
    AuthContext,
    IssuedSession,
    SessionRecord,
    UserRecord,
)
from deep_research.auth.passwords import Argon2PasswordHasher, validate_password
from deep_research.auth.rate_limit import LoginRateLimiter
from deep_research.persistence.auth_store import AuthStore


class InvalidCredentials(ValueError):
    pass


class LoginRateLimited(RuntimeError):
    pass


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(
        self,
        store: AuthStore,
        password_hasher: Argon2PasswordHasher,
        rate_limiter: LoginRateLimiter,
        *,
        session_days: int = 7,
        now: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._store = store
        self._password_hasher = password_hasher
        self._rate_limiter = rate_limiter
        self._session_days = session_days
        self._now = now or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))

    @staticmethod
    def hash_session_token(raw_token: str) -> str:
        return hash_session_token(raw_token)

    async def registration_open(self) -> bool:
        return await self._store.registration_open()

    async def register(self, username: str, password: str) -> IssuedSession:
        normalized_username = self._validate_username(username)
        validate_password(password)
        user = await self._store.create_owner(
            normalized_username,
            self._password_hasher.hash(password),
            self._now(),
        )
        return await self._issue_session(user.user_id, user)

    async def login(
        self,
        username: str,
        password: str,
        client_ip: str,
    ) -> IssuedSession:
        normalized_username = self._validate_username(username)
        if not self._rate_limiter.is_allowed(client_ip, normalized_username):
            raise LoginRateLimited("Too many login attempts.")
        user = await self._store.find_owner_by_username(normalized_username)
        if user is None or not self._password_hasher.verify(
            user.password_hash,
            password,
        ):
            self._rate_limiter.record_failure(client_ip, normalized_username)
            raise InvalidCredentials("Invalid username or password.")
        self._rate_limiter.clear(client_ip, normalized_username)
        return await self._issue_session(user.user_id, user)

    async def authenticate(self, raw_token: str | None) -> AuthContext | None:
        if not raw_token:
            return None
        return await self._store.resolve_session(
            hash_session_token(raw_token),
            self._now(),
        )

    async def logout(self, raw_token: str | None) -> None:
        if raw_token:
            await self._store.delete_session(hash_session_token(raw_token))

    async def reset_password(self, new_password: str) -> None:
        validate_password(new_password)
        await self._store.replace_owner_password(
            self._password_hasher.hash(new_password),
            self._now(),
        )

    async def _issue_session(self, user_id: str, user: UserRecord) -> IssuedSession:
        now = self._now()
        expires_at = now + timedelta(days=self._session_days)
        raw_token = self._token_factory()
        csrf_token = self._token_factory()
        await self._store.create_session(
            SessionRecord(
                token_hash=hash_session_token(raw_token),
                user_id=user_id,
                csrf_token=csrf_token,
                created_at=now,
                expires_at=expires_at,
                last_seen_at=now,
            )
        )
        return IssuedSession(
            user=user,
            raw_token=raw_token,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )

    @staticmethod
    def _validate_username(username: str) -> str:
        normalized = username.strip()
        if not 1 <= len(normalized) <= 64:
            raise ValueError("Username must contain 1 to 64 characters.")
        return normalized
