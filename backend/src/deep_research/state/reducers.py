from collections.abc import Mapping
from typing import TypeVar

from deep_research.domain.errors import ResearchError

K = TypeVar("K")
V = TypeVar("V")


def merge_mapping(left: Mapping[K, V] | None, right: Mapping[K, V] | None) -> dict[K, V]:
    """Return a last-write-wins merge without mutating either input mapping."""
    return {**(left or {}), **(right or {})}


merge_tasks = merge_mapping
merge_sources = merge_mapping
merge_evidence = merge_mapping
merge_gap_assessments = merge_mapping


def append_errors(
    left: list[ResearchError] | None,
    right: list[ResearchError] | None,
) -> list[ResearchError]:
    """Append error patches while leaving both source lists unchanged."""
    return [*(left or []), *(right or [])]
