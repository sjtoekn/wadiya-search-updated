from __future__ import annotations

from typing import Sequence

from .base import Ranker


class BM25Ranker(Ranker):
    """Phase 0 ranking: FTS5's BM25 with per-field weights (applied at retrieval).
    Ties are broken deterministically by document id. Future signals (exact-title match,
    freshness, domain quality...) belong in a new Ranker, not in the indexer or API."""
    field_weights = {"title": 5.0, "headings": 3.0, "description": 2.0, "body": 1.0}

    def rank(self, query, hits: Sequence) -> list:
        return sorted(hits, key=lambda h: (-h.score, h.doc_id))
