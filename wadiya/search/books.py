"""Books search provider contract and deterministic v1 provider."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BookResult:
    title: str
    author: list[str]
    isbn: str | None
    cover_url: str | None
    publisher: str | None
    published_at: str | None
    description: str | None
    url: str
    language: str | None
    score: float


class BooksProvider(Protocol):
    def search(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookResult]:
        ...


class StaticBooksProvider:
    """Deterministic provider used until a real Books source is connected."""

    def search(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookResult]:
        if not query.strip():
            return []

        return [
            BookResult(
                title="Python Programming",
                author=["Example Author"],
                isbn=None,
                cover_url=None,
                publisher=None,
                published_at=None,
                description="A sample book result for the Books v1 contract.",
                url="https://books.example/python-programming",
                language="en",
                score=1.0,
            )
        ][offset:offset + limit]


class DBBooksProvider:
    """Books provider backed by SQLite metadata and the Books FTS index."""

    def __init__(self, storage, indexer):
        self.storage = storage
        self.indexer = indexer

    def search(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BookResult]:
        hits = self.indexer.search(
            query,
            limit=max(0, int(limit)),
            offset=max(0, int(offset)),
        )

        results = []

        for hit in hits.hits:
            book = self.storage.get_book_by_url(
                self._url_from_hit(hit)
            )

            if book is None:
                book_id = hit.get("id")
                if book_id is not None:
                    for candidate in self.storage.get_books(limit=10000):
                        if candidate.id == int(book_id):
                            book = candidate
                            break

            if book is None:
                continue

            results.append(
                BookResult(
                    title=book.title,
                    author=list(book.author),
                    isbn=book.isbn,
                    cover_url=book.cover_url,
                    publisher=book.publisher,
                    published_at=book.published_at,
                    description=book.description,
                    url=book.url,
                    language=book.language,
                    score=float(hit.get("score", book.score)),
                )
            )

        return results

    @staticmethod
    def _url_from_hit(hit) -> str:
        return str(hit.get("url") or "")
