from __future__ import annotations

import pytest

from deep_research.auth.passwords import (
    Argon2PasswordHasher,
    InvalidPassword,
    validate_password,
)
from deep_research.auth.rate_limit import LoginRateLimiter


@pytest.mark.parametrize("length", [11, 129])
def test_password_policy_rejects_lengths_outside_the_approved_range(length: int) -> None:
    with pytest.raises(InvalidPassword):
        validate_password("x" * length)


@pytest.mark.parametrize("length", [12, 128])
def test_password_policy_accepts_the_range_boundaries(length: int) -> None:
    validate_password("x" * length)


def test_argon2id_hash_verifies_only_the_original_password() -> None:
    hasher = Argon2PasswordHasher()
    password = "a sufficiently long password"

    encoded = hasher.hash(password)

    assert encoded.startswith("$argon2id$")
    assert password not in encoded
    assert hasher.verify(encoded, password) is True
    assert hasher.verify(encoded, "a different password") is False


def test_login_limiter_keys_failures_by_ip_and_normalized_username() -> None:
    now = [100.0]
    limiter = LoginRateLimiter(max_attempts=5, window_seconds=900, clock=lambda: now[0])

    for _ in range(5):
        assert limiter.is_allowed("203.0.113.4", " Owner ") is True
        limiter.record_failure("203.0.113.4", " Owner ")

    assert limiter.is_allowed("203.0.113.4", "owner") is False
    assert limiter.is_allowed("203.0.113.5", "owner") is True

    limiter.clear("203.0.113.4", "OWNER")
    assert limiter.is_allowed("203.0.113.4", "owner") is True

    for _ in range(5):
        limiter.record_failure("203.0.113.4", "owner")
    now[0] += 901
    assert limiter.is_allowed("203.0.113.4", "owner") is True


def test_login_limiter_prunes_expired_keys_and_caps_tracked_identities() -> None:
    now = [100.0]
    limiter = LoginRateLimiter(
        max_attempts=5,
        window_seconds=900,
        max_keys=2,
        clock=lambda: now[0],
    )

    limiter.record_failure("203.0.113.1", "first")
    limiter.record_failure("203.0.113.2", "second")

    assert limiter.is_allowed("203.0.113.3", "third") is True
    limiter.record_failure("203.0.113.3", "third")
    assert len(limiter._failures) == 2
    assert ("203.0.113.1", "first") not in limiter._failures

    now[0] += 901
    assert limiter.is_allowed("203.0.113.4", "fourth") is True
    limiter.record_failure("203.0.113.4", "fourth")
    assert list(limiter._failures) == [("203.0.113.4", "fourth")]


def test_login_limiter_applies_an_ip_wide_limit_across_usernames() -> None:
    limiter = LoginRateLimiter(
        max_attempts=2,
        max_ip_attempts=2,
        window_seconds=900,
        clock=lambda: 0.0,
    )

    limiter.record_failure("203.0.113.8", "first")
    limiter.record_failure("203.0.113.8", "second")

    assert limiter.is_allowed("203.0.113.8", "owner") is False
    assert limiter.is_allowed("203.0.113.9", "owner") is True


def test_login_limiter_expires_the_requested_identity_at_the_exact_window() -> None:
    now = [0.0]
    limiter = LoginRateLimiter(max_attempts=1, window_seconds=900, clock=lambda: now[0])
    limiter.record_failure("203.0.113.8", "owner")

    now[0] = 899.0
    assert limiter.is_allowed("203.0.113.8", "owner") is False
    now[0] = 901.0
    assert limiter.is_allowed("203.0.113.8", "owner") is True
