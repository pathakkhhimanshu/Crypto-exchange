from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Dict, Iterable, List, Optional, Tuple

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


class RollingWindowStore:
    def __init__(self, window_seconds: int) -> None:
        self._window_seconds = window_seconds
        self._data: Dict[Tuple[str, str], Deque[NormalizedTick]] = defaultdict(deque)

    def add(self, ticks: Iterable[NormalizedTick]) -> None:
        for tick in ticks:
            key = (tick.exchange, tick.symbol)
            bucket = self._data[key]
            if bucket and tick.timestamp < bucket[-1].timestamp:
                # Reject out-of-order ticks to preserve temporal integrity
                continue
            bucket.append(tick)
            self._trim(bucket)

    def get_series(self, exchange: str, symbol: str) -> List[NormalizedTick]:
        key = (exchange.lower(), normalize_symbol(symbol))
        bucket = self._data.get(key, deque())
        return list(bucket)

    def latest_by_symbol(
        self, symbol: str, now: datetime, max_age_seconds: Optional[int] = None
    ) -> Dict[str, NormalizedTick]:
        result: Dict[str, NormalizedTick] = {}
        symbol = normalize_symbol(symbol)
        for (exchange, sym), bucket in self._data.items():
            if sym != symbol or not bucket:
                continue
            latest = bucket[-1]
            if max_age_seconds is not None:
                age_seconds = (now - latest.timestamp).total_seconds()
                if age_seconds > max_age_seconds:
                    continue
            result[exchange] = latest
        return result

    def _trim(self, bucket: Deque[NormalizedTick]) -> None:
        if not bucket:
            return
        cutoff = bucket[-1].timestamp.timestamp() - self._window_seconds
        while bucket and bucket[0].timestamp.timestamp() < cutoff:
            bucket.popleft()
