from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class ExchangeConfig:
    name: str
    taker_fee_bps: float = 10.0
    maker_fee_bps: float = 0.0
    latency_ms: float = 150.0
    min_notional: float = 0.0


@dataclass(frozen=True)
class EngineConfig:
    symbols: List[str] = field(
        default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]
    )
    window_seconds: int = 120
    refresh_interval_seconds: int = 2
    max_tick_age_seconds: int = 5
    max_timestamp_drift_seconds: int = 2
    spread_threshold_bps: float = 15.0
    max_latency_penalty_bps: float = 50.0
    drift_penalty_bps_per_ms: float = 0.002
    exchanges: Dict[str, ExchangeConfig] = field(default_factory=dict)
