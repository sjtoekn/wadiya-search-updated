"""Dedicated SQLite FTS5 index for Books."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


TOKENIZER = "porter unicode61 remove_diacritics 2"


class BooksIndexer:
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
                "CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5("
                "title, author, isbn, description, "
                f"tokenize='{TOKENIZER}')"
            )

    def index(self, books) -> int:
        count = 0

        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                for book in books:
                    book_id = int(book["id"])

                    c.execute(
                        "DELETE FROM books_fts WHERE rowid=?",
                        (book_id,),
                    )

                    authors = book.get("author") or []
                    if isinstance(authors, str):
                        authors = [authors]

                    c.execute(
                        """
                        INSERT INTO books_fts(
                            rowid, title, author, isbn, description
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            book_id,
                            book.get("title") or "",
                            ", ".join(str(a) for a in authors),
                            book.get("isbn") or "",
                            book.get("description") or "",
                        ),
                    )
                    count += 1

                c.execute("COMMIT")
            except BaseException:
                c.execute("ROLLBACK")
                raise

        return count

    def remove(self, book_ids) -> None:
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                for book_id in book_ids:
                    c.execute(
                        "DELETE FROM books_fts WHERE rowid=?",
                        (int(book_id),),
                    )
                c.execute("COMMIT")
            except BaseException:
                c.execute("ROLLBACK")
                raise

    def clear(self) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM books_fts")

    def search(self, query: str, limit: int, offset: int = 0):
        query = str(query or "").strip()
        if not query:
            return _BookSearchHits([])

        limit = max(0, int(limit))
        offset = max(0, int(offset))

        parts = [
            f'"{term.replace(chr(34), "")}"'
            for term in query.split()
            if term
        ]
        if not parts:
            return _BookSearchHits([])

        match = " AND ".join(parts)

        with self._conn() as c:
            rows = c.execute(
                """
                SELECT
                    rowid AS id,
                    title,
                    author,
                    isbn,
                    description,
                    bm25(books_fts) AS rank
                FROM books_fts
                WHERE books_fts MATCH ?
                ORDER BY rank ASC
                LIMIT ? OFFSET ?
                """,
                (match, limit, offset),
            ).fetchall()

            total = c.execute(
                """
                SELECT COUNT(*)
                FROM books_fts
                WHERE books_fts MATCH ?
                """,
                (match,),
            ).fetchone()[0]

        return _BookSearchHits(
            [
                {
                    "id": int(row["id"]),
                    "title": row["title"],
                    "author": [
                        name.strip()
                        for name in (row["author"] or "").split(",")
                        if name.strip()
                    ],
                    "isbn": row["isbn"] or None,
                    "description": row["description"] or None,
                    "score": float(-row["rank"]),
                }
                for row in rows
            ],
            total=int(total),
        )


class _BookSearchHits:
    def __init__(self, hits, total=None):
        self.hits = hits
        self.total = len(hits) if total is None else total
        self.total_capped = False
