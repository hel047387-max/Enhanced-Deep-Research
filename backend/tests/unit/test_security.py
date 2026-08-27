import asyncio

import pytest

from deep_research.security.redaction import redact_payload
from deep_research.security.urls import UnsafeUrlError, validate_public_http_url
from deep_research.services.retry import retry_async


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/admin",
        "http://127.0.0.1/private",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.2/internal",
        "http://192.168.1.10/internal",
    ],
)
def test_private_and_non_http_urls_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_public_http_url(url, resolved_ips=[])


def test_dns_resolution_cannot_rebind_public_hostname_to_private_ip() -> None:
    with pytest.raises(UnsafeUrlError, match="public address"):
        validate_public_http_url(
            "https://public.example/research",
            resolved_ips=["93.184.216.34", "10.0.0.8"],
        )


def test_public_url_uses_canonical_normalizer_and_allows_public_dns_result() -> None:
    assert validate_public_http_url(
        "HTTPS://ExAmPle.COM.:443/a",
        resolved_ips=["93.184.216.34"],
    ) == "https://example.com:443/a"


def test_nested_payload_redacts_known_secrets_and_raw_content() -> None:
    payload = {
        "token": "secret-value",
        "nested": {
            "raw_content": "full page",
            "message": "prefix secret-value suffix",
            "items": [{"authorization": "Bearer hidden"}],
        },
    }

    assert redact_payload(payload, secrets={"secret-value"}) == {
        "token": "[REDACTED]",
        "nested": {
            "raw_content": "[OMITTED]",
            "message": "prefix [REDACTED] suffix",
            "items": [{"authorization": "[REDACTED]"}],
        },
    }


@pytest.mark.asyncio
async def test_retry_stops_after_two_retries() -> None:
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("provider timeout")

    with pytest.raises(TimeoutError, match="provider timeout"):
        await retry_async(operation, retries=2, base_delay_seconds=0)

    assert attempts == 3


@pytest.mark.asyncio
async def test_retry_uses_exponential_delays_and_ignores_non_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []
    attempts = 0

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    async def transient_operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("retry")
        return "ok"

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    assert await retry_async(
        transient_operation,
        retries=2,
        base_delay_seconds=0.25,
    ) == "ok"
    assert delays == [0.25, 0.5]

    async def invalid_operation() -> str:
        raise ValueError("invalid")

    with pytest.raises(ValueError, match="invalid"):
        await retry_async(invalid_operation, retries=2, base_delay_seconds=0)
