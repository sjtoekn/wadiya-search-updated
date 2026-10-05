"""Indexer interface. The search API/service depend only on this, never on FTS5."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass
class IndexDocument:
    doc_id: int
    url: str
    domain: str
    title: str
    headings: str
    description: str
    content: str


@dataclass
class Hit:
    doc_id: int
    score: float          # higher is better
    title: str
    url: str
    domain: str


@dataclass
class SearchHits:
    total: int            # number of matches (capped by count_cap)
    total_capped: bool
    hits: list = field(default_factory=list)


DEFAULT_WEIGHTS = {"title": 5.0, "headings": 3.0, "description": 2.0, "body": 1.0}


class Indexer(ABC):
    @abstractmethod
    def init(self) -> None: ...
    @abstractmethod
    def index(self, docs: Iterable[IndexDocument]) -> int: ...
    @abstractmethod
    def remove(self, doc_ids: Iterable[int]) -> None: ...
    @abstractmethod
    def clear(self) -> None: ...
    @abstractmethod
    def search(self, query, limit: int, offset: int = 0, match_all: bool = True,
               weights: Optional[dict] = None, count_cap: int = 10_000) -> SearchHits: ...
    @abstractmethod
    def count(self) -> int: ...
    @abstractmethod
    def info(self) -> dict: ...
