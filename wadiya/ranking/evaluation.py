from __future__ import annotations

from collections.abc import Iterable, Sequence


def precision_at_k(
    ranked_ids: Sequence[str],
    relevant_ids: Iterable[str],
    k: int,
) -> float:
    if k <= 0:
        return 0.0

    relevant = set(relevant_ids)
    top = ranked_ids[:k]
    return sum(doc_id in relevant for doc_id in top) / k


def mean_reciprocal_rank(
    ranked_lists: Sequence[Sequence[str]],
    relevant_sets: Sequence[Iterable[str]],
) -> float:
    if not ranked_lists:
        return 0.0

    total = 0.0
    for ranked_ids, relevant_ids in zip(ranked_lists, relevant_sets):
        relevant = set(relevant_ids)
        reciprocal = 0.0
        for rank, doc_id in enumerate(ranked_ids, 1):
            if doc_id in relevant:
                reciprocal = 1.0 / rank
                break
        total += reciprocal

    return total / len(ranked_lists)
