"""Search orchestration: parse -> retrieve -> rank -> hydrate -> snippet. No crawling, no SQL."""
from __future__ import annotations

import math
import time

from ..indexer.base import Indexer
from ..query.parser import QueryError, parse_query
from ..ranking.base import Ranker
from ..storage.base import Storage
from .snippets import make_snippet


class InvalidSearchRequest(ValueError):
    pass


class SearchService:
    def __init__(self, settings, storage: Storage, indexer: Indexer, ranker: Ranker):
        self.s, self.storage, self.indexer, self.ranker = settings, storage, indexer, ranker

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

        ranked = self.ranker.rank(q, res.hits)
        start = (page - 1) * self.s.page_size
        page_hits = ranked[start:start + self.s.page_size]
        docs = self.storage.get_documents([h.doc_id for h in page_hits])
        results = []
        for h in page_hits:
            d = docs.get(h.doc_id)
            if d is None or d.status != "ok":   # index briefly out of sync / doc deactivated: never show it
                continue
            results.append({"title": d.title or d.url, "url": d.url, "domain": d.domain,
                            "snippet": make_snippet(d.content, q.all_terms, fallback=d.description)})
        reachable = min(res.total, window)
        latency = round((time.perf_counter() - t0) * 1000, 2)
        try:
            self.storage.log_query(q.normalized, res.total, latency)
        except Exception:
            pass               # metrics must never break search
        return {"query": q.raw.strip(), "page": page, "page_size": self.s.page_size,
                "total_pages": math.ceil(reachable / self.s.page_size), "result_count": res.total,
                "result_count_exact": not res.total_capped, "match": mode,
                "latency_ms": latency, "results": results}
