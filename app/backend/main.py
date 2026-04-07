"""
backend/main.py
Alpha-Stream FastAPI backend.

Run (from app\backend directory):
    uvicorn main:app --reload --port 8000

Endpoints:
    GET  /api/universes          — list available universes
    GET  /api/regime             — Stage 0: market fragility (TTL 15 min)
    GET  /api/macro              — Stage 1: global macro (TTL 30 min)
    GET  /api/sectors/{universe} — Stage 2: sector screener (TTL 30 min)
    GET  /api/rankings/{universe}— return cached ranking results
    POST /api/scan/start         — launch a background full scan
    GET  /api/scan/status/{id}   — poll scan progress
    GET  /api/scan/stream/{id}   — SSE stream of scan progress (for live progress bar)
    DELETE /api/cache            — invalidate all caches (admin)
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional
from uuid import uuid4

# Add project root (alphas/) to sys.path so src.agents.* imports resolve
# regardless of which directory uvicorn is launched from.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from cache import TTLCache
from pipeline import (
    analyze_ticker,
    fetch_macro,
    fetch_regime,
    fetch_sectors,
    get_universe_info,
)
from schemas import (
    MacroResponse,
    RankingsResponse,
    RegimeResponse,
    ScanProgress,
    ScanResult,
    SectorsResponse,
    TickerRow,
    UniversesResponse,
)
from src.agents.sector_screener import UNIVERSE_REGISTRY


# ─────────────────────────────────────────────────────────────
# GLOBAL STATE
# ─────────────────────────────────────────────────────────────

cache: TTLCache = TTLCache()

# In-memory scan job store: {job_id: dict}
_scan_jobs: dict[str, dict] = {}


def _make_job(universe: str, total: int = 0) -> dict:
    return {
        "job_id":       str(uuid4()),
        "status":       "pending",
        "universe":     universe,
        "total":        total,
        "completed":    0,
        "progress_pct": 0.0,
        "started_at":   datetime.utcnow().isoformat(),
        "completed_at": None,
        "error":        None,
        "results":      [],
        "errors":       [],
    }


def _job_progress_pct(job: dict) -> float:
    if job["total"] == 0:
        return 0.0
    return round(job["completed"] / job["total"] * 100, 1)


# ─────────────────────────────────────────────────────────────
# LIFESPAN
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    _scan_jobs.clear()
    cache.clear()


# ─────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Alpha-Stream Quantitative Terminal",
    description = "Institutional pipeline API — Stages 0–4",
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],   # tightened after frontend URL is known (Part 5)
    allow_credentials = False,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _clean_floats(obj):
    """Recursively replace NaN/Inf with None so JSON serialisation never breaks."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _clean_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_floats(i) for i in obj]
    return obj


def _build_rankings_response(
    universe_key:   str,
    ok_rows:        list[dict],
    err_rows:       list[dict],
    composite_risk: float,
    macro:          dict,
) -> RankingsResponse:
    ticker_rows = []
    for r in ok_rows:
        ticker_rows.append(TickerRow(
            ticker       = r["ticker"],
            sector       = r.get("sector", "UNKNOWN"),
            price        = r.get("price"),
            alpha        = r.get("alpha", 0.0),
            roic         = r.get("roic"),
            wacc         = r.get("wacc"),
            moat         = r.get("moat"),
            z            = r.get("z"),
            sloan        = r.get("sloan"),
            fcf_q        = r.get("fcf_q"),
            beta         = r.get("beta"),
            cvar         = r.get("cvar"),
            sortino      = r.get("sortino"),
            a_turn       = r.get("a_turn"),
            ccc          = r.get("ccc"),
            sector_score = r.get("sector_score", 50.0),
            sector_adj   = r.get("sector_adj", 0),
            strategy     = r.get("strategy", "N/A"),
            regime_fit   = r.get("regime_fit"),
            signal_str   = r.get("signal_str", 0),
            rr           = r.get("rr", 0.0),
            entry        = r.get("entry"),
            tp           = r.get("tp"),
            sl           = r.get("sl"),
            atr          = r.get("atr"),
            gate3        = r.get("gate3", False),
            gate4        = r.get("gate4", False),
            rank_score   = r.get("rank_score", 0.0),
            verdict      = r.get("verdict", "FAIL"),
        ))

    cfg = UNIVERSE_REGISTRY[universe_key]
    return RankingsResponse(
        universe       = cfg["display_name"],
        total_scanned  = len(ok_rows),
        buy_count      = sum(1 for r in ok_rows if r.get("gate3") and r.get("gate4")),
        failed_count   = len(err_rows),
        composite_risk = composite_risk,
        macro_regime   = macro.get("macro_regime", "UNKNOWN"),
        cycle_quadrant = macro.get("cycle_quadrant", "UNKNOWN"),
        rows           = ticker_rows,
        errors         = [{"ticker": e["ticker"], "error": e.get("error", "")} for e in err_rows],
    )


# ─────────────────────────────────────────────────────────────
# BACKGROUND SCAN TASK
# ─────────────────────────────────────────────────────────────

async def _run_scan(job_id: str, universe_key: str) -> None:
    job = _scan_jobs[job_id]
    job["status"] = "running"

    try:
        cfg     = UNIVERSE_REGISTRY[universe_key]
        tickers = list(dict.fromkeys(
            t for s in cfg["universe"].values() for t in s["members"]
        ))
        job["total"] = len(tickers)

        # ── Shared context (Stages 0–2) ───────────────────────
        regime_data = await asyncio.to_thread(fetch_regime)
        composite_risk = regime_data["composite_risk"]

        macro = cache.get(f"macro")
        if macro is None:
            macro = await asyncio.to_thread(fetch_macro)
            cache.set("macro", macro, ttl_seconds=1800)

        sector_data = await asyncio.to_thread(fetch_sectors, universe_key, macro)
        sector_scores = {
            s["sector"]: s["sector_score"]
            for s in sector_data["ranked_sectors"]
        }

        # ── Per-ticker scan (Stages 3+4) ──────────────────────
        sem = asyncio.Semaphore(8)

        async def _process(ticker: str) -> dict:
            async with sem:
                result = await asyncio.to_thread(
                    analyze_ticker,
                    ticker, composite_risk, macro, sector_scores, cfg["universe"],
                )
                job["completed"] += 1
                job["progress_pct"] = _job_progress_pct(job)
                if result["ok"]:
                    job["results"].append(_clean_floats(result))
                else:
                    job["errors"].append({"ticker": ticker, "error": result.get("error", "")})
                return result

        tasks = [asyncio.create_task(_process(t)) for t in tickers]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Sort: BUY first, then by rank_score descending
        job["results"].sort(
            key=lambda r: (-(r.get("gate3", False) and r.get("gate4", False)),
                           -r.get("rank_score", 0))
        )

        # Build final response and cache it
        rankings = _build_rankings_response(
            universe_key   = universe_key,
            ok_rows        = job["results"],
            err_rows       = job["errors"],
            composite_risk = composite_risk,
            macro          = macro,
        )
        cache.set(f"rankings_{universe_key}", rankings, ttl_seconds=3600)

        job["status"]       = "completed"
        job["completed_at"] = datetime.utcnow().isoformat()
        job["progress_pct"] = 100.0

    except Exception as exc:
        job["status"] = "failed"
        job["error"]  = str(exc)


# ─────────────────────────────────────────────────────────────
# ROUTES — UNIVERSES
# ─────────────────────────────────────────────────────────────

@app.get("/api/universes", response_model=UniversesResponse, tags=["Config"])
async def list_universes():
    """Return all available stock universes."""
    return UniversesResponse(universes=get_universe_info())


# ─────────────────────────────────────────────────────────────
# ROUTES — STAGE 0: REGIME
# ─────────────────────────────────────────────────────────────

@app.get("/api/regime", response_model=RegimeResponse, tags=["Stage 0"])
async def get_regime(refresh: bool = Query(False, description="Force cache refresh")):
    """
    Stage 0 — Market Fragility Monitor.
    SPX 200DMA · Yield curve · HY credit · Breadth · VIX
    Cached for 15 minutes.
    """
    if not refresh:
        cached = cache.get("regime")
        if cached is not None:
            return cached

    data   = await asyncio.to_thread(fetch_regime)
    result = RegimeResponse(**data)
    cache.set("regime", result, ttl_seconds=900)
    return result


# ─────────────────────────────────────────────────────────────
# ROUTES — STAGE 1: MACRO
# ─────────────────────────────────────────────────────────────

@app.get("/api/macro", response_model=MacroResponse, tags=["Stage 1"])
async def get_macro(refresh: bool = Query(False)):
    """
    Stage 1 — Global Macro (8 signals, weighted composite, cycle quadrant).
    Cached for 30 minutes.
    """
    if not refresh:
        cached = cache.get("macro")
        if cached is not None:
            return cached

    raw = await asyncio.to_thread(fetch_macro)

    def _sig(d: dict) -> dict:
        """Flatten a signal sub-dict, filling optional fields."""
        return {
            "ticker":           d.get("ticker", "N/A"),
            "current_price":    d.get("current_price"),
            "mom_20d_pct":      d.get("mom_20d_pct"),
            "mom_60d_pct":      d.get("mom_60d_pct"),
            "z_score_60d":      d.get("z_score_60d"),
            "signal":           d.get("signal", "N/A"),
            "risk_score":       d.get("risk_score", 50),
            "macro_bias":       d.get("macro_bias", "NEUTRAL"),
            "yield_level":      d.get("yield_level"),
            "yield_chg_20d":    d.get("yield_chg_20d"),
            "real_yield_rising":d.get("real_yield_rising"),
            "tip_mom_20d":      d.get("tip_mom_20d"),
            "usdthb_rate":      d.get("usdthb_rate"),
            "eem_mom_20d":      d.get("eem_mom_20d"),
            "spy_mom_20d":      d.get("spy_mom_20d"),
            "em_alpha_20d":     d.get("em_alpha_20d"),
            "thd_mom_20d":      d.get("thd_mom_20d"),
            "mchi_mom_60d":     d.get("mchi_mom_60d"),
            "kweb_mom_20d":     d.get("kweb_mom_20d"),
            "note":             d.get("note"),
        }

    result = MacroResponse(
        real_yield            = _sig(raw["real_yield"]),
        dxy                   = _sig(raw["dxy"]),
        thb                   = _sig(raw["thb"]),
        crude_oil             = _sig(raw["crude_oil"]),
        copper                = _sig(raw["copper"]),
        gold                  = _sig(raw["gold"]),
        em_flows              = _sig(raw["em_flows"]),
        china                 = _sig(raw["china"]),
        composite_macro_risk  = raw["composite_macro_risk"],
        macro_regime          = raw["macro_regime"],
        cycle_quadrant        = raw["cycle_quadrant"],
        quadrant_advice       = raw["quadrant_advice"],
        copper_gold_ratio     = raw["copper_gold_ratio"],
        macro_bias_summary    = raw["macro_bias_summary"],
        sector_adjustments    = raw["sector_adjustments"],
        raw_scores            = raw["raw_scores"],
        signal_weights        = raw["signal_weights"],
    )
    cache.set("macro", raw, ttl_seconds=1800)   # store raw dict for pipeline reuse
    cache.set("macro_response", result, ttl_seconds=1800)
    return result


# ─────────────────────────────────────────────────────────────
# ROUTES — STAGE 2: SECTORS
# ─────────────────────────────────────────────────────────────

@app.get("/api/sectors/{universe}", response_model=SectorsResponse, tags=["Stage 2"])
async def get_sectors(
    universe: str,
    refresh:  bool = Query(False),
):
    """
    Stage 2 — Sector Screener.
    universe: SET100 | WATCHLIST
    Cached for 30 minutes.
    """
    if universe not in UNIVERSE_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Universe '{universe}' not found.")

    cache_key = f"sectors_{universe}"
    if not refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    macro_raw = cache.get("macro")
    if macro_raw is None:
        macro_raw = await asyncio.to_thread(fetch_macro)
        cache.set("macro", macro_raw, ttl_seconds=1800)

    raw    = await asyncio.to_thread(fetch_sectors, universe, macro_raw)
    result = SectorsResponse(
        universe        = raw["universe"],
        sector_gate     = raw["sector_gate"],
        sector_rotation = raw["sector_rotation"],
        top_sectors     = raw["top_sectors"],
        avoid_sectors   = raw["avoid_sectors"],
        ranked_sectors  = raw["ranked_sectors"],
    )
    cache.set(cache_key, result, ttl_seconds=1800)
    return result


# ─────────────────────────────────────────────────────────────
# ROUTES — SCAN: START / STATUS / STREAM / RESULTS
# ─────────────────────────────────────────────────────────────

@app.post("/api/scan/start", response_model=ScanProgress, tags=["Scan"])
async def start_scan(universe: str = Query("SET100", description="SET100 | WATCHLIST")):
    """
    Launch a background full-universe scan (Stages 0–4 for every ticker).
    Returns a job_id to poll for progress.
    """
    if universe not in UNIVERSE_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Universe '{universe}' not found.")

    job      = _make_job(universe)
    job_id   = job["job_id"]
    _scan_jobs[job_id] = job

    asyncio.create_task(_run_scan(job_id, universe))

    return ScanProgress(
        job_id       = job_id,
        status       = "pending",
        universe     = universe,
        total        = 0,
        completed    = 0,
        progress_pct = 0.0,
        started_at   = datetime.utcnow(),
    )


@app.get("/api/scan/status/{job_id}", response_model=ScanProgress, tags=["Scan"])
async def scan_status(job_id: str):
    """Poll the progress of a running scan job."""
    job = _scan_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return ScanProgress(
        job_id       = job["job_id"],
        status       = job["status"],
        universe     = job["universe"],
        total        = job["total"],
        completed    = job["completed"],
        progress_pct = job["progress_pct"],
        started_at   = datetime.fromisoformat(job["started_at"]),
        completed_at = datetime.fromisoformat(job["completed_at"]) if job["completed_at"] else None,
        error        = job.get("error"),
    )


@app.get("/api/scan/stream/{job_id}", tags=["Scan"])
async def scan_stream(job_id: str):
    """
    Server-Sent Events stream for real-time scan progress.
    The frontend connects once and receives progress updates every second
    until status is 'completed' or 'failed'.

    Event format:  data: <JSON>\n\n
    """
    if job_id not in _scan_jobs:
        raise HTTPException(status_code=404, detail="Job not found.")

    async def _generate() -> AsyncGenerator[str, None]:
        while True:
            job = _scan_jobs.get(job_id)
            if job is None:
                break
            payload = {
                "job_id":       job["job_id"],
                "status":       job["status"],
                "universe":     job["universe"],
                "total":        job["total"],
                "completed":    job["completed"],
                "progress_pct": job["progress_pct"],
                "started_at":   job["started_at"],
                "completed_at": job["completed_at"],
                "error":        job.get("error"),
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if job["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        _generate(),
        media_type = "text/event-stream",
        headers    = {
            "Cache-Control":              "no-cache",
            "X-Accel-Buffering":          "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/api/rankings/{universe}", response_model=RankingsResponse, tags=["Rankings"])
async def get_rankings(universe: str):
    """
    Return the most recent completed rankings for the given universe.
    Trigger a scan first via POST /api/scan/start if no results exist.
    """
    if universe not in UNIVERSE_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Universe '{universe}' not found.")

    cached = cache.get(f"rankings_{universe}")
    if cached is not None:
        return cached

    raise HTTPException(
        status_code = 404,
        detail      = "No ranking results cached. Start a scan first via POST /api/scan/start.",
    )


# ─────────────────────────────────────────────────────────────
# ROUTES — PRICE HISTORY
# ─────────────────────────────────────────────────────────────

@app.get("/api/price/{ticker}", tags=["Price"])
async def get_price_history(ticker: str, period: str = Query("3mo")):
    """
    Return daily OHLCV bars for a ticker (via yfinance).
    period: 1mo | 3mo | 6mo | 1y | 2y
    Cached for 1 hour.
    """
    cache_key = f"price_{ticker}_{period}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    import yfinance as yf

    def _fetch():
        df = yf.download(ticker, period=period, interval="1d",
                         auto_adjust=True, progress=False, multi_level_index=False)
        if df.empty:
            return None
        bars = []
        for ts, row in df.iterrows():
            try:
                o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
                if any(math.isnan(v) for v in [o, h, l, c]):
                    continue
                vol = float(row.get("Volume", 0) or 0)
                bars.append({"time": ts.strftime("%Y-%m-%d"), "open": o, "high": h, "low": l, "close": c, "volume": vol})
            except Exception:
                continue
        return bars

    bars = await asyncio.to_thread(_fetch)
    if not bars:
        raise HTTPException(status_code=404, detail=f"No price data for {ticker}")

    result = {"ticker": ticker, "bars": bars}
    cache.set(cache_key, result, ttl_seconds=3600)
    return result


# ─────────────────────────────────────────────────────────────
# ROUTES — MARKET OVERVIEW
# ─────────────────────────────────────────────────────────────

@app.get("/api/market-overview", tags=["Market"])
async def get_market_overview():
    """
    Return price, change%, and 30-day sparkline for key indices:
    SET (^SET.BK), S&P 500 (^GSPC), Gold (GC=F), Crude Oil (CL=F).
    Cached for 5 minutes.
    """
    cache_key = "market_overview"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    import yfinance as yf

    INSTRUMENTS = [
        {"id": "SET",       "name": "SET Index",  "ticker": "^SET.BK"},
        {"id": "SP500",     "name": "S&P 500",    "ticker": "^GSPC"},
        {"id": "GOLD",      "name": "Gold",       "ticker": "GC=F"},
        {"id": "CRUDE",     "name": "Crude Oil",  "ticker": "CL=F"},
    ]

    def _fetch():
        rows = []
        for inst in INSTRUMENTS:
            try:
                tk = yf.Ticker(inst["ticker"])
                df = tk.history(period="35d", interval="1d", auto_adjust=True)
                if df.empty or len(df) < 2:
                    rows.append({**inst, "price": None, "change": None, "change_pct": None, "sparkline": []})
                    continue
                closes = df["Close"].dropna().tolist()
                price  = closes[-1]
                prev   = closes[-2]
                change     = price - prev
                change_pct = (change / prev * 100) if prev else 0.0
                sparkline  = [round(v, 4) for v in closes[-30:]]
                rows.append({
                    **inst,
                    "price":      round(price, 4),
                    "change":     round(change, 4),
                    "change_pct": round(change_pct, 4),
                    "sparkline":  sparkline,
                })
            except Exception as e:
                rows.append({**inst, "price": None, "change": None, "change_pct": None, "sparkline": [], "error": str(e)})
        return {"instruments": _clean_floats(rows)}

    result = await asyncio.to_thread(_fetch)
    cache.set(cache_key, result, ttl_seconds=300)
    return result


# ─────────────────────────────────────────────────────────────
# ROUTES — WATCHLIST
# ─────────────────────────────────────────────────────────────

@app.get("/api/watchlist", tags=["Market"])
async def get_watchlist(tickers: str = Query(..., description="Comma-separated tickers, e.g. AAPL,MSFT")):
    """
    Return last price and day/week/month/year % change for a list of tickers.
    Cached for 5 minutes per unique ticker set.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="No tickers provided.")

    cache_key = f"watchlist_{','.join(sorted(ticker_list))}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    import yfinance as yf

    def _fetch():
        rows = []
        for ticker in ticker_list:
            try:
                df = yf.download(ticker, period="13mo", interval="1d",
                                 auto_adjust=True, progress=False, multi_level_index=False)
                if df.empty:
                    rows.append({"ticker": ticker, "price": None, "day_pct": None, "week_pct": None, "month_pct": None, "year_pct": None})
                    continue
                closes = df["Close"].dropna()
                price = float(closes.iloc[-1])

                def _pct(n):
                    if len(closes) > n:
                        ref = float(closes.iloc[-(n+1)])
                        return round((price - ref) / ref * 100, 2) if ref else None
                    return None

                rows.append({
                    "ticker":     ticker,
                    "price":      round(price, 4),
                    "day_pct":    _pct(1),
                    "week_pct":   _pct(5),
                    "month_pct":  _pct(21),
                    "year_pct":   _pct(252),
                })
            except Exception as e:
                rows.append({"ticker": ticker, "price": None, "day_pct": None, "week_pct": None, "month_pct": None, "year_pct": None, "error": str(e)})
        return {"rows": _clean_floats(rows)}

    result = await asyncio.to_thread(_fetch)
    cache.set(cache_key, result, ttl_seconds=300)
    return result


# ─────────────────────────────────────────────────────────────
# ROUTES — TICKER PROFILE
# ─────────────────────────────────────────────────────────────

@app.get("/api/ticker/profile/{ticker}", tags=["Ticker"])
async def get_ticker_profile(ticker: str):
    """
    Return cleaned yfinance .info dict for a ticker.
    Cached for 1 hour.
    """
    cache_key = f"profile_{ticker}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    import yfinance as yf

    def _fetch():
        tk   = yf.Ticker(ticker)
        info = dict(tk.info)
        KEEP = [
            "shortName", "longName", "symbol", "exchange", "quoteType",
            "sector", "industry", "country", "currency", "website",
            "longBusinessSummary",
            "marketCap", "enterpriseValue", "trailingPE", "forwardPE",
            "priceToBook", "priceToSalesTrailing12Months",
            "profitMargins", "operatingMargins", "grossMargins",
            "returnOnEquity", "returnOnAssets",
            "totalRevenue", "revenueGrowth", "earningsGrowth",
            "totalDebt", "debtToEquity", "currentRatio", "quickRatio",
            "freeCashflow", "operatingCashflow",
            "dividendYield", "payoutRatio",
            "beta", "52WeekChange", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
            "averageVolume", "averageVolume10days",
            "fullTimeEmployees", "auditRisk", "boardRisk", "compensationRisk",
            "sharesOutstanding", "floatShares", "heldPercentInsiders", "heldPercentInstitutions",
            "shortRatio", "shortPercentOfFloat",
            "recommendationKey", "numberOfAnalystOpinions",
            "targetMeanPrice", "targetHighPrice", "targetLowPrice",
        ]
        cleaned = {k: info[k] for k in KEEP if k in info}
        return _clean_floats({"ticker": ticker, "profile": cleaned})

    result = await asyncio.to_thread(_fetch)
    cache.set(cache_key, result, ttl_seconds=3600)
    return result


# ─────────────────────────────────────────────────────────────
# ROUTES — TICKER INFO (summary metrics + sparkline)
# ─────────────────────────────────────────────────────────────

@app.get("/api/ticker/info/{ticker}", tags=["Ticker"])
async def get_ticker_info(ticker: str):
    """
    Return summary metrics and a 14-day close sparkline for a ticker.
    Cached for 5 minutes.
    """
    cache_key = f"ticker_info_{ticker}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    import yfinance as yf

    def _fetch():
        tk   = yf.Ticker(ticker)
        info = dict(tk.info)
        df   = tk.history(period="20d", interval="1d", auto_adjust=True)

        closes = df["Close"].dropna().tolist() if not df.empty else []
        price  = closes[-1]  if closes else None
        prev   = closes[-2]  if len(closes) >= 2 else None
        change     = (price - prev) if price and prev else None
        change_pct = (change / prev * 100) if change and prev else None

        return _clean_floats({
            "ticker":      ticker,
            "price":       round(price, 4) if price else None,
            "change":      round(change, 4) if change else None,
            "change_pct":  round(change_pct, 4) if change_pct else None,
            "volume":      info.get("regularMarketVolume") or info.get("averageVolume"),
            "avg_volume":  info.get("averageVolume"),
            "market_cap":  info.get("marketCap"),
            "sector":      info.get("sector"),
            "industry":    info.get("industry"),
            "country":     info.get("country"),
            "currency":    info.get("currency"),
            "sparkline":   [round(v, 4) for v in closes[-14:]],
        })

    result = await asyncio.to_thread(_fetch)
    cache.set(cache_key, result, ttl_seconds=300)
    return result


# ─────────────────────────────────────────────────────────────
# ROUTES — BACKTESTING
# ─────────────────────────────────────────────────────────────

from pydantic import BaseModel as _BaseModel

class BacktestRequest(_BaseModel):
    strategy:           str   = "MomentumStrategy"
    universe:           str   = "SP500_SAMPLE"
    optimizer:          str   = "EqualWeightOptimizer"
    max_stop_loss_pct:  float = 5.0
    initial_capital:    float = 1_000_000.0
    period_years:       int   = 3


@app.post("/api/backtest/run", tags=["Backtest"])
async def run_backtest_endpoint(req: BacktestRequest):
    """
    Run a walk-forward backtest.
    Returns equity_curve, benchmark_curve, fold_boundaries, metrics, and trade_log_summary.
    """
    from src.strategies import STRATEGY_MAP
    from src.universes import UNIVERSE_MAP
    from src.backtesting.optimizers import OPTIMIZER_MAP
    from src.backtesting.data_loader import load_prices
    from src.backtesting.engine import run_backtest

    # Validate inputs
    if req.strategy not in STRATEGY_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown strategy '{req.strategy}'. Valid: {list(STRATEGY_MAP)}")
    if req.optimizer not in OPTIMIZER_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown optimizer '{req.optimizer}'. Valid: {list(OPTIMIZER_MAP)}")
    if req.universe not in UNIVERSE_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown universe '{req.universe}'. Valid: {list(UNIVERSE_MAP)}")
    if not (1 <= req.period_years <= 15):
        raise HTTPException(status_code=400, detail="period_years must be between 1 and 15.")

    universe   = UNIVERSE_MAP[req.universe]
    strategy   = STRATEGY_MAP[req.strategy]()
    optimizer  = OPTIMIZER_MAP[req.optimizer]()

    def _execute():
        # Load prices (universe tickers + benchmark)
        prices = load_prices(
            tickers=universe.tickers,
            period_years=req.period_years + 2,   # extra for warm-up
            extra_tickers=[universe.benchmark_ticker],
        )

        # Separate benchmark
        bm_ticker = universe.benchmark_ticker
        if bm_ticker in prices.columns:
            benchmark_prices = prices[bm_ticker]
            asset_prices     = prices[universe.tickers].dropna(how="all")
        else:
            # If benchmark not found, use first asset
            asset_prices     = prices[universe.tickers].dropna(how="all")
            benchmark_prices = asset_prices.iloc[:, 0]

        result = run_backtest(
            prices            = asset_prices,
            benchmark_prices  = benchmark_prices,
            strategy          = strategy,
            optimizer         = optimizer,
            initial_capital   = req.initial_capital,
            max_stop_loss_pct = req.max_stop_loss_pct / 100.0,
        )
        return result

    try:
        result = await asyncio.to_thread(_execute)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")

    # Serialize equity curve
    equity_dict    = {d.strftime("%Y-%m-%d"): round(v, 2) for d, v in result.equity_curve.items() if not math.isnan(v)}
    benchmark_dict = {d.strftime("%Y-%m-%d"): round(v, 2) for d, v in result.benchmark_curve.items() if not math.isnan(v)}

    # Fold boundaries (first date of each fold's test period)
    fold_boundaries: list[str] = []
    for s in result.fold_returns:
        if len(s) > 0:
            fold_boundaries.append(s.index[0].strftime("%Y-%m-%d"))

    trade_log_summary = {
        "total_trades":  result.metrics.get("total_trades", 0),
        "long_trades":   result.metrics.get("long_trades", 0),
        "short_trades":  result.metrics.get("short_trades", 0),
    }

    # Positions chart — sample to ≤150 points, active tickers only
    wh = result.weights_history
    sample_step = max(1, len(wh) // 150)
    wh_sampled  = wh.iloc[::sample_step]
    # Only tickers that held a non-zero position at some point
    active_cols = wh_sampled.columns[(wh_sampled.abs() > 1e-4).any()].tolist()
    positions_chart = []
    for date, row in wh_sampled[active_cols].iterrows():
        entry: dict = {"date": date.strftime("%Y-%m-%d")}
        entry.update({t: round(float(v), 4) for t, v in row.items()})
        positions_chart.append(entry)

    return _clean_floats({
        "equity_curve":      equity_dict,
        "benchmark_curve":   benchmark_dict,
        "fold_boundaries":   fold_boundaries,
        "metrics":           result.metrics,
        "trade_log_summary": trade_log_summary,
        "positions_chart":   positions_chart,
    })


# ─────────────────────────────────────────────────────────────
# ROUTES — ADMIN
# ─────────────────────────────────────────────────────────────

@app.delete("/api/cache", tags=["Admin"])
async def clear_cache():
    """Invalidate all caches. Forces fresh data on next request."""
    cache.clear()
    return {"message": "Cache cleared.", "stats": cache.stats()}


@app.get("/api/cache/stats", tags=["Admin"])
async def cache_stats():
    """Return cache occupancy statistics."""
    return cache.stats()


@app.get("/api/health", tags=["Admin"])
async def health():
    return {
        "status":    "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "universes": list(UNIVERSE_REGISTRY.keys()),
    }


@app.get("/api/debug/financials/{ticker}", tags=["Admin"])
async def debug_financials(ticker: str):
    """
    Temporary debug endpoint — returns raw yfinance field names for a ticker.
    Use this to diagnose ROIC/WACC = 0 for non-US tickers (.BK etc.).
    Call: GET /api/debug/financials/PTTEP.BK
    Remove once field name issues are resolved.
    """
    import yfinance as yf
    from src.data.providers import _enrich_info

    def _fetch():
        stock   = yf.Ticker(ticker)
        history = stock.history(period="5d")
        info    = _enrich_info(dict(stock.info), history)

        fin_index = list(stock.financials.index) if stock.financials is not None and not stock.financials.empty else []
        bs_index  = list(stock.balance_sheet.index) if stock.balance_sheet is not None and not stock.balance_sheet.empty else []
        cf_index  = list(stock.cashflow.index) if stock.cashflow is not None and not stock.cashflow.empty else []

        # Sample first column values for key rows
        def _sample(df, rows):
            out = {}
            if df is None or df.empty:
                return out
            for r in rows:
                if r in df.index:
                    try:
                        out[r] = float(df.loc[r].iloc[0])
                    except Exception:
                        out[r] = None
            return out

        ebit_candidates = ["EBIT", "Ebit", "Operating Income", "OperatingIncome",
                           "Income From Operations", "IncomeFromOperations"]
        rev_candidates  = ["Total Revenue", "TotalRevenue", "Revenue"]
        debt_candidates = ["Total Debt", "TotalDebt", "Long Term Debt", "LongTermDebt"]

        return {
            "ticker":              ticker,
            "financials_fields":   fin_index,
            "balance_sheet_fields":bs_index,
            "cashflow_fields":     cf_index,
            "ebit_probe":          _sample(stock.financials, ebit_candidates),
            "revenue_probe":       _sample(stock.financials, rev_candidates),
            "debt_probe":          _sample(stock.balance_sheet, debt_candidates),
            "market_cap_in_info":  info.get("marketCap"),
            "shares_outstanding":  info.get("sharesOutstanding"),
            "current_price":       info.get("currentPrice") or info.get("regularMarketPrice"),
        }

    result = await asyncio.to_thread(_fetch)
    return _clean_floats(result)
