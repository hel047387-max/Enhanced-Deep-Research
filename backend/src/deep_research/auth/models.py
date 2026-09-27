from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UserRecord:
    user_id: str
    username: str
    password_hash: str
    role: str
    created_at: datetime
    password_changed_at: datetime


@dataclass(frozen=True)
class SessionRecord:
    token_hash: str
    user_id: str
    csrf_token: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class AuthContext:
    user: UserRecord
    session: SessionRecord


@dataclass(frozen=True)
class IssuedSession:
    user: UserRecord
    raw_token: str
    csrf_token: str
    expires_at: datetime
