from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from arbitrage_engine import ArbitrageEngine
from config import EngineConfig, ExchangeConfig, ModelConfig
from data_ingestion import DummyAdapter, PriceAdapter


app = FastAPI(title="Crypto Arbitrage Monitor")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

_engine: Optional[ArbitrageEngine] = None
_lock = asyncio.Lock()


def build_adapters() -> Dict[str, PriceAdapter]:
    """Build dummy adapters with realistic price variations"""
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
            ("BTC/USDT", 70250.0),  # 0.36% higher - profitable arbitrage
            ("ETH/USDT", 2490.0),   # 0.4% lower
            ("SOL/USDT", 111.2),    # 1.09% higher
            ("XRP/USDT", 0.60),     # 3.2% lower
        ],
    )
    adapter_c = DummyAdapter(
        exchange="kraken",
        prices=[
            ("BTC/USDT", 70120.0),  # 0.17% higher
            ("ETH/USDT", 2515.0),   # 0.6% higher  
            ("SOL/USDT", 109.4),    # 0.55% lower
            ("XRP/USDT", 0.625),    # 0.8% higher
        ],
    )
    return {"binance": adapter_a, "coinbase": adapter_b, "kraken": adapter_c}


def build_config() -> EngineConfig:
    """Build configuration with ALL symbols enabled"""
    return EngineConfig(
        # ✅ FIX #1: Include all 4 symbols your adapters support
        symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"],
        window_seconds=120,
        min_points=8,  # ✅ FIX #4: Reduced from 16 to allow faster confidence scoring
        spread_threshold_bps=5.0,  # 0.05% minimum
        exchanges={
            "binance": ExchangeConfig(name="binance", taker_fee_bps=7.5, latency_ms=80.0),
            "coinbase": ExchangeConfig(name="coinbase", taker_fee_bps=10.0, latency_ms=120.0),
            "kraken": ExchangeConfig(name="kraken", taker_fee_bps=9.0, latency_ms=110.0),
        },
        models=ModelConfig(
            sentiment_model_id="ProsusAI/finbert",
            trend_model_id="huggingface/time-series-transformer-tourism-monthly",
            anomaly_model_id="ibm-research/patchtst-etth1-pretrain",
            device="cpu",
        ),
    )


@app.on_event("startup")
async def _startup() -> None:
    """Initialize engine - models cached after first download"""
    global _engine
    print("🚀 Initializing Arbitrage Engine...")
    print("⏳ First run: downloading models (~1 min). Subsequent runs: instant.")
    _engine = ArbitrageEngine(config=build_config(), adapters=build_adapters())
    
    # ✅ FIX #4: Pre-populate store with historical data for confidence scoring
    config = build_config()
    for _ in range(10):  # Simulate 10 ticks of history
        await _engine.ingest(symbols=config.symbols)
        await asyncio.sleep(0.01)
    
    print("✅ Engine ready!")


@app.get("/")
async def index(request: Request):
    """Render main dashboard"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/opportunities", response_class=JSONResponse)
async def api_opportunities(sentiment_text: Optional[str] = None) -> JSONResponse:
    """Fetch current arbitrage opportunities with AI scoring"""
    if not _engine:
        return JSONResponse(status_code=503, content={"error": "Engine not initialized"})
    
    config = build_config()
    async with _lock:
        # Ingest latest prices
        await _engine.ingest(symbols=config.symbols)
        
        # Detect arbitrage opportunities
        opportunities = _engine.detect(symbols=config.symbols, sentiment_text=sentiment_text)
    
    # Format response
    payload = [
        {
            "symbol": opp.symbol,
            "exchange_buy": opp.exchange_buy,
            "exchange_sell": opp.exchange_sell,
            "spread_bps": round(opp.spread_bps, 2),
            "adjusted_spread_bps": round(opp.adjusted_spread_bps, 2),
            "confidence": round(opp.confidence, 3),
            "sentiment": {
                "label": opp.sentiment_label,
                "confidence": round(opp.sentiment_confidence, 3) if opp.sentiment_confidence else None,
            },
            "anomaly_score": round(opp.anomaly_score, 3) if opp.anomaly_score else None,
            "timestamp": opp.timestamp.astimezone(timezone.utc).isoformat(),
        }
        for opp in opportunities
    ]
    
    return JSONResponse(
        content={
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "count": len(payload),
            "opportunities": payload,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)