from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from typing import Any

_OMITTED_KEYS = {"page_body", "raw_content"}
_REDACTED_KEYS = {"api_key", "authorization", "token"}


def redact_payload(payload: Any, *, secrets: AbstractSet[str] = frozenset()) -> Any:
    """Return a recursively sanitized copy of a provider-facing payload."""

    if isinstance(payload, Mapping):
        redacted: dict[Any, Any] = {}
        for key, value in payload.items():
            normalized_key = str(key).casefold()
            if normalized_key in _OMITTED_KEYS:
                redacted[key] = "[OMITTED]"
            elif normalized_key in _REDACTED_KEYS:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_payload(value, secrets=secrets)
        return redacted
    if isinstance(payload, list):
        return [redact_payload(value, secrets=secrets) for value in payload]
    if isinstance(payload, tuple):
        return tuple(redact_payload(value, secrets=secrets) for value in payload)
    if isinstance(payload, str):
        redacted_text = payload
        for secret in sorted(secrets, key=len, reverse=True):
            if secret:
                redacted_text = redacted_text.replace(secret, "[REDACTED]")
        return redacted_text
    return payload
