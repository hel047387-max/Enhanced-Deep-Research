from collections.abc import Collection, Mapping, Sequence
from collections.abc import Set as AbstractSet
from itertools import combinations
from typing import Protocol


def citation_validity(
    *,
    used_ids: AbstractSet[str],
    known_ids: AbstractSet[str],
) -> float:
    """Return the fraction of cited Evidence IDs that can be resolved."""

    if not used_ids:
        return 1.0
    return len(used_ids & known_ids) / len(used_ids)


def task_overlap(tasks: Sequence[Collection[str]]) -> float:
    """Return the fraction of task pairs with identical normalized query sets."""

    normalized = [
        frozenset(query.strip().casefold() for query in queries if query.strip())
        for queries in tasks
    ]
    pairs = list(combinations(normalized, 2))
    if not pairs:
        return 0.0
    return sum(left == right for left, right in pairs) / len(pairs)


def dimension_coverage(
    observed: AbstractSet[str],
    expected: AbstractSet[str],
) -> float:
    """Return the fraction of expected dimensions represented in an output."""

    if not expected:
        return 1.0
    return len(observed & expected) / len(expected)


def budget_compliance(
    observed: Mapping[str, int],
    limits: Mapping[str, int],
) -> float:
    """Return 1 when every observed counter is within its configured limit."""

    compliant = all(0 <= observed.get(name, 0) <= limit for name, limit in limits.items())
    return float(compliant)


class OptionalJudge(Protocol):
    """Optional versioned judge boundary; default evaluation never requires it."""

    name: str

    def score(self, query: str, report: str) -> Mapping[str, float]: ...
