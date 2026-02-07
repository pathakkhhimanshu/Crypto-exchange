from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Protocol, Sequence


@dataclass(frozen=True)
class PriceTick:
    exchange: str
    symbol: str
    timestamp: datetime
    price: float
    volume: float | None = None


class PriceAdapter(Protocol):
    async def fetch_latest(self, symbols: Sequence[str]) -> List[PriceTick]:
        ...


@dataclass(frozen=True)
class Snapshot:
    timestamp: datetime
    ticks: Dict[str, Dict[str, PriceTick]]


class SnapshotStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._snapshot: Snapshot | None = None

    async def update(self, snapshot: Snapshot) -> None:
        async with self._lock:
            self._snapshot = snapshot

    async def get(self) -> Snapshot | None:
        async with self._lock:
            return self._snapshot


async def fetch_all(adapters: Dict[str, PriceAdapter], symbols: Iterable[str]) -> List[PriceTick]:
    tasks = [adapter.fetch_latest(list(symbols)) for adapter in adapters.values()]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    ticks: List[PriceTick] = []
    for batch in results:
        ticks.extend(batch)
    return ticks


class DummyAdapter:
    def __init__(self, exchange: str, prices: Iterable[tuple[str, float]]) -> None:
        self._exchange = exchange
        self._prices = list(prices)

    async def fetch_latest(self, symbols: Sequence[str]) -> List[PriceTick]:
        await asyncio.sleep(0)
        now = datetime.now(tz=timezone.utc)
        ticks: List[PriceTick] = []
        for symbol, price in self._prices:
            if symbol in symbols:
                ticks.append(
                    PriceTick(
                        exchange=self._exchange,
                        symbol=symbol,
                        timestamp=now,
                        price=price,
                        volume=None,
                    )
                )
        return ticks
