from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Protocol, Sequence


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


# Real exchange adapters (e.g., CCXT or native REST/WebSocket clients)
# should implement the PriceAdapter protocol and be injected into the engine.
