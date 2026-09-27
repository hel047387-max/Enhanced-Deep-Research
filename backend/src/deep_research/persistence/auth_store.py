from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite

from deep_research.auth.models import AuthContext, SessionRecord, UserRecord


class RegistrationClosed(RuntimeError):
    pass


class AuthStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def _connect(self) -> aiosqlite.Connection:
        connection = await aiosqlite.connect(self._database_path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        return connection

    async def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = await self._connect()
        try:
            await connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL UNIQUE CHECK (role = 'owner'),
                    created_at TEXT NOT NULL,
                    password_changed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_expiry
                ON auth_sessions(user_id, expires_at);
                """
            )
            await connection.commit()
        finally:
            await connection.close()

    async def registration_open(self) -> bool:
        connection = await self._connect()
        try:
            cursor = await connection.execute(
                "SELECT 1 FROM users WHERE role = 'owner' LIMIT 1"
            )
            return await cursor.fetchone() is None
        finally:
            await connection.close()

    async def create_owner(
        self,
        username: str,
        password_hash: str,
        now: datetime,
    ) -> UserRecord:
        user = UserRecord(
            user_id=str(uuid4()),
            username=username,
            password_hash=password_hash,
            role="owner",
            created_at=now,
            password_changed_at=now,
        )
        connection = await self._connect()
        try:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                await connection.execute(
                    """
                    INSERT INTO users (
                        user_id, username, password_hash, role,
                        created_at, password_changed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user.user_id,
                        user.username,
                        user.password_hash,
                        user.role,
                        user.created_at.isoformat(),
                        user.password_changed_at.isoformat(),
                    ),
                )
            except aiosqlite.IntegrityError as exc:
                await connection.rollback()
                raise RegistrationClosed("Owner registration is closed.") from exc
            await connection.commit()
            return user
        finally:
            await connection.close()

    async def find_owner_by_username(self, username: str) -> UserRecord | None:
        connection = await self._connect()
        try:
            cursor = await connection.execute(
                """
                SELECT user_id, username, password_hash, role,
                       created_at, password_changed_at
                FROM users
                WHERE role = 'owner' AND username = ?
                """,
                (username,),
            )
            row = await cursor.fetchone()
            return self._user(row) if row is not None else None
        finally:
            await connection.close()

    async def create_session(self, session: SessionRecord) -> None:
        connection = await self._connect()
        try:
            await connection.execute(
                """
                INSERT INTO auth_sessions (
                    token_hash, user_id, csrf_token,
                    created_at, expires_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.token_hash,
                    session.user_id,
                    session.csrf_token,
                    session.created_at.isoformat(),
                    session.expires_at.isoformat(),
                    session.last_seen_at.isoformat(),
                ),
            )
            await connection.commit()
        finally:
            await connection.close()

    async def resolve_session(
        self,
        token_hash: str,
        now: datetime,
    ) -> AuthContext | None:
        connection = await self._connect()
        try:
            cursor = await connection.execute(
                """
                SELECT
                    s.token_hash, s.user_id, s.csrf_token,
                    s.created_at AS session_created_at,
                    s.expires_at, s.last_seen_at,
                    u.username, u.password_hash, u.role,
                    u.created_at AS user_created_at,
                    u.password_changed_at
                FROM auth_sessions AS s
                JOIN users AS u ON u.user_id = s.user_id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at <= now:
                await connection.execute(
                    "DELETE FROM auth_sessions WHERE token_hash = ?",
                    (token_hash,),
                )
                await connection.commit()
                return None
            await connection.execute(
                "UPDATE auth_sessions SET last_seen_at = ? WHERE token_hash = ?",
                (now.isoformat(), token_hash),
            )
            await connection.commit()
            session = SessionRecord(
                token_hash=row["token_hash"],
                user_id=row["user_id"],
                csrf_token=row["csrf_token"],
                created_at=datetime.fromisoformat(row["session_created_at"]),
                expires_at=expires_at,
                last_seen_at=now,
            )
            user = UserRecord(
                user_id=row["user_id"],
                username=row["username"],
                password_hash=row["password_hash"],
                role=row["role"],
                created_at=datetime.fromisoformat(row["user_created_at"]),
                password_changed_at=datetime.fromisoformat(
                    row["password_changed_at"]
                ),
            )
            return AuthContext(user=user, session=session)
        finally:
            await connection.close()

    async def delete_session(self, token_hash: str) -> None:
        connection = await self._connect()
        try:
            await connection.execute(
                "DELETE FROM auth_sessions WHERE token_hash = ?",
                (token_hash,),
            )
            await connection.commit()
        finally:
            await connection.close()

    async def replace_owner_password(
        self,
        password_hash: str,
        changed_at: datetime,
    ) -> None:
        connection = await self._connect()
        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                UPDATE users
                SET password_hash = ?, password_changed_at = ?
                WHERE role = 'owner'
                """,
                (password_hash, changed_at.isoformat()),
            )
            if cursor.rowcount != 1:
                await connection.rollback()
                raise RuntimeError("Owner account does not exist.")
            await connection.execute("DELETE FROM auth_sessions")
            await connection.commit()
        finally:
            await connection.close()

    @staticmethod
    def _user(row: aiosqlite.Row) -> UserRecord:
        return UserRecord(
            user_id=row["user_id"],
            username=row["username"],
            password_hash=row["password_hash"],
            role=row["role"],
            created_at=datetime.fromisoformat(row["created_at"]),
            password_changed_at=datetime.fromisoformat(row["password_changed_at"]),
        )
