from collections.abc import Mapping
from datetime import UTC
from typing import TypeVar

from deep_research.domain.errors import ResearchError
from deep_research.domain.evidence import Source
from deep_research.services.evidence_store import (
    canonicalize_url,
    source_id_from_canonical_url,
)

K = TypeVar("K")
V = TypeVar("V")


def merge_mapping(left: Mapping[K, V] | None, right: Mapping[K, V] | None) -> dict[K, V]:
    """Return a last-write-wins merge without mutating either input mapping."""
    return {**(left or {}), **(right or {})}


merge_tasks = merge_mapping
merge_evidence = merge_mapping
merge_gap_assessments = merge_mapping


def _validated_source_entries(
    sources: Mapping[str, Source] | None,
) -> list[tuple[str, Source]]:
    entries: list[tuple[str, Source]] = []
    for key, source in (sources or {}).items():
        if key != source.source_id:
            raise ValueError(f"source mapping key {key!r} does not match source_id {source.source_id!r}")
        canonical_url = canonicalize_url(str(source.canonical_url))
        expected_source_id = source_id_from_canonical_url(canonical_url)
        if source.source_id != expected_source_id:
            raise ValueError(
                f"source_id {source.source_id!r} is not derived from canonical URL {canonical_url!r}"
            )
        entries.append((key, source))
    return entries


def _source_conflict_key(source: Source) -> tuple[tuple[int, str], str]:
    retrieved_at = source.retrieved_at
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        timestamp_key = (0, retrieved_at.isoformat(timespec="microseconds"))
    else:
        timestamp_key = (1, retrieved_at.astimezone(UTC).isoformat(timespec="microseconds"))
    return timestamp_key, source.model_dump_json()


def merge_sources(
    left: Mapping[str, Source] | None,
    right: Mapping[str, Source] | None,
) -> dict[str, Source]:
    """Merge canonical sources commutatively without mixing source snapshots."""
    merged: dict[str, Source] = {}
    for source_id, source in [*_validated_source_entries(left), *_validated_source_entries(right)]:
        existing = merged.get(source_id)
        if existing is None or _source_conflict_key(source) > _source_conflict_key(existing):
            merged[source_id] = source
    return {source_id: merged[source_id] for source_id in sorted(merged)}


def append_errors(
    left: list[ResearchError] | None,
    right: list[ResearchError] | None,
) -> list[ResearchError]:
    """Append error patches while leaving both source lists unchanged."""
    return [*(left or []), *(right or [])]
