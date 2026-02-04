from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Dict, Iterable, List, Tuple

import pandas as pd

@dataclass(frozen=True)
class NormalizedTick:
    exchange: str
    symbol: str
    timestamp: datetime
    price: float


def normalize_symbol(symbol: str) -> str:
    return symbol.replace("-", "/").upper()


def normalize_ticks(ticks: Iterable[NormalizedTick]) -> List[NormalizedTick]:
    normalized: List[NormalizedTick] = []
    for tick in ticks:
        normalized.append(
            NormalizedTick(
                exchange=tick.exchange.lower(),
                symbol=normalize_symbol(tick.symbol),
                timestamp=tick.timestamp.astimezone(timezone.utc),
                price=float(tick.price),
            )
        )
    return normalized


def to_frame(ticks: Iterable[NormalizedTick]) -> pd.DataFrame:
    rows = [
        {
            "exchange": tick.exchange,
            "symbol": tick.symbol,
            "timestamp": tick.timestamp,
            "price": tick.price,
        }
        for tick in ticks
    ]
    return pd.DataFrame(rows)


class RollingWindowStore:
    def __init__(self, window_seconds: int) -> None:
        self._window_seconds = window_seconds
        self._data: Dict[Tuple[str, str], Deque[NormalizedTick]] = defaultdict(deque)

    def add(self, ticks: Iterable[NormalizedTick]) -> None:
        for tick in ticks:
            key = (tick.exchange, tick.symbol)
            bucket = self._data[key]
            bucket.append(tick)
            self._trim(bucket)

    def get_series(self, exchange: str, symbol: str) -> List[NormalizedTick]:
        key = (exchange.lower(), normalize_symbol(symbol))
        bucket = self._data.get(key, deque())
        return list(bucket)

    def latest_by_symbol(self, symbol: str) -> Dict[str, NormalizedTick]:
        result: Dict[str, NormalizedTick] = {}
        symbol = normalize_symbol(symbol)
        for (exchange, sym), bucket in self._data.items():
            if sym != symbol or not bucket:
                continue
            result[exchange] = bucket[-1]
        return result

    def _trim(self, bucket: Deque[NormalizedTick]) -> None:
        if not bucket:
            return
        cutoff = bucket[-1].timestamp.timestamp() - self._window_seconds
        while bucket and bucket[0].timestamp.timestamp() < cutoff:
            bucket.popleft()
