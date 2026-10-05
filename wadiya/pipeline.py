"""Glue between Storage and Indexer (the only place that knows both)."""
from __future__ import annotations

from .indexer.base import IndexDocument, Indexer
from .storage.base import Storage


def sync_index(storage: Storage, indexer: Indexer, batch: int = 200) -> tuple:
    """Bring the index in line with storage. Active docs are (re)indexed; deactivated docs are REMOVED
    from the index. Returns (indexed, removed)."""
    indexed = removed = 0
    while True:
        docs = storage.documents_needing_index(batch)
        if not docs:
            return indexed, removed
        live = [d for d in docs if d.status == "ok"]
        dead = [d.id for d in docs if d.status != "ok"]
        indexer.index(IndexDocument(d.id, d.url, d.domain, d.title, d.headings, d.description, d.content) for d in live)
        indexer.remove(dead)
        storage.mark_indexed([d.id for d in docs])
        indexed += len(live)
        removed += len(dead)


def index_pending(storage: Storage, indexer: Indexer, batch: int = 200) -> int:
    """Sync the index; returns how many documents were (re)indexed."""
    return sync_index(storage, indexer, batch)[0]


def rebuild_index(storage: Storage, indexer: Indexer) -> int:
    indexer.clear()
    storage.reset_indexed()
    return index_pending(storage, indexer)
