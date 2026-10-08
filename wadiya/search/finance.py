"""Finance search provider contract and Alpha Vantage implementation."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
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
    """Finance provider backed by Alpha Vantage symbol search and quotes."""

    BASE_URL = "https://www.alphavantage.co/query"

    # Keep Alpha Vantage traffic low because the free plan has a
    # relatively small daily request allowance.
    SEARCH_CACHE_TTL = 3600.0
    QUOTE_CACHE_TTL = 60.0
    SEARCH_PERSIST_TTL = 7 * 24 * 60 * 60

    def __init__(self, api_key: str, timeout: float = 10.0):
        self.api_key = api_key.strip()
        self.timeout = float(timeout)

        self._search_cache: dict[
            str,
            tuple[float, list[FinanceResult]],
        ] = {}

        self._quote_cache: dict[
            str,
            tuple[float, tuple[float | None, float | None, str | None]],
        ] = {}

        self._search_cache_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "finance_search_cache.json"
        )

        self._load_search_cache()

    def search(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FinanceResult]:
        query = query.strip()

        if not query or not self.api_key:
            return []

        cache_key = query.casefold()
        now = time.monotonic()

        cached = self._search_cache.get(cache_key)

        if cached is not None:
            cached_at, cached_results = cached

            if now - cached_at < self.SEARCH_CACHE_TTL:
                return self._slice_results(
                    cached_results,
                    limit,
                    offset,
                )

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
            return self._cached_results(cache_key, limit, offset)

        matches = payload.get("bestMatches")

        # Alpha Vantage returns an "Information" or "Note" object when
        # the request is blocked by a plan/rate limit. Never replace a
        # previously cached search result with an empty response.
        if not isinstance(matches, list):
            return self._cached_results(cache_key, limit, offset)

        parsed: list[tuple[dict, str, str, float]] = []

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

            parsed.append((match, symbol, name, score))

        # Alpha Vantage may rate-limit multiple GLOBAL_QUOTE requests.
        # Enrich only the strongest search match with a live quote.
        top_symbol = parsed[0][1] if parsed else None

        top_quote = (
            self._get_quote(top_symbol)
            if top_symbol
            else (None, None, None)
        )

        results: list[FinanceResult] = []

        for index, (match, symbol, name, score) in enumerate(parsed):
            if index == 0:
                price, change, change_percent = top_quote
            else:
                price, change, change_percent = None, None, None

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
                    price=price,
                    change=change,
                    change_percent=change_percent,
                )
            )

        self._search_cache[cache_key] = (
            now,
            results,
        )

        self._save_search_cache()

        return self._slice_results(results, limit, offset)

    def history(
        self,
        symbol: str,
        range_name: str = "1M",
    ) -> list[dict[str, float | str]]:
        """Return historical daily closing prices for a supported chart range."""
        symbol = symbol.strip()

        if not symbol or not self.api_key:
            return []

        range_map = {
            "1D": "TIME_SERIES_INTRADAY",
            "1W": "TIME_SERIES_DAILY",
            "1M": "TIME_SERIES_DAILY",
            "3M": "TIME_SERIES_DAILY",
            "6M": "TIME_SERIES_DAILY",
            "1Y": "TIME_SERIES_DAILY",
            "5Y": "TIME_SERIES_DAILY",
            "MAX": "TIME_SERIES_DAILY",
        }

        function = range_map.get(range_name.upper())

        if function is None:
            return []

        params = {
            "function": function,
            "symbol": symbol,
            "apikey": self.api_key,
        }

        if function == "TIME_SERIES_INTRADAY":
            params["interval"] = "60min"

        if range_name.upper() in {"5Y", "MAX"}:
            params["outputsize"] = "full"

        request = Request(
            f"{self.BASE_URL}?{urlencode(params)}",
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

        series_key = {
            "TIME_SERIES_INTRADAY": "Time Series (60min)",
            "TIME_SERIES_DAILY": "Time Series (Daily)",
        }.get(function)

        series = payload.get(series_key or "")

        if not isinstance(series, dict):
            return []

        points: list[dict[str, float | str]] = []

        for timestamp, values in series.items():
            if not isinstance(values, dict):
                continue

            close = self._float_or_none(
                values.get("4. close")
            )

            if close is None:
                continue

            points.append(
                {
                    "date": str(timestamp),
                    "close": close,
                }
            )

        points.sort(key=lambda item: str(item["date"]))

        return self._limit_history(points, range_name)

    @staticmethod
    def _limit_history(
        points: list[dict[str, float | str]],
        range_name: str,
    ) -> list[dict[str, float | str]]:
        """Keep chart payloads small while preserving the selected range."""
        if not points:
            return []

        limits = {
            "1D": 24,
            "1W": 7,
            "1M": 31,
            "3M": 93,
            "6M": 186,
            "1Y": 366,
            "5Y": 500,
            "MAX": 1000,
        }

        limit = limits.get(range_name.upper(), 31)

        if len(points) <= limit:
            return points

        return points[-limit:]

    def _get_quote(
        self,
        symbol: str,
    ) -> tuple[float | None, float | None, str | None]:
        now = time.monotonic()
        cached = self._quote_cache.get(symbol)

        if cached is not None:
            cached_at, quote = cached

            if now - cached_at < self.QUOTE_CACHE_TTL:
                return quote

        params = urlencode(
            {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
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
            return self._cached_quote(symbol)

        quote = payload.get("Global Quote")

        if not isinstance(quote, dict):
            return self._cached_quote(symbol)

        price = self._float_or_none(
            quote.get("05. price")
        )
        change = self._float_or_none(
            quote.get("09. change")
        )
        change_percent = self._optional(
            quote.get("10. change percent")
        )

        result = (
            price,
            change,
            change_percent,
        )

        self._quote_cache[symbol] = (
            now,
            result,
        )

        return result

    def _load_search_cache(self) -> None:
        """Load previously successful finance searches from local disk."""
        try:
            if not self._search_cache_path.exists():
                return

            raw = json.loads(
                self._search_cache_path.read_text(encoding="utf-8")
            )

            if not isinstance(raw, dict):
                return

            now = time.monotonic()
            loaded: dict[
                str,
                tuple[float, list[FinanceResult]],
            ] = {}

            for cache_key, entry in raw.items():
                if not isinstance(entry, dict):
                    continue

                saved_at = entry.get("saved_at")
                items = entry.get("results")

                if not isinstance(saved_at, (int, float)):
                    continue

                if not isinstance(items, list):
                    continue

                age = time.time() - float(saved_at)

                if age < 0 or age > self.SEARCH_PERSIST_TTL:
                    continue

                results: list[FinanceResult] = []

                for item in items:
                    if not isinstance(item, dict):
                        continue

                    try:
                        results.append(
                            FinanceResult(
                                symbol=str(item.get("symbol") or ""),
                                name=str(item.get("name") or ""),
                                type=self._optional(item.get("type")),
                                region=self._optional(item.get("region")),
                                market_open=self._optional(
                                    item.get("market_open")
                                ),
                                market_close=self._optional(
                                    item.get("market_close")
                                ),
                                timezone=self._optional(
                                    item.get("timezone")
                                ),
                                currency=self._optional(
                                    item.get("currency")
                                ),
                                match_score=float(
                                    item.get("match_score") or 0
                                ),
                                price=self._float_or_none(
                                    item.get("price")
                                ),
                                change=self._float_or_none(
                                    item.get("change")
                                ),
                                change_percent=self._optional(
                                    item.get("change_percent")
                                ),
                            )
                        )
                    except (TypeError, ValueError):
                        continue

                if results:
                    loaded[cache_key] = (
                        now,
                        results,
                    )

            self._search_cache.update(loaded)

        except Exception:
            # Cache is an optimization only. Never break Finance search
            # because the local cache is missing or malformed.
            return

    def _save_search_cache(self) -> None:
        """Persist successful finance searches without storing credentials."""
        try:
            self._search_cache_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            payload: dict[str, dict] = {}

            for cache_key, (cached_at, results) in self._search_cache.items():
                payload[cache_key] = {
                    "saved_at": time.time(),
                    "results": [
                        asdict(result)
                        for result in results
                    ],
                }

            temporary_path = self._search_cache_path.with_suffix(
                ".tmp"
            )

            temporary_path.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            temporary_path.replace(self._search_cache_path)

        except Exception:
            # Cache persistence must never make the search request fail.
            return

    def _cached_results(
        self,
        cache_key: str,
        limit: int,
        offset: int,
    ) -> list[FinanceResult]:
        cached = self._search_cache.get(cache_key)

        if cached is None:
            return []

        _, results = cached

        return self._slice_results(
            results,
            limit,
            offset,
        )

    def _cached_quote(
        self,
        symbol: str,
    ) -> tuple[float | None, float | None, str | None]:
        cached = self._quote_cache.get(symbol)

        if cached is None:
            return None, None, None

        _, quote = cached
        return quote

    @staticmethod
    def _slice_results(
        results: list[FinanceResult],
        limit: int,
        offset: int,
    ) -> list[FinanceResult]:
        start = max(0, int(offset))
        end = start + max(0, int(limit))

        return results[start:end]

    @staticmethod
    def _float_or_none(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional(value) -> str | None:
        value = str(value or "").strip()
        return value or None
