from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from typing import TypeVar

Key = TypeVar("Key")


class LoginRateLimiter:
    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: int,
        max_keys: int = 10_000,
        max_ip_attempts: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._max_keys = max_keys
        self._max_ip_attempts = max_ip_attempts or max_attempts * 5
        self._clock = clock
        self._next_prune_at = 0.0
        self._failures: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        self._ip_failures: OrderedDict[str, list[float]] = OrderedDict()

    @staticmethod
    def _key(client_ip: str, username: str) -> tuple[str, str]:
        return client_ip, username.strip().casefold()

    def _active(
        self,
        failures: OrderedDict[Key, list[float]],
        key: Key,
        now: float,
    ) -> list[float]:
        cutoff = now - self._window_seconds
        active = [timestamp for timestamp in failures.get(key, ()) if timestamp > cutoff]
        if active:
            failures[key] = active
            failures.move_to_end(key)
        else:
            failures.pop(key, None)
        return active

    def _prune_expired(self, now: float) -> None:
        if now < self._next_prune_at:
            return
        cutoff = now - self._window_seconds
        for failures in (self._failures, self._ip_failures):
            for key, timestamps in list(failures.items()):
                active = [timestamp for timestamp in timestamps if timestamp > cutoff]
                if active:
                    failures[key] = active
                else:
                    del failures[key]
        self._next_prune_at = now + min(self._window_seconds, 60)

    def _record(
        self,
        failures: OrderedDict[Key, list[float]],
        key: Key,
        now: float,
        limit: int,
    ) -> None:
        active = self._active(failures, key, now)
        active.append(now)
        failures[key] = active[-limit:]
        failures.move_to_end(key)
        while len(failures) > self._max_keys:
            failures.popitem(last=False)

    def is_allowed(self, client_ip: str, username: str) -> bool:
        now = self._clock()
        self._prune_expired(now)
        identity_failures = self._active(
            self._failures,
            self._key(client_ip, username),
            now,
        )
        ip_failures = self._active(self._ip_failures, client_ip, now)
        return (
            len(identity_failures) < self._max_attempts
            and len(ip_failures) < self._max_ip_attempts
        )

    def record_failure(self, client_ip: str, username: str) -> None:
        now = self._clock()
        self._prune_expired(now)
        self._record(
            self._failures,
            self._key(client_ip, username),
            now,
            self._max_attempts,
        )
        self._record(
            self._ip_failures,
            client_ip,
            now,
            self._max_ip_attempts,
        )

    def clear(self, client_ip: str, username: str) -> None:
        self._failures.pop(self._key(client_ip, username), None)
        self._ip_failures.pop(client_ip, None)
