from collections.abc import Iterable
from ipaddress import ip_address

from deep_research.domain.evidence import (
    validate_public_http_url as normalize_public_http_url,
)

#防止访问危险url

class UnsafeUrlError(ValueError):
    """Raised when a URL or its resolved address is unsafe to request."""


def validate_public_http_url(
    url: str,
    *,#只能用关键字参数导入
    resolved_ips: Iterable[str] = (),
) -> str:
    """Apply canonical URL validation and reject unsafe DNS results."""

    try:
        normalized = normalize_public_http_url(url)
    except ValueError as exc:
        raise UnsafeUrlError(str(exc)) from exc

    for value in resolved_ips:
        try:
            address = ip_address(value)
        except ValueError as exc:
            raise UnsafeUrlError("DNS returned an invalid address") from exc
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
            or not address.is_global
        ):
            raise UnsafeUrlError("DNS must resolve only to a public address")
    return normalized
