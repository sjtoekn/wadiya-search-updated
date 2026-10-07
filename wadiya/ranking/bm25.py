from __future__ import annotations

from datetime import datetime, timezone
from math import exp
from typing import Mapping, Sequence

from ..unicode_text import tokenize

from .base import Ranker


class BM25Ranker(Ranker):
    """BM25 base ranking with small query/title relevance boosts.

    FTS5 remains responsible for candidate retrieval and field-weighted BM25.
    This layer adds query-aware title signals without changing Hit.score.
    """
    field_weights = {"title": 5.0, "headings": 3.0, "description": 2.0, "body": 1.0}

    @classmethod
    def _title_terms(cls, title: str) -> tuple[str, ...]:
        return tuple(
            t.casefold()
            for t in tokenize(title or "")
            if t
        )

    @classmethod
    def _freshness_boost(cls, updated_at: str | None) -> float:
        if not updated_at:
            return 0.0
        try:
            value = updated_at.replace("Z", "+00:00")
            updated = datetime.fromisoformat(value)
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age_days = max(
                0.0,
                (datetime.now(timezone.utc) - updated.astimezone(timezone.utc)).total_seconds()
                / 86400.0,
            )
            return exp(-age_days / 30.0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _boost(cls, query, hit, document=None) -> float:
        title = (hit.title or "").casefold().strip()
        if not title:
            return 0.0

        title_terms = cls._title_terms(title)
        query_terms = tuple(
            t.casefold()
            for t in getattr(query, "terms", ())
            if t
        )

        boost = 0.0

        # Strongest signal: the whole normalized query is the title.
        normalized_query = (getattr(query, "normalized", "") or "").casefold().strip()
        if normalized_query and title == normalized_query:
            boost += 8.0

        # Strong signal: title begins with the complete query.
        if normalized_query and title.startswith(normalized_query + " "):
            boost += 4.0

        # Strong signal: every query term appears in the title.
        if query_terms:
            title_set = set(title_terms)
            if all(term in title_set for term in query_terms):
                boost += 3.0

        # Quoted phrase appearing in the title.
        for phrase in getattr(query, "phrases", ()):
            phrase_text = " ".join(phrase).casefold().strip()
            if phrase_text and phrase_text in title:
                boost += 5.0

        if document is not None:
            # Small freshness signal: exact relevance remains dominant.
            boost += 0.75 * cls._freshness_boost(
                getattr(document, "updated_at", None)
            )

        return boost

    def rank(
        self,
        query,
        hits: Sequence,
        documents: Mapping[int, object] | None = None,
    ) -> list:
        documents = documents or {}
        return sorted(
            hits,
            key=lambda h: (
                -h.score - self._boost(query, h, documents.get(h.doc_id)),
                h.doc_id,
            ),
        )
