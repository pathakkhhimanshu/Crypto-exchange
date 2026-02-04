from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ExchangeConfig:
    name: str
    taker_fee_bps: float = 10.0
    maker_fee_bps: float = 0.0
    latency_ms: float = 150.0
    min_notional: float = 0.0


@dataclass(frozen=True)
class ModelConfig:
    sentiment_model_id: str = "ProsusAI/finbert"
    trend_model_id: str = "huggingface/time-series-transformer-tourism-monthly"
    anomaly_model_id: str = "ibm-research/patchtst-etth1-pretrain"
    device: str = "cpu"
    max_length: int = 256


@dataclass(frozen=True)
class EngineConfig:
    symbols: List[str] = field(
        default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]
    )
    window_seconds: int = 120
    min_points: int = 16
    spread_threshold_bps: float = 15.0
    max_latency_penalty_bps: float = 50.0
    anomaly_threshold: float = 2.5
    exchanges: Dict[str, ExchangeConfig] = field(default_factory=dict)
    models: ModelConfig = field(default_factory=ModelConfig)
