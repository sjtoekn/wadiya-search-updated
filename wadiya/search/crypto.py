"""Crypto search providers.

Crypto search reads from local storage so normal searches do not depend on
external market APIs. A future background updater can refresh the stored
assets and quotes independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..storage.base import CryptoAsset, Storage


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


DEFAULT_CRYPTO_ASSETS = (
    CryptoAsset(
        id=None,
        symbol="BTC",
        name="Bitcoin",
        asset_type="Cryptocurrency",
        rank=1,
        currency="USD",
        updated_at="",
    ),
    CryptoAsset(
        id=None,
        symbol="ETH",
        name="Ethereum",
        asset_type="Cryptocurrency",
        rank=2,
        currency="USD",
        updated_at="",
    ),
    CryptoAsset(
        id=None,
        symbol="USDT",
        name="Tether",
        asset_type="Cryptocurrency",
        rank=3,
        currency="USD",
        updated_at="",
    ),
    CryptoAsset(
        id=None,
        symbol="BNB",
        name="BNB",
        asset_type="Cryptocurrency",
        rank=4,
        currency="USD",
        updated_at="",
    ),
    CryptoAsset(
        id=None,
        symbol="SOL",
        name="Solana",
        asset_type="Cryptocurrency",
        rank=5,
        currency="USD",
        updated_at="",
    ),
)


def seed_default_crypto_assets(storage: Storage) -> None:
    """Ensure the local crypto catalog has its initial assets."""
    for asset in DEFAULT_CRYPTO_ASSETS:
        existing = storage.get_crypto_asset(asset.symbol)

        if existing is None:
            storage.save_crypto_asset(asset)


class SQLiteCryptoProvider:
    """Crypto search provider backed entirely by local SQLite storage."""

    def __init__(self, storage: Storage):
        self.storage = storage

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

        limit = max(0, int(limit))
        offset = max(0, int(offset))

        if limit == 0:
            return []

        assets = self.storage.get_crypto_assets(limit=1000, offset=0)

        matches = [
            asset
            for asset in assets
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
                asset.id if asset.id is not None else 999999999,
            )
        )

        results: list[CryptoResult] = []

        for asset in matches[offset:offset + limit]:
            quote = self.storage.get_crypto_quote(asset.symbol)

            results.append(
                CryptoResult(
                    symbol=asset.symbol,
                    name=asset.name,
                    asset_type=asset.asset_type,
                    rank=asset.rank,
                    price=quote.price if quote else None,
                    change=quote.change if quote else None,
                    change_percent=quote.change_percent if quote else None,
                    currency=(
                        quote.currency
                        if quote is not None
                        else asset.currency
                    ),
                )
            )

        return results
