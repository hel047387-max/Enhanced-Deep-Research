from __future__ import annotations

import ipaddress
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


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

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
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
