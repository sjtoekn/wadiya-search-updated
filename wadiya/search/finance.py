"""Finance search provider contract and Alpha Vantage implementation."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class FinanceResult:
    symbol: str
    name: str
    type: str | None
    region: str | None
    market_open: str | None
    market_close: str | None
    timezone: str | None
    currency: str | None
    match_score: float
    price: float | None = None
    change: float | None = None
    change_percent: str | None = None


class FinanceProvider(Protocol):
    def search(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FinanceResult]:
        ...


class AlphaVantageFinanceProvider:
    """Finance provider backed by Alpha Vantage SYMBOL_SEARCH."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str, timeout: float = 10.0):
        self.api_key = api_key.strip()
        self.timeout = float(timeout)

    def search(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FinanceResult]:
        query = query.strip()

        if not query or not self.api_key:
            return []

        params = urlencode(
            {
                "function": "SYMBOL_SEARCH",
                "keywords": query,
                "apikey": self.api_key,
            }
        )

        request = Request(
            f"{self.BASE_URL}?{params}",
            headers={"User-Agent": "WadiyaFinance/1.0"},
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(
                    response.read().decode("utf-8")
                )
        except Exception:
            return []

        matches = payload.get("bestMatches")

        if not isinstance(matches, list):
            return []

        results: list[FinanceResult] = []

        for match in matches:
            if not isinstance(match, dict):
                continue

            symbol = str(match.get("1. symbol") or "").strip()
            name = str(match.get("2. name") or "").strip()

            if not symbol or not name:
                continue

            try:
                score = float(match.get("9. matchScore") or 0)
            except (TypeError, ValueError):
                score = 0.0

            results.append(
                FinanceResult(
                    symbol=symbol,
                    name=name,
                    type=self._optional(match.get("3. type")),
                    region=self._optional(match.get("4. region")),
                    market_open=self._optional(match.get("5. marketOpen")),
                    market_close=self._optional(match.get("6. marketClose")),
                    timezone=self._optional(match.get("7. timezone")),
                    currency=self._optional(match.get("8. currency")),
                    match_score=score,
                )
            )

        start = max(0, int(offset))
        end = start + max(0, int(limit))

        return results[start:end]

    @staticmethod
    def _optional(value) -> str | None:
        value = str(value or "").strip()
        return value or None
