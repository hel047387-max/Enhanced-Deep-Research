from __future__ import annotations

import argparse
import asyncio
import getpass
from collections.abc import Callable, Sequence

from deep_research.auth.passwords import Argon2PasswordHasher
from deep_research.auth.rate_limit import LoginRateLimiter
from deep_research.auth.service import AuthService
from deep_research.config import Settings
from deep_research.persistence.auth_store import AuthStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m deep_research.auth")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("reset-password")
    return parser


async def reset_password_command(
    service: AuthService,
    *,
    prompt: Callable[[str], str] = getpass.getpass,
) -> None:
    password = prompt("New owner password: ")
    confirmation = prompt("Confirm new owner password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    await service.reset_password(password)
    print("Owner password reset; all sessions were revoked.")


async def _run(command: str) -> None:
    settings = Settings()
    store = AuthStore(settings.checkpoint_db_path)
    await store.initialize()
    service = AuthService(
        store,
        Argon2PasswordHasher(),
        LoginRateLimiter(
            max_attempts=settings.auth_login_attempts,
            window_seconds=settings.auth_login_window_seconds,
        ),
        session_days=settings.auth_session_days,
    )
    if command == "reset-password":
        await reset_password_command(service)


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    asyncio.run(_run(args.command))


if __name__ == "__main__":
    main()
