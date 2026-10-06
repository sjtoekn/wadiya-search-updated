"""SQLite FTS5 implementation of Indexer (own database file, separate from document storage)."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

from .base import DEFAULT_WEIGHTS, Hit, IndexDocument, Indexer, SearchHits

TOKENIZER = "porter unicode61 remove_diacritics 2"


class FTS5Indexer(Indexer):
    def __init__(self, path: str):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
        finally:
            conn.close()

    def init(self) -> None:
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5("
                "title, headings, description, body, url UNINDEXED, domain UNINDEXED, "
                f"tokenize='{TOKENIZER}')")

    # rowid == document id, so replace/remove are O(log n)
    def index(self, docs: Iterable[IndexDocument]) -> int:
        n = 0
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                for d in docs:
                    c.execute("DELETE FROM docs_fts WHERE rowid=?", (d.doc_id,))
                    c.execute("INSERT INTO docs_fts(rowid,title,headings,description,body,url,domain) "
                              "VALUES (?,?,?,?,?,?,?)",
                              (d.doc_id, d.title, d.headings, d.description, d.content, d.url, d.domain))
                    n += 1
                c.execute("COMMIT")
            except BaseException:
                c.execute("ROLLBACK")
                raise
        return n

    def remove(self, doc_ids: Iterable[int]) -> None:
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            for i in doc_ids:
                c.execute("DELETE FROM docs_fts WHERE rowid=?", (i,))
            c.execute("COMMIT")

    def clear(self) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM docs_fts")

    @staticmethod
    def build_match(query, match_all: bool) -> str:
        # Tokens from the query parser are word characters only; each is still quoted so
        # user input can never become FTS5 operator syntax.
        parts = [f'"{t}"' for t in query.terms] + [f'"{" ".join(p)}"' for p in query.phrases]
        return (" AND " if match_all else " OR ").join(parts)

    def search(self, query, limit: int, offset: int = 0, match_all: bool = True,
               weights: Optional[dict] = None, count_cap: int = 10_000) -> SearchHits:
        w = {**DEFAULT_WEIGHTS, **(weights or {})}
        match = self.build_match(query, match_all)
        if not match:
            return SearchHits(0, False, [])
        try:
            with self._conn() as c:
                total = c.execute("SELECT count(*) FROM (SELECT 1 FROM docs_fts WHERE docs_fts MATCH ? LIMIT ?)",
                                  (match, count_cap)).fetchone()[0]
                rows = c.execute(
                    "SELECT rowid AS doc_id, title, url, domain, bm25(docs_fts, ?, ?, ?, ?, 0, 0) AS bm "
                    "FROM docs_fts WHERE docs_fts MATCH ? ORDER BY bm LIMIT ? OFFSET ?",
                    (w["title"], w["headings"], w["description"], w["body"], match, limit, offset)).fetchall()
        except sqlite3.OperationalError:
            return SearchHits(0, False, [])
        return SearchHits(total, total >= count_cap,
                          [Hit(r["doc_id"], -float(r["bm"]), r["title"], r["url"], r["domain"]) for r in rows])

    def count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT count(*) FROM docs_fts").fetchone()[0]

    def info(self) -> dict:
        size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        return {"engine": "sqlite-fts5", "tokenizer": TOKENIZER, "documents": self.count(),
                "size_bytes": size, "sqlite_version": sqlite3.sqlite_version}
