from __future__ import annotations

import ipaddress
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


def _parse_legacy_ipv4_literal(host: str) -> ipaddress.IPv4Address | None:
    """Parse IPv4 forms accepted by common HTTP client stacks."""
    components = host.rstrip(".").split(".")
    if not 1 <= len(components) <= 4 or any(not component for component in components):
        return None

    values: list[int] = []
    for component in components:
        if component.casefold().startswith("0x"):
            digits = component[2:]
            if not digits or any(character not in "0123456789abcdefABCDEF" for character in digits):
                return None
            base = 16
        elif len(component) > 1 and component.startswith("0"):
            if any(character not in "01234567" for character in component):
                return None
            digits = component
            base = 8
        else:
            if any(character not in "0123456789" for character in component):
                return None
            digits = component
            base = 10
        values.append(int(digits, base))

    limits_by_component_count = {
        1: (0xFFFFFFFF,),
        2: (0xFF, 0xFFFFFF),
        3: (0xFF, 0xFF, 0xFFFF),
        4: (0xFF, 0xFF, 0xFF, 0xFF),
    }
    limits = limits_by_component_count[len(values)]
    if any(value > limit for value, limit in zip(values, limits, strict=True)):
        return None
    if len(values) == 1:
        packed = values[0]
    elif len(values) == 2:
        packed = (values[0] << 24) | values[1]
    elif len(values) == 3:
        packed = (values[0] << 24) | (values[1] << 16) | values[2]
    else:
        packed = (values[0] << 24) | (values[1] << 16) | (values[2] << 8) | values[3]
    return ipaddress.IPv4Address(packed)


def validate_public_http_url(url: str) -> None:
    """Validate the URL policy that applies before any network access."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid URL") from exc

    if parsed.scheme.casefold() not in {"http", "https"}:
        raise ValueError("URL scheme must be HTTP or HTTPS")
    if not parsed.netloc or not host:
        raise ValueError("URL must include a host")

    normalized_host = host.casefold().rstrip(".")
    if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
        raise ValueError("localhost URLs are not allowed")

    literal_host = host.rstrip(".")
    try:
        address = ipaddress.ip_address(literal_host)
    except ValueError:
        address = _parse_legacy_ipv4_literal(literal_host)
    if address is not None and (address.is_loopback or address.is_private):
        raise ValueError("loopback and private literal IP hosts are not allowed")

    if port is not None and not 1 <= port <= 65535:
        raise ValueError("URL port is out of range")


class SourceType(StrEnum):
    WEB = "web"
    OFFICIAL = "official"
    NEWS = "news"


class Relevance(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Source(BaseModel, frozen=True):
    source_id: str
    url: AnyHttpUrl
    canonical_url: AnyHttpUrl
    title: str
    domain: str
    published_at: datetime | None = None
    retrieved_at: datetime
    content_hash: str
    source_type: SourceType

    @field_validator("url", "canonical_url", mode="before")
    @classmethod
    def validate_url(cls, value: AnyHttpUrl | str) -> AnyHttpUrl | str:
        validate_public_http_url(str(value))
        return value


class EvidenceItem(BaseModel, frozen=True):
    evidence_id: str
    task_id: str
    source_id: str
    claim: str = Field(min_length=1)
    excerpt: str = Field(min_length=1, max_length=1000)
    context: str = Field(min_length=1)
    relevance: Relevance
    discovered_in_round: int = Field(ge=1, le=2)
    citation_label: str
