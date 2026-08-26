from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from deep_research.domain.evidence import (
    EvidenceItem,
    Relevance,
    Source,
    SourceType,
    validate_public_http_url,
)

_TRACKING_PARAMETERS = {"gclid", "fbclid"}


def canonicalize_url(url: str) -> str:
    """Return a deterministic public HTTP(S) URL representation."""
    validate_public_http_url(url)
    parsed = urlsplit(url)
    scheme = parsed.scheme.casefold()
    host = parsed.hostname
    if host is None:  # pragma: no cover - validate_public_http_url catches this
        raise ValueError("URL must include a host")

    host = host.casefold()
    if ":" in host:
        host = f"[{host}]"
    netloc = host
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo = f"{userinfo}:{parsed.password}"
        netloc = f"{userinfo}@{netloc}"

    path = parsed.path.rstrip("/")
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_PARAMETERS
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def _short_hash(value: str, prefix: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}"


def build_source(
    url: str,
    title: str,
    body: str,
    retrieved_at: datetime,
    source_type: SourceType,
    published_at: datetime | None = None,
) -> Source:
    canonical_url = canonicalize_url(url)
    host = urlsplit(canonical_url).hostname
    if host is None:  # pragma: no cover - canonicalize_url validates this
        raise ValueError("URL must include a host")
    return Source(
        source_id=_short_hash(canonical_url, "src-"),
        url=url,
        canonical_url=canonical_url,
        title=title,
        domain=host,
        published_at=published_at,
        retrieved_at=retrieved_at,
        content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        source_type=source_type,
    )


def build_evidence(
    task_id: str,
    source_id: str,
    claim: str,
    excerpt: str,
    context: str,
    relevance: Relevance,
    discovered_in_round: int,
) -> EvidenceItem:
    normalized_claim = " ".join(claim.split()).casefold()
    evidence_id = _short_hash(f"{task_id}|{source_id}|{normalized_claim}", "ev-")
    return EvidenceItem(
        evidence_id=evidence_id,
        task_id=task_id,
        source_id=source_id,
        claim=claim,
        excerpt=excerpt,
        context=context,
        relevance=relevance,
        discovered_in_round=discovered_in_round,
        citation_label=evidence_id.upper(),
    )


def merge_evidence_batches(*batches: Mapping[str, EvidenceItem]) -> dict[str, EvidenceItem]:
    merged: dict[str, EvidenceItem] = {}
    for batch in batches:
        merged.update(batch)
    return merged
