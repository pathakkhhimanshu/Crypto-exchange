from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from config import EngineConfig, ExchangeConfig
from data_ingestion import PriceAdapter, PriceTick
from feature_engineering import NormalizedTick, RollingWindowStore, normalize_ticks
from model_inference import ModelRegistry


@dataclass(frozen=True)
class ArbitrageOpportunity:
    symbol: str
    exchange_buy: str
    exchange_sell: str
    spread_bps: float
    adjusted_spread_bps: float
    confidence: float
    sentiment_label: Optional[str]
    sentiment_confidence: Optional[float]
    anomaly_score: Optional[float]
    timestamp: datetime


class ArbitrageEngine:
    def __init__(self, config: EngineConfig, adapters: Dict[str, PriceAdapter]) -> None:
        self._config = config
        self._adapters = adapters
        self._store = RollingWindowStore(config.window_seconds)
        self._models = ModelRegistry.get(
            sentiment_model_id=config.models.sentiment_model_id,
            trend_model_id=config.models.trend_model_id,
            anomaly_model_id=config.models.anomaly_model_id,
            device=config.models.device,
            max_length=config.models.max_length,
        )

    async def ingest(self, symbols: Iterable[str]) -> None:
        """Fetch latest prices from all exchanges and normalize"""
        ticks: List[PriceTick] = []
        for adapter in self._adapters.values():
            ticks.extend(await adapter.fetch_latest(list(symbols)))
        
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

    def detect(self, symbols: Iterable[str], sentiment_text: Optional[str] = None) -> List[ArbitrageOpportunity]:
        """Detect arbitrage opportunities across exchange pairs"""
        opportunities: List[ArbitrageOpportunity] = []
        now = datetime.now(tz=timezone.utc)
        
        for symbol in symbols:
            latest = self._store.latest_by_symbol(symbol)
            if len(latest) < 2:
                continue
            
            items = list(latest.items())
            
            # Check all exchange pairs
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    exch_a, tick_a = items[i]
                    exch_b, tick_b = items[j]
                    
                    # ✅ FIX #3: Check BOTH directions for arbitrage
                    # Direction 1: Buy on A, Sell on B
                    spread_ab = self._calculate_spread_bps(tick_a.price, tick_b.price, "buy_a_sell_b")
                    adjusted_ab = self._adjust_spread(exch_a, exch_b, spread_ab)
                    
                    if adjusted_ab >= self._config.spread_threshold_bps:
                        confidence, sent_label, sent_conf, anomaly_score = self._confidence(symbol, sentiment_text)
                        opportunities.append(
                            ArbitrageOpportunity(
                                symbol=symbol,
                                exchange_buy=exch_a,
                                exchange_sell=exch_b,
                                spread_bps=spread_ab,
                                adjusted_spread_bps=adjusted_ab,
                                confidence=confidence,
                                sentiment_label=sent_label,
                                sentiment_confidence=sent_conf,
                                anomaly_score=anomaly_score,
                                timestamp=now,
                            )
                        )
                    
                    # Direction 2: Buy on B, Sell on A
                    spread_ba = self._calculate_spread_bps(tick_b.price, tick_a.price, "buy_b_sell_a")
                    adjusted_ba = self._adjust_spread(exch_b, exch_a, spread_ba)
                    
                    if adjusted_ba >= self._config.spread_threshold_bps:
                        confidence, sent_label, sent_conf, anomaly_score = self._confidence(symbol, sentiment_text)
                        opportunities.append(
                            ArbitrageOpportunity(
                                symbol=symbol,
                                exchange_buy=exch_b,
                                exchange_sell=exch_a,
                                spread_bps=spread_ba,
                                adjusted_spread_bps=adjusted_ba,
                                confidence=confidence,
                                sentiment_label=sent_label,
                                sentiment_confidence=sent_conf,
                                anomaly_score=anomaly_score,
                                timestamp=now,
                            )
                        )
        
        return opportunities

    def _calculate_spread_bps(self, buy_price: float, sell_price: float, direction: str) -> float:
        """
        ✅ FIX #3: Correctly calculate spread for arbitrage
        
        Arbitrage profit = (sell_price - buy_price) / buy_price
        
        Example:
        - Buy BTC on Binance @ $70,000
        - Sell BTC on Coinbase @ $70,250
        - Spread = (70250 - 70000) / 70000 * 10000 = 35.7 bps (0.357%)
        """
        if buy_price <= 0:
            return 0.0
        
        spread_percent = (sell_price - buy_price) / buy_price
        return spread_percent * 10_000  # Convert to basis points

    def _adjust_spread(self, buy_exchange: str, sell_exchange: str, spread_bps: float) -> float:
        """Adjust spread for fees and latency penalties"""
        buy_cfg = self._config.exchanges.get(
            buy_exchange, ExchangeConfig(name=buy_exchange)
        )
        sell_cfg = self._config.exchanges.get(
            sell_exchange, ExchangeConfig(name=sell_exchange)
        )
        
        # Total fees = buy taker fee + sell taker fee
        fee_bps = buy_cfg.taker_fee_bps + sell_cfg.taker_fee_bps
        
        # Latency penalty (conservative estimate: 0.01 bps per ms)
        latency_bps = min(
            (buy_cfg.latency_ms + sell_cfg.latency_ms) * 0.01,
            self._config.max_latency_penalty_bps,
        )
        
        return spread_bps - fee_bps - latency_bps

    def _confidence(
        self, symbol: str, sentiment_text: Optional[str]
    ) -> tuple[float, Optional[str], Optional[float], Optional[float]]:
        """
        Calculate AI confidence score combining:
        1. Volatility (lower = better)
        2. Trend forecast (stable = better)  
        3. Anomaly detection (normal = better)
        4. Sentiment (positive = better)
        """
        confidence = 1.0
        sent_label: Optional[str] = None
        sent_conf: Optional[float] = None
        anomaly_score: Optional[float] = None

        # Collect price series across all exchanges
        series = []
        for exchange in self._adapters.keys():
            ticks = self._store.get_series(exchange, symbol)
            if ticks:
                series.extend([tick.price for tick in ticks])

        # ✅ FIX #4: Apply AI scoring if sufficient data
        if len(series) >= self._config.min_points:
            series_trimmed = series[-self._config.min_points:]
            
            # Volatility penalty
            series_pd = pd.Series(series_trimmed)
            volatility = float(series_pd.pct_change().abs().mean())
            
            # Trend forecast
            try:
                forecast = self._models.forecast_trend(series_trimmed)
                delta = abs(forecast.mean - series_trimmed[-1]) / max(series_trimmed[-1], 1e-6)
                confidence *= float(np.clip(1.0 - delta - volatility, 0.3, 1.0))
            except Exception:
                # Model inference failed - use neutral confidence
                confidence *= 0.7
            
            # Anomaly detection
            try:
                anomaly = self._models.score_anomaly(series_trimmed)
                anomaly_score = anomaly.score
                
                if anomaly_score > self._config.anomaly_threshold:
                    confidence *= 0.5  # High anomaly = risky trade
            except Exception:
                anomaly_score = 0.0

        else:
            # Insufficient historical data - reduce confidence
            confidence *= 0.6

        # Sentiment analysis
        if sentiment_text:
            try:
                sentiment = self._models.score_sentiment(sentiment_text)
                sent_label = sentiment.label
                sent_conf = sentiment.confidence
                
                if sent_label in {"negative", "bearish"}:
                    confidence *= 0.8
                elif sent_label in {"positive", "bullish"}:
                    confidence *= 1.05
            except Exception:
                # Sentiment model failed - ignore
                pass

        return float(np.clip(confidence, 0.0, 1.0)), sent_label, sent_conf, anomaly_score