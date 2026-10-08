"""Background-friendly Binance crypto quote updater.

This module only fetches public Binance market data and persists it locally.
Normal crypto searches never call Binance directly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..storage.base import CryptoQuote, Storage


BINANCE_24HR_URL = "https://data-api.binance.vision/api/v3/ticker/24hr"

# Keep the initial asset set deliberately small.
# More assets can be added later without changing the storage/search architecture.
BINANCE_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "BNB": "BNBUSDT",
    "SOL": "SOLUSDT",
}


class BinanceCryptoUpdater:
    def __init__(
        self,
        storage: Storage,
        *,
        timeout: float = 10.0,
    ) -> None:
        self.storage = storage
        self.timeout = max(1.0, float(timeout))

    def update(self) -> int:
        """Fetch Binance 24h data and save available quotes.

        Returns the number of successfully updated assets.
        """
        symbols = list(BINANCE_SYMBOLS.values())
        query = urlencode({"symbols": json.dumps(symbols, separators=(",", ":"))})
        url = f"{BINANCE_24HR_URL}?{query}"

        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Wadiya-Crypto-Updater/1.0",
            },
            method="GET",
        )

        with urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not isinstance(payload, list):
            raise ValueError("Binance 24hr response must be a JSON list")

        reverse_symbols = {
            binance_symbol: asset_symbol
            for asset_symbol, binance_symbol in BINANCE_SYMBOLS.items()
        }

        fetched_at = datetime.now(timezone.utc).isoformat()
        updated = 0

        for row in payload:
            if not isinstance(row, dict):
                continue

            binance_symbol = str(row.get("symbol") or "").upper()
            asset_symbol = reverse_symbols.get(binance_symbol)

            if asset_symbol is None:
                continue

            price = _float_or_none(row.get("lastPrice"))
            change = _float_or_none(row.get("priceChange"))
            change_percent = _string_or_none(row.get("priceChangePercent"))

            self.storage.save_crypto_quote(
                CryptoQuote(
                    id=None,
                    symbol=asset_symbol,
                    price=price,
                    change=change,
                    change_percent=change_percent,
                    currency="USD",
                    source="binance",
                    fetched_at=fetched_at,
                )
            )
            updated += 1

        return updated


def _float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
