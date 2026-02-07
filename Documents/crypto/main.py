from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from arbitrage_engine import ArbitrageEngine, ArbitrageOpportunity
from config import EngineConfig, ExchangeConfig
from data_ingestion import DummyAdapter, PriceTick, Snapshot, SnapshotStore, fetch_all


app = FastAPI(title="Crypto Arbitrage Monitor")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@dataclass(frozen=True)
class DashboardSnapshot:
    timestamp: datetime
    opportunities: list[ArbitrageOpportunity]


class DashboardStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._snapshot: Optional[DashboardSnapshot] = None

    async def update(self, snapshot: DashboardSnapshot) -> None:
        async with self._lock:
            self._snapshot = snapshot

    async def get(self) -> Optional[DashboardSnapshot]:
        async with self._lock:
            return self._snapshot


class RateLimiter:
    def __init__(self, min_interval_ms: int) -> None:
        self._min_interval = min_interval_ms / 1000.0
        self._last_seen: Dict[str, float] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        last = self._last_seen.get(key)
        if last is not None and now - last < self._min_interval:
            return False
        self._last_seen[key] = now
        return True


_engine: Optional[ArbitrageEngine] = None
_snapshot_store = SnapshotStore()
_dashboard_store = DashboardStore()
_refresh_task: Optional[asyncio.Task] = None
_rate_limiter = RateLimiter(min_interval_ms=200)


def build_adapters() -> Dict[str, DummyAdapter]:
    adapter_a = DummyAdapter(
        exchange="binance",
        prices=[
            ("BTC/USDT", 70000.0),
            ("ETH/USDT", 2500.0),
            ("SOL/USDT", 110.0),
            ("XRP/USDT", 0.62),
        ],
    )
    adapter_b = DummyAdapter(
        exchange="coinbase",
        prices=[
            ("BTC/USDT", 70250.0),
            ("ETH/USDT", 2490.0),
            ("SOL/USDT", 111.2),
            ("XRP/USDT", 0.60),
        ],
    )
    adapter_c = DummyAdapter(
        exchange="kraken",
        prices=[
            ("BTC/USDT", 70120.0),
            ("ETH/USDT", 2515.0),
            ("SOL/USDT", 109.4),
            ("XRP/USDT", 0.625),
        ],
    )
    return {"binance": adapter_a, "coinbase": adapter_b, "kraken": adapter_c}


def build_config() -> EngineConfig:
    return EngineConfig(
        symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"],
        window_seconds=120,
        refresh_interval_seconds=2,
        max_tick_age_seconds=5,
        max_timestamp_drift_seconds=2,
        spread_threshold_bps=5.0,
        exchanges={
            "binance": ExchangeConfig(name="binance", taker_fee_bps=7.5, latency_ms=80.0),
            "coinbase": ExchangeConfig(name="coinbase", taker_fee_bps=10.0, latency_ms=120.0),
            "kraken": ExchangeConfig(name="kraken", taker_fee_bps=9.0, latency_ms=110.0),
        },
    )


async def refresh_loop(config: EngineConfig, adapters: Dict[str, DummyAdapter]) -> None:
    global _engine
    _engine = ArbitrageEngine(config=config)

    while True:
        now = datetime.now(tz=timezone.utc)
        ticks = await fetch_all(adapters, config.symbols)
        _engine.ingest_ticks(ticks)

        snapshot = Snapshot(
            timestamp=now,
            ticks=_group_ticks(ticks),
        )
        await _snapshot_store.update(snapshot)

        opportunities = _engine.compute_opportunities(config.symbols, now=now)
        await _dashboard_store.update(
            DashboardSnapshot(timestamp=now, opportunities=opportunities)
        )

        await asyncio.sleep(config.refresh_interval_seconds) 


def _group_ticks(ticks: list[PriceTick]) -> Dict[str, Dict[str, PriceTick]]:
    grouped: Dict[str, Dict[str, PriceTick]] = {}
    for tick in ticks:
        grouped.setdefault(tick.exchange, {})[tick.symbol] = tick
    return grouped


def _require_token(request: Request) -> Optional[JSONResponse]:
    token = os.environ.get("ARBITRAGE_API_TOKEN")
    if not token:
        return None
    provided = request.headers.get("X-API-Token", "")
    if provided != token:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return None


def _is_local_request(request: Request) -> bool:
    if not request.client:
        return False
    return request.client.host in {"127.0.0.1", "::1", "localhost"}


@app.on_event("startup")
async def _startup() -> None:
    config = build_config()
    adapters = build_adapters()

    global _refresh_task
    _refresh_task = asyncio.create_task(refresh_loop(config, adapters))


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _refresh_task
    if _refresh_task:
        _refresh_task.cancel()


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/opportunities", response_class=JSONResponse)
async def api_opportunities(request: Request) -> JSONResponse:
    if (resp := _require_token(request)) is not None:
        return resp

    client_key = request.client.host if request.client else "unknown"
    if not _is_local_request(request):
        if not _rate_limiter.allow(client_key):
            return JSONResponse(status_code=429, content={"error": "Too Many Requests"})

    snapshot = await _dashboard_store.get()
    if not snapshot:
        return JSONResponse(status_code=503, content={"error": "Data not ready"})

    payload = [
        {
            "symbol": opp.symbol,
            "exchange_buy": opp.exchange_buy,
            "exchange_sell": opp.exchange_sell,
            "buy_price": round(opp.buy_price, 8),
            "sell_price": round(opp.sell_price, 8),
            "raw_spread_bps": round(opp.raw_spread_bps, 2),
            "net_spread_bps": round(opp.net_spread_bps, 2),
            "fees_bps": round(opp.fees_bps, 2),
            "latency_bps": round(opp.latency_bps, 2),
            "drift_ms": round(opp.drift_ms, 1),
            "score_bps": round(opp.score_bps, 2),
            "volatility_bps": round(opp.volatility_bps, 2),
            "timestamp": opp.timestamp.astimezone(timezone.utc).isoformat(),
        }
        for opp in snapshot.opportunities
    ]

    return JSONResponse(
        content={
            "timestamp": snapshot.timestamp.astimezone(timezone.utc).isoformat(),
            "count": len(payload),
            "opportunities": payload,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
