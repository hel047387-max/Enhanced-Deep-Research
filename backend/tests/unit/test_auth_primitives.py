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
