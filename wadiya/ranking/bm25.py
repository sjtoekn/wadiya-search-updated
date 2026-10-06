from __future__ import annotations

import re
from typing import Sequence

from .base import Ranker


class BM25Ranker(Ranker):
    """BM25 base ranking with small query/title relevance boosts.

    FTS5 remains responsible for candidate retrieval and field-weighted BM25.
    This layer adds query-aware title signals without changing Hit.score.
    """
    field_weights = {"title": 5.0, "headings": 3.0, "description": 2.0, "body": 1.0}

    _TOKEN = re.compile(r"[\w]+", re.UNICODE)

    @classmethod
    def _title_terms(cls, title: str) -> tuple[str, ...]:
        return tuple(
            t.casefold()
            for t in cls._TOKEN.findall(title or "")
            if t
        )

    @classmethod
    def _boost(cls, query, hit) -> float:
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

        return boost

    def rank(self, query, hits: Sequence) -> list:
        return sorted(
            hits,
            key=lambda h: (-h.score - self._boost(query, h), h.doc_id),
        )
