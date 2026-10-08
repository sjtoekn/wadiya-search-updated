"""Search orchestration: parse -> retrieve -> rank -> hydrate -> snippet. No crawling, no SQL."""
from __future__ import annotations

import random

import math
import time

from ..indexer.base import Indexer
from ..query.parser import QueryError, parse_query
from ..ranking.base import Ranker
from ..storage.base import Storage
from .books import BooksProvider, StaticBooksProvider
from .snippets import make_snippet


class InvalidSearchRequest(ValueError):
    pass


class SearchService:
    def __init__(
        self,
        settings,
        storage: Storage,
        indexer: Indexer,
        ranker: Ranker,
        books_provider: BooksProvider | None = None,
    ):
        self.s, self.storage, self.indexer, self.ranker = settings, storage, indexer, ranker
        self.books_provider = books_provider or StaticBooksProvider()

    def search_books(self, raw_query, page: int = 1) -> dict:
        """Search Books through the configured Books provider."""
        t0 = time.perf_counter()

        if not isinstance(raw_query, str):
            raise InvalidSearchRequest("query must be a string")

        raw = raw_query.strip()
        if not raw:
            raise InvalidSearchRequest("query is required")

        try:
            q = parse_query(raw, self.s.max_query_length, self.s.max_query_terms)
        except QueryError as e:
            raise InvalidSearchRequest(str(e))

        if not isinstance(page, int) or page < 1 or page > self.s.max_pages:
            raise InvalidSearchRequest(f"page must be between 1 and {self.s.max_pages}")

        window = self.s.page_size * self.s.max_pages
        rows = self.books_provider.search(
            q.raw.strip(),
            limit=window,
            offset=0,
        )

        start = (page - 1) * self.s.page_size
        page_rows = rows[start:start + self.s.page_size]

        results = [
            {
                "title": book.title,
                "author": list(book.author),
                "isbn": book.isbn,
                "cover_url": book.cover_url,
                "publisher": book.publisher,
                "published_at": book.published_at,
                "description": book.description,
                "url": book.url,
                "language": book.language,
                "score": book.score,
            }
            for book in page_rows
        ]

        latency = round((time.perf_counter() - t0) * 1000, 2)

        return {
            "query": raw,
            "page": page,
            "page_size": self.s.page_size,
            "total_pages": math.ceil(len(rows) / self.s.page_size),
            "result_count": len(rows),
            "result_count_exact": len(rows) < window,
            "latency_ms": latency,
            "results": results,
        }

    def search_images(self, raw_query, page: int = 1) -> dict:
        """Search persisted page images without changing the normal web-search path."""
        t0 = time.perf_counter()

        if not isinstance(raw_query, str):
            raise InvalidSearchRequest("query must be a string")

        raw = raw_query.strip()
        if not raw:
            raise InvalidSearchRequest("query is required")

        try:
            q = parse_query(raw, self.s.max_query_length, self.s.max_query_terms)
        except QueryError as e:
            raise InvalidSearchRequest(str(e))

        if not isinstance(page, int) or page < 1 or page > self.s.max_pages:
            raise InvalidSearchRequest(f"page must be between 1 and {self.s.max_pages}")

        # Image search currently uses the literal user query against image/page
        # metadata. This deliberately does not reuse FTS ranking.
        window = self.s.page_size * self.s.max_pages
        rows = self.storage.search_images(
            q.raw.strip(),
            limit=window,
            offset=0,
        )

        start = (page - 1) * self.s.page_size
        page_rows = rows[start:start + self.s.page_size]

        results = [
            {
                "image_url": row["image_url"],
                "source_page_url": row["source_page_url"],
                "source_domain": row["source_domain"],
                "alt_text": row["alt_text"],
                "title": row["title"] or row["page_title"] or row["source_page_url"],
            }
            for row in page_rows
        ]

        latency = round((time.perf_counter() - t0) * 1000, 2)

        return {
            "query": raw,
            "page": page,
            "page_size": self.s.page_size,
            "total_pages": math.ceil(len(rows) / self.s.page_size),
            "result_count": len(rows),
            "result_count_exact": len(rows) < window,
            "latency_ms": latency,
            "results": results,
        }

    def search(self, raw_query, page: int = 1) -> dict:
        t0 = time.perf_counter()
        try:
            q = parse_query(raw_query, self.s.max_query_length, self.s.max_query_terms)
        except QueryError as e:
            raise InvalidSearchRequest(str(e))
        if not isinstance(page, int) or page < 1 or page > self.s.max_pages:
            raise InvalidSearchRequest(f"page must be between 1 and {self.s.max_pages}")

        window = self.s.page_size * self.s.max_pages
        res, mode = self.indexer.search(q, window, 0, True, self.ranker.field_weights, self.s.count_cap), "all"
        if res.total == 0 and len(q.terms) + len(q.phrases) > 1:
            res, mode = self.indexer.search(q, window, 0, False, self.ranker.field_weights, self.s.count_cap), "any"

        candidate_docs = self.storage.get_documents([h.doc_id for h in res.hits])
        ranked = self.ranker.rank(q, res.hits, candidate_docs)
        start = (page - 1) * self.s.page_size
        page_hits = ranked[start:start + self.s.page_size]
        docs = {h.doc_id: candidate_docs[h.doc_id] for h in page_hits if h.doc_id in candidate_docs}
        results = []
        for h in page_hits:
            d = docs.get(h.doc_id)
            if d is None or d.status != "ok":   # index briefly out of sync / doc deactivated: never show it
                continue
            results.append({
                "title": d.title or d.url,
                "url": d.url,
                "canonical_url": d.canonical_url,
                "display_url": d.canonical_url or d.url,
                "domain": d.domain,
                "snippet": "" if d.nosnippet else make_snippet(
                    d.content, q.all_terms, fallback=d.description
                ),
                "favicon": None,
                "language": d.language,
                "country": None,
                "published_at": None,
                "updated_at": d.updated_at,
                "source_type": "web",
                "score": h.score,
            })
        reachable = min(res.total, window)
        latency = round((time.perf_counter() - t0) * 1000, 2)
        try:
            sample_rate = float(getattr(self.s, "query_log_sample_rate", 0.10))
            if sample_rate >= 1.0:
                self.storage.log_query(q.normalized, res.total, latency)
            elif sample_rate > 0.0 and random.random() < sample_rate:
                self.storage.log_query(q.normalized, res.total, latency)
        except Exception:
            pass               # metrics must never break search

        response = {
            "query": q.raw.strip(),
            "page": page,
            "page_size": self.s.page_size,
            "total_pages": math.ceil(reachable / self.s.page_size),
            "result_count": res.total,
            "result_count_exact": not res.total_capped,
            "match": mode,
            "latency_ms": latency,
            "results": results,
        }
        if res.corrected_query:
            response["corrected_query"] = res.corrected_query
        return response
