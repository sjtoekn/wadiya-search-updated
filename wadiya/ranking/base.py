from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence


class Ranker(ABC):
    """rank(query, hits) -> hits in final order. `field_weights` tells the indexer how to
    weight fields when it retrieves candidates (title > headings > description > body)."""
    field_weights: dict = {}

    @abstractmethod
    def rank(self, query, hits: Sequence) -> list: ...
