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
