"""Crypto search provider foundation.

The provider interface is intentionally independent of any exchange.
Exchange adapters can be added later without changing the search API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CryptoResult:
    symbol: str
    name: str
    asset_type: str
    rank: int | None = None
    price: float | None = None
    change: float | None = None
    change_percent: str | None = None
    currency: str = "USD"


class CryptoProvider(Protocol):
    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[CryptoResult]:
        ...


class StaticCryptoProvider:
    """Small local foundation until live exchange providers are added."""

    _ASSETS = (
        CryptoResult(
            symbol="BTC",
            name="Bitcoin",
            asset_type="Cryptocurrency",
            rank=1,
        ),
        CryptoResult(
            symbol="ETH",
            name="Ethereum",
            asset_type="Cryptocurrency",
            rank=2,
        ),
        CryptoResult(
            symbol="USDT",
            name="Tether",
            asset_type="Cryptocurrency",
            rank=3,
        ),
        CryptoResult(
            symbol="BNB",
            name="BNB",
            asset_type="Cryptocurrency",
            rank=4,
        ),
        CryptoResult(
            symbol="SOL",
            name="Solana",
            asset_type="Cryptocurrency",
            rank=5,
        ),
    )

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[CryptoResult]:
        needle = query.strip().lower()

        if not needle:
            return []

        matches = [
            asset
            for asset in self._ASSETS
            if needle in asset.symbol.lower()
            or needle in asset.name.lower()
        ]

        matches.sort(
            key=lambda asset: (
                0
                if asset.symbol.lower() == needle
                else 1
                if asset.name.lower() == needle
                else 2,
                asset.rank if asset.rank is not None else 999999,
            )
        )

        return matches[offset:offset + limit]
