from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deep_research.domain.evidence import Relevance, Source, SourceType
from deep_research.services.evidence_store import (
    build_evidence,
    build_source,
    canonicalize_url,
    merge_evidence_batches,
)


def test_canonicalize_url_removes_fragment_and_tracking_parameters() -> None:
    url = "https://Example.com/path/?utm_source=test&b=2&a=1#section"
    assert canonicalize_url(url) == "https://example.com/path?a=1&b=2"


def test_same_canonical_url_produces_same_source_id() -> None:
    retrieved_at = datetime(2026, 8, 26, tzinfo=UTC)
    first = build_source("https://example.com/a?utm_campaign=x", "A", "body", retrieved_at, SourceType.WEB)
    second = build_source("https://EXAMPLE.com/a#top", "A2", "body", retrieved_at, SourceType.WEB)
    assert first.source_id == second.source_id


@pytest.mark.parametrize(
    ("alias", "equivalent", "canonical"),
    [
        (
            "https://éxample.com/path",
            "https://xn--xample-9ua.com/path",
            "https://xn--xample-9ua.com/path",
        ),
        ("https://example.com./path", "https://example.com/path", "https://example.com/path"),
    ],
)
def test_host_aliases_have_one_canonical_url_and_source_id(
    alias: str,
    equivalent: str,
    canonical: str,
) -> None:
    retrieved_at = datetime(2026, 8, 26, tzinfo=UTC)

    first = build_source(alias, "Alias", "body", retrieved_at, SourceType.WEB)
    second = build_source(equivalent, "Equivalent", "body", retrieved_at, SourceType.WEB)

    assert canonicalize_url(alias) == canonical
    assert canonicalize_url(equivalent) == canonical
    assert first.source_id == second.source_id
    assert str(first.canonical_url).rstrip("/") == canonical


def test_evidence_id_is_stable_for_same_task_source_claim() -> None:
    first = build_evidence("task-1", "source-1", "A claim", "Exact excerpt", "Context", Relevance.HIGH, 1)
    second = build_evidence("task-1", "source-1", "A claim", "Exact excerpt", "Context", Relevance.HIGH, 1)
    assert first.evidence_id == second.evidence_id


def test_evidence_id_normalizes_claim_whitespace_and_case() -> None:
    first = build_evidence("task-1", "source-1", "  A   CLAIM ", "Exact excerpt", "Context", Relevance.HIGH, 1)
    second = build_evidence("task-1", "source-1", "a claim", "Other excerpt", "Other context", Relevance.LOW, 2)
    assert first.evidence_id == second.evidence_id


def test_merge_evidence_batches_is_keyed_by_evidence_id_and_later_batches_win() -> None:
    first = build_evidence("task-1", "source-1", "A claim", "first", "Context", Relevance.LOW, 1)
    second = build_evidence("task-1", "source-1", "A claim", "second", "Context", Relevance.HIGH, 2)
    other = build_evidence("task-1", "source-2", "Another claim", "excerpt", "Context", Relevance.MEDIUM, 1)

    merged = merge_evidence_batches({first.evidence_id: first}, {second.evidence_id: second, other.evidence_id: other})

    assert merged == {first.evidence_id: second, other.evidence_id: other}


def test_source_hashes_body_without_storing_raw_body() -> None:
    source = build_source(
        "https://example.com/a",
        "A",
        "secret raw body",
        datetime(2026, 8, 26, tzinfo=UTC),
        SourceType.WEB,
    )
    assert source.content_hash
    assert "secret raw body" not in source.model_dump_json()
    assert not hasattr(source, "body")


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "file:///tmp/file",
        "https://localhost/path",
        "https://127.0.0.1/path",
        "https://10.0.0.1/path",
        "https://192.168.1.5/path",
        "https://[::1]/path",
        "https://[fd00::1]/path",
        "https://0177.0.0.1/path",
        "https://127.1/path",
        "https://2130706433/path",
        "https://0x7f000001/path",
        "http://127。0。0。1/path",
        "http://%31%32%37.0.0.1/path",
        "https://user@example.com/path",
        "https://user:password@example.com/path",
        "https://0.0.0.0/path",
        "https://169.254.1.1/path",
        "https://224.0.0.1/path",
    ],
)
def test_canonicalize_url_rejects_unsafe_url_hosts_and_schemes(url: str) -> None:
    with pytest.raises(ValueError):
        canonicalize_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/path",
        "http://127。0。0。1/path",
        "http://%31%32%37.0.0.1/path",
        "https://user@example.com/path",
    ],
)
def test_source_validation_rejects_unsafe_url_even_when_constructed_directly(url: str) -> None:
    with pytest.raises(ValidationError):
        Source(
            source_id="src-1",
            url=url,
            canonical_url=url,
            title="A",
            domain="localhost",
            retrieved_at=datetime(2026, 8, 26, tzinfo=UTC),
            content_hash="hash",
            source_type=SourceType.WEB,
        )


@pytest.mark.parametrize(
    ("alias", "equivalent"),
    [
        ("https://éxample.com/path", "https://xn--xample-9ua.com/path"),
        ("https://example.com./path", "https://example.com/path"),
    ],
)
def test_source_direct_construction_normalizes_equivalent_authorities(
    alias: str,
    equivalent: str,
) -> None:
    def direct(url: str) -> Source:
        return Source(
            source_id="src-direct",
            url=url,
            canonical_url=url,
            title="A",
            domain="example.com",
            retrieved_at=datetime(2026, 8, 26, tzinfo=UTC),
            content_hash="hash",
            source_type=SourceType.WEB,
        )

    first = direct(alias)
    second = direct(equivalent)

    assert str(first.url) == str(second.url)
    assert str(first.canonical_url) == str(second.canonical_url)
