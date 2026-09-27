from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deep_research.auth.__main__ import build_parser, reset_password_command
from deep_research.auth.rate_limit import LoginRateLimiter
from deep_research.auth.service import AuthService
from deep_research.persistence.auth_store import AuthStore


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"hash:{password}"

    def verify(self, hash_value: str, password: str) -> bool:
        return hash_value == f"hash:{password}"


@pytest.mark.asyncio
async def test_reset_password_cli_double_prompts_and_never_prints_password(
    tmp_path,
    capsys,
) -> None:
    store = AuthStore(tmp_path / "auth.sqlite")
    await store.initialize()
    service = AuthService(
        store,
        FakeHasher(),
        LoginRateLimiter(max_attempts=5, window_seconds=900),
        now=lambda: datetime(2026, 9, 27, tzinfo=UTC),
    )
    await service.register("owner", "original password")
    answers = iter(["replacement password", "replacement password"])

    await reset_password_command(service, prompt=lambda _: next(answers))

    output = capsys.readouterr().out
    assert "replacement password" not in output
    owner = await store.find_owner_by_username("owner")
    assert owner is not None
    assert owner.password_hash == "hash:replacement password"


def test_reset_password_cli_rejects_password_as_an_argument() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["reset-password", "secret-on-command-line"])
