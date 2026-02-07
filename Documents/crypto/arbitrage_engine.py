from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List

from config import EngineConfig, ExchangeConfig
from data_ingestion import PriceTick
from feature_engineering import NormalizedTick, RollingWindowStore, normalize_ticks
from model_inference import compute_volatility_bps


@dataclass(frozen=True)
class ArbitrageOpportunity:
    symbol: str
    exchange_buy: str
    exchange_sell: str
    buy_price: float
    sell_price: float
    raw_spread_bps: float
    net_spread_bps: float
    fees_bps: float
    latency_bps: float
    drift_ms: float
    score_bps: float
    volatility_bps: float
    timestamp: datetime


class ArbitrageEngine:
    def __init__(self, config: EngineConfig) -> None:
        self._config = config
        self._store = RollingWindowStore(config.window_seconds)

    def ingest_ticks(self, ticks: List[PriceTick]) -> None:
        normalized = normalize_ticks(
            [
                NormalizedTick(
                    exchange=tick.exchange,
                    symbol=tick.symbol,
                    timestamp=tick.timestamp,
                    price=tick.price,
                )
                for tick in ticks
            ]
        )
        self._store.add(normalized)

    def compute_opportunities(self, symbols: Iterable[str], now: datetime) -> List[ArbitrageOpportunity]:
        opportunities: List[ArbitrageOpportunity] = []

        for symbol in symbols:
            latest = self._store.latest_by_symbol(
                symbol, now=now, max_age_seconds=self._config.max_tick_age_seconds
            )
            if len(latest) < 2:
                continue

            # Volatility for context only (transparent metric)
            series = []
            for exchange in latest.keys():
                series.extend([tick.price for tick in self._store.get_series(exchange, symbol)])
            volatility_bps = compute_volatility_bps(series).value_bps if series else 0.0

            items = list(latest.items())
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    exch_a, tick_a = items[i]
                    exch_b, tick_b = items[j]

                    # Skip pairs that are too far apart in time
                    drift_ms = abs((tick_a.timestamp - tick_b.timestamp).total_seconds() * 1000.0)
                    if drift_ms > self._config.max_timestamp_drift_seconds * 1000.0:
                        continue

                    # Direction A -> B
                    opp_ab = self._build_opportunity(
                        symbol=symbol,
                        buy_exchange=exch_a,
                        sell_exchange=exch_b,
                        buy_price=tick_a.price,
                        sell_price=tick_b.price,
                        drift_ms=drift_ms,
                        volatility_bps=volatility_bps,
                        now=now,
                    )
                    if opp_ab is not None:
                        opportunities.append(opp_ab)

                    # Direction B -> A
                    opp_ba = self._build_opportunity(
                        symbol=symbol,
                        buy_exchange=exch_b,
                        sell_exchange=exch_a,
                        buy_price=tick_b.price,
                        sell_price=tick_a.price,
                        drift_ms=drift_ms,
                        volatility_bps=volatility_bps,
                        now=now,
                    )
                    if opp_ba is not None:
                        opportunities.append(opp_ba)

        return opportunities

    def _build_opportunity(
        self,
        symbol: str,
        buy_exchange: str,
        sell_exchange: str,
        buy_price: float,
        sell_price: float,
        drift_ms: float,
        volatility_bps: float,
        now: datetime,
    ) -> ArbitrageOpportunity | None:
        raw_spread_bps = self._calculate_spread_bps(buy_price, sell_price)
        net_spread_bps, fees_bps, latency_bps = self._adjust_spread(
            buy_exchange, sell_exchange, raw_spread_bps
        )

        if net_spread_bps < self._config.spread_threshold_bps:
            return None

        score_bps = self._score(net_spread_bps, drift_ms)

        return ArbitrageOpportunity(
            symbol=symbol,
            exchange_buy=buy_exchange,
            exchange_sell=sell_exchange,
            buy_price=buy_price,
            sell_price=sell_price,
            raw_spread_bps=raw_spread_bps,
            net_spread_bps=net_spread_bps,
            fees_bps=fees_bps,
            latency_bps=latency_bps,
            drift_ms=drift_ms,
            score_bps=score_bps,
            volatility_bps=volatility_bps,
            timestamp=now,
        )

    def _calculate_spread_bps(self, buy_price: float, sell_price: float) -> float:
        if buy_price <= 0:
            return 0.0
        return ((sell_price - buy_price) / buy_price) * 10_000

    def _adjust_spread(self, buy_exchange: str, sell_exchange: str, spread_bps: float) -> tuple[float, float, float]:
        buy_cfg = self._config.exchanges.get(
            buy_exchange, ExchangeConfig(name=buy_exchange)
        )
        sell_cfg = self._config.exchanges.get(
            sell_exchange, ExchangeConfig(name=sell_exchange)
        )
        fees_bps = buy_cfg.taker_fee_bps + sell_cfg.taker_fee_bps
        latency_bps = min(
            (buy_cfg.latency_ms + sell_cfg.latency_ms) * 0.01,
            self._config.max_latency_penalty_bps,
        )
        return spread_bps - fees_bps - latency_bps, fees_bps, latency_bps

    def _score(self, net_spread_bps: float, drift_ms: float) -> float:
        drift_penalty = drift_ms * self._config.drift_penalty_bps_per_ms
        return net_spread_bps - drift_penalty
