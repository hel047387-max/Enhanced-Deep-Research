from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type


class InvalidPassword(ValueError):
    pass


def validate_password(password: str) -> None:
    if not 12 <= len(password) <= 128:
        raise InvalidPassword("Password must contain 12 to 128 characters.")


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._hasher = PasswordHasher(
            type=Type.ID,
            memory_cost=19_456,
            time_cost=2,
            parallelism=1,
            hash_len=32,
            salt_len=16,
        )

    def hash(self, password: str) -> str:
        validate_password(password)
        return self._hasher.hash(password)

    def verify(self, hash_value: str, password: str) -> bool:
        try:
            return self._hasher.verify(hash_value, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
