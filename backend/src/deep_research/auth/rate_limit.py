from __future__ import annotations

import time
from collections.abc import Callable


class LoginRateLimiter:
    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._clock = clock
        self._failures: dict[tuple[str, str], list[float]] = {}

    @staticmethod
    def _key(client_ip: str, username: str) -> tuple[str, str]:
        return client_ip, username.strip().casefold()

    def _active_failures(self, key: tuple[str, str]) -> list[float]:
        cutoff = self._clock() - self._window_seconds
        active = [timestamp for timestamp in self._failures.get(key, []) if timestamp > cutoff]
        if active:
            self._failures[key] = active
        else:
            self._failures.pop(key, None)
        return active

    def is_allowed(self, client_ip: str, username: str) -> bool:
        return len(self._active_failures(self._key(client_ip, username))) < self._max_attempts

    def record_failure(self, client_ip: str, username: str) -> None:
        key = self._key(client_ip, username)
        active = self._active_failures(key)
        active.append(self._clock())
        self._failures[key] = active

    def clear(self, client_ip: str, username: str) -> None:
        self._failures.pop(self._key(client_ip, username), None)
