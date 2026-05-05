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
    HMMRegimeResponse,
    MacroResponse,
    RankingsResponse,
    RegimeResponse,
    ScanProgress,
    ScanResult,
    SectorsResponse,
    TickerRow,
    UniversesResponse,
)
from src.universes import UNIVERSE_REGISTRY


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
async def start_scan(universe: str = Query("SET100", description=str(list(UNIVERSE_REGISTRY)))):
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
                df = tk.history(period="10d", interval="1d", auto_adjust=True)
                if df.empty or len(df) < 2:
                    rows.append({**inst, "price": None, "change": None, "change_pct": None, "sparkline": []})
                    continue
                closes = df["Close"].dropna().tolist()
                price  = closes[-1]
                prev   = closes[-2]
                change     = price - prev
                change_pct = (change / prev * 100) if prev else 0.0
                sparkline  = [round(v, 4) for v in closes[-7:]]
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

def _infer_benchmark(ticker: str) -> str:
    """Return an appropriate benchmark ticker for a given asset ticker."""
    t = ticker.upper()
    # Crypto (yfinance format: BTC-USD, ETH-USD, etc.)
    if t.endswith("-USD") or t.endswith("-USDT") or t.endswith("-BTC"):
        return "BTC-USD"
    # Thai SET-listed stocks (.BK suffix)
    if t.endswith(".BK"):
        return "^SET.BK"
    # London Stock Exchange
    if t.endswith(".L"):
        return "^FTSE"
    # Tokyo Stock Exchange
    if t.endswith(".T"):
        return "^N225"
    # Australian Securities Exchange
    if t.endswith(".AX"):
        return "^AXJO"
    # Hong Kong
    if t.endswith(".HK"):
        return "^HSI"
    # German XETRA
    if t.endswith(".DE"):
        return "^GDAXI"
    # Toronto Stock Exchange
    if t.endswith(".TO"):
        return "^GSPTSE"
    # Default: S&P 500
    return "SPY"


class BacktestRequest(_BaseModel):
    strategy:           str        = "MomentumStrategy"
    universe:           str        = "SP500_SAMPLE"
    optimizer:          str        = "EqualWeightOptimizer"
    max_stop_loss_pct:  float      = 5.0
    initial_capital:    float      = 1_000_000.0
    period_years:       int        = 3
    # Single-ticker mode: when set, ignores universe/optimizer and tests one asset vs benchmark
    single_ticker:      str | None = None
    # Explicit benchmark for single-ticker mode; if omitted, auto-inferred from ticker suffix
    benchmark_ticker:   str | None = None


@app.get("/api/backtest/infer-benchmark", tags=["Backtest"])
async def infer_benchmark_endpoint(ticker: str):
    """Return the auto-inferred benchmark ticker for a given asset ticker."""
    return {"benchmark": _infer_benchmark(ticker.upper().strip())}


@app.post("/api/backtest/run", tags=["Backtest"])
async def run_backtest_endpoint(req: BacktestRequest):
    """
    Run a walk-forward backtest.
    Returns equity_curve, benchmark_curve, fold_boundaries, metrics, and trade_log_summary.

    Modes:
      - Universe mode (default): run strategy across a multi-asset universe with portfolio optimization.
      - Single-ticker mode (single_ticker set): run strategy on one asset, full allocation (no optimizer).
    """
    from src.strategies import STRATEGY_MAP
    from src.universes import UNIVERSE_MAP
    from src.backtesting.optimizers import OPTIMIZER_MAP
    from src.backtesting.data_loader import load_prices
    from src.backtesting.engine import run_backtest

    # Validate common inputs
    if req.strategy not in STRATEGY_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown strategy '{req.strategy}'. Valid: {list(STRATEGY_MAP)}")
    if not (1 <= req.period_years <= 15):
        raise HTTPException(status_code=400, detail="period_years must be between 1 and 15.")

    strategy = STRATEGY_MAP[req.strategy]()

    if req.single_ticker:
        # ── Single-ticker mode ────────────────────────────────────────────────
        ticker = req.single_ticker.upper().strip()
        if not ticker:
            raise HTTPException(status_code=400, detail="single_ticker cannot be empty.")

        bm_ticker = (req.benchmark_ticker.upper().strip() if req.benchmark_ticker else None) or _infer_benchmark(ticker)

        # EqualWeight on one asset = full allocation (signal → weight directly)
        optimizer = OPTIMIZER_MAP["EqualWeightOptimizer"]()

        def _execute():
            prices = load_prices(
                tickers=[ticker],
                period_years=req.period_years + 2,
                extra_tickers=[bm_ticker],
            )
            if ticker not in prices.columns:
                raise ValueError(f"No price data found for '{ticker}'.")

            benchmark_prices = prices[bm_ticker] if bm_ticker in prices.columns else prices[ticker]
            asset_prices     = prices[[ticker]].dropna(how="all")

            bt_result = run_backtest(
                prices            = asset_prices,
                benchmark_prices  = benchmark_prices,
                strategy          = strategy,
                optimizer         = optimizer,
                initial_capital   = req.initial_capital,
                max_stop_loss_pct = req.max_stop_loss_pct / 100.0,
            )
            # Buy-and-hold: asset price rebased to initial_capital, aligned to equity_curve dates
            bh_slice = asset_prices[ticker].reindex(bt_result.equity_curve.index).ffill().dropna()
            if len(bh_slice) > 0:
                buyhold_curve = (bh_slice / bh_slice.iloc[0]) * req.initial_capital
            else:
                buyhold_curve = bh_slice
            return bt_result, buyhold_curve

    else:
        # ── Universe mode ─────────────────────────────────────────────────────
        if req.optimizer not in OPTIMIZER_MAP:
            raise HTTPException(status_code=400, detail=f"Unknown optimizer '{req.optimizer}'. Valid: {list(OPTIMIZER_MAP)}")
        if req.universe not in UNIVERSE_MAP:
            raise HTTPException(status_code=400, detail=f"Unknown universe '{req.universe}'. Valid: {list(UNIVERSE_MAP)}")

        universe  = UNIVERSE_MAP[req.universe]
        optimizer = OPTIMIZER_MAP[req.optimizer]()

        def _execute():
            prices = load_prices(
                tickers=universe.tickers,
                period_years=req.period_years + 2,
                extra_tickers=[universe.benchmark_ticker],
            )
            bm_ticker = universe.benchmark_ticker
            if bm_ticker in prices.columns:
                benchmark_prices = prices[bm_ticker]
                asset_prices     = prices[universe.tickers].dropna(how="all")
            else:
                asset_prices     = prices[universe.tickers].dropna(how="all")
                benchmark_prices = asset_prices.iloc[:, 0]

            bt_result = run_backtest(
                prices            = asset_prices,
                benchmark_prices  = benchmark_prices,
                strategy          = strategy,
                optimizer         = optimizer,
                initial_capital   = req.initial_capital,
                max_stop_loss_pct = req.max_stop_loss_pct / 100.0,
            )
            return bt_result, None

    try:
        result, buyhold_series = await asyncio.to_thread(_execute)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")

    # Serialize equity curve
    equity_dict    = {d.strftime("%Y-%m-%d"): round(v, 2) for d, v in result.equity_curve.items() if not math.isnan(v)}
    benchmark_dict = {d.strftime("%Y-%m-%d"): round(v, 2) for d, v in result.benchmark_curve.items() if not math.isnan(v)}
    buyhold_dict   = (
        {d.strftime("%Y-%m-%d"): round(v, 2) for d, v in buyhold_series.items() if not math.isnan(v)}
        if buyhold_series is not None else None
    )

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

    # Trade markers — buy (entry) and sell (exit) dates for chart annotation
    trade_markers: list[dict] = []
    if not result.trade_log.empty:
        for _, row in result.trade_log.iterrows():
            entry = row.get("entry_date")
            exit_ = row.get("exit_date")
            if entry is not None and entry == entry:  # NaN-safe check
                trade_markers.append({"date": str(entry)[:10], "type": "buy"})
            if exit_ is not None and exit_ == exit_:
                stopped = bool(row.get("stop_triggered", False))
                trade_markers.append({"date": str(exit_)[:10], "type": "stop" if stopped else "sell"})

    # Full trade log for the positions table
    trade_log_rows: list[dict] = []
    if not result.trade_log.empty:
        for _, row in result.trade_log.iterrows():
            trade_log_rows.append({
                "asset":          row.get("asset", ""),
                "entry_date":     str(row.get("entry_date", ""))[:10],
                "exit_date":      str(row.get("exit_date",  ""))[:10],
                "entry_price":    round(float(row.get("entry_price",  0) or 0), 4),
                "exit_price":     round(float(row.get("exit_price",   0) or 0), 4),
                "return_pct":     round(float(row.get("return_pct",   0) or 0), 6),
                "pnl":            round(float(row.get("pnl",          0) or 0), 2),
                "balance":        round(float(row.get("equity_at_exit", 0) or 0), 2),
                "stop_triggered": bool(row.get("stop_triggered", False)),
            })

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
        "buyhold_curve":     buyhold_dict,
        "fold_boundaries":   fold_boundaries,
        "metrics":           result.metrics,
        "trade_log":         trade_log_rows,
        "trade_log_summary": trade_log_summary,
        "trade_markers":     trade_markers,
        "positions_chart":   positions_chart,
    })


# ─────────────────────────────────────────────────────────────
# ROUTES — MONTE CARLO INTEGRATED BACKTEST
# ─────────────────────────────────────────────────────────────

from typing import List as _List

class MCBacktestRequest(_BaseModel):
    # Strategies
    buy_strategy:  str   = "MomentumStrategy"
    sell_strategy: str   = "TP_SL"   # strategy name | "TP_SL" | "BOTH"
    # Universe / single-ticker mode
    universe:      str   = "SP500_SAMPLE"
    # Single-ticker mode: when set, ignores universe and tests one asset.
    single_ticker:    Optional[str] = None
    benchmark_ticker: Optional[str] = None
    # Backtest period
    backtest_start: str  = "2021-01-01"
    backtest_end:   str  = "2024-01-01"
    # Capital & risk
    initial_capital:      float = 1_000_000.0
    max_stop_loss_pct:    float = 0.08
    acceptable_risk_pct:  float = 0.01
    # MC simulation
    n_simulations:        int   = 1000
    holding_days:         int   = 10
    tp_quantile:          float = 0.80
    sl_quantile:          float = 0.10
    shock_distribution:   str   = "student_t"
    student_t_df:         int   = 6
    # Volatility estimation
    vol_lookback_days:    int   = 20
    vol_method:           str   = "ewma"
    ewma_halflife_days:   int   = 10
    vol_floor:            float = 0.10
    vol_cap:              float = 1.50
    drift_method:         str   = "zero"
    # Position & portfolio controls
    max_open_positions:   int   = 10
    max_position_pct:     float = 0.15
    cash_reserve_pct:     float = 0.10
    max_signals_per_bar:  int   = 5
    signal_confirmation_bars: int = 1
    cooloff_days:         int   = 5
    # Exit behaviour
    breakeven_trail_enabled: bool  = True
    max_holding_days:     int   = 20
    partial_tp_pct:       float = 1.0
    # EV filter
    min_ev_dollars:       float = 0.0
    min_rr_ratio:         float = 1.5
    min_p_tp:             float = 0.50
    # Position sizing
    sizing_method:        str   = "risk_parity_sl"
    kelly_fraction:       float = 0.25
    # Correlation controls
    correlation_penalty_enabled: bool  = True
    correlation_threshold:       float = 0.70
    correlation_penalty_factor:  float = 0.50
    # Walk-forward
    n_folds:              int   = 4
    test_window_days:     int   = 63
    purge_days:           int   = 10
    optimise_mc_params_on_train: bool = False
    sl_quantile_grid:     _List[float] = [0.05, 0.10, 0.15]
    tp_quantile_grid:     _List[float] = [0.75, 0.80, 0.85, 0.90]
    # Fill price
    fill_price:           str   = "open_next_day"
    # Misc
    seed_base:            int   = 42
    commission_bps:       float = 10.0
    sl_commission_bps:    float = 5.0


@app.post("/api/backtest/run-mc", tags=["Backtest"])
async def run_mc_backtest_endpoint(req: MCBacktestRequest):
    """
    Run a Monte Carlo integrated walk-forward backtest.

    Uses Monte Carlo path simulation to derive per-trade TP and SL levels.
    Returns the same equity_curve/benchmark/metrics/trade_log structure as
    /api/backtest/run, plus mc_trade_details and mc_aggregate_stats.
    """
    from src.universes import UNIVERSE_MAP
    from src.backtesting.data_loader import load_prices
    from src.backtesting.mc_engine import MCParams, run_mc_walk_forward

    is_single = bool(req.single_ticker)

    if not is_single and req.universe not in UNIVERSE_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown universe '{req.universe}'. Valid: {list(UNIVERSE_MAP)}")

    universe = None if is_single else UNIVERSE_MAP[req.universe]

    def _execute():
        # Load prices: extra years for vol warmup before backtest_start
        import pandas as _pd
        bs = _pd.Timestamp(req.backtest_start)
        be = _pd.Timestamp(req.backtest_end)
        period_years = max(2, int((be - bs).days / 365) + 2)

        if is_single:
            ticker = req.single_ticker.strip().upper()
            # Auto-infer benchmark if not provided (reuse normal-mode logic)
            bm_ticker = req.benchmark_ticker or (
                "^SET.BK" if ticker.endswith(".BK") else
                "BTC-USD" if ticker.endswith("-USD") else
                "SPY"
            )
            prices = load_prices(
                tickers=[ticker],
                period_years=period_years,
                extra_tickers=[bm_ticker],
            )
            if ticker not in prices.columns:
                raise ValueError(f"No price data for '{ticker}'.")
            asset_prices = prices[[ticker]].dropna(how="all")
            benchmark_prices = prices[bm_ticker] if bm_ticker in prices.columns else asset_prices.iloc[:, 0]
            tickers_list = [ticker]
        else:
            bm_ticker = universe.benchmark_ticker
            prices = load_prices(
                tickers=universe.tickers,
                period_years=period_years,
                extra_tickers=[bm_ticker],
            )
            if bm_ticker in prices.columns:
                benchmark_prices = prices[bm_ticker]
                asset_prices = prices[universe.tickers].dropna(how="all")
            else:
                asset_prices = prices[universe.tickers].dropna(how="all")
                benchmark_prices = asset_prices.iloc[:, 0]
            tickers_list = universe.tickers

        params = MCParams(
            buy_strategy=req.buy_strategy,
            sell_strategy=req.sell_strategy,
            tickers=tickers_list,
            benchmark_ticker=bm_ticker,
            backtest_start=_pd.Timestamp(req.backtest_start),
            backtest_end=_pd.Timestamp(req.backtest_end),
            initial_capital=req.initial_capital,
            max_stop_loss_pct=req.max_stop_loss_pct,
            acceptable_risk_pct=req.acceptable_risk_pct,
            n_simulations=req.n_simulations,
            holding_days=req.holding_days,
            tp_quantile=req.tp_quantile,
            sl_quantile=req.sl_quantile,
            shock_distribution=req.shock_distribution,
            student_t_df=req.student_t_df,
            vol_lookback_days=req.vol_lookback_days,
            vol_method=req.vol_method,
            ewma_halflife_days=req.ewma_halflife_days,
            vol_floor=req.vol_floor,
            vol_cap=req.vol_cap,
            drift_method=req.drift_method,
            max_open_positions=req.max_open_positions,
            max_position_pct=req.max_position_pct,
            cash_reserve_pct=req.cash_reserve_pct,
            max_signals_per_bar=req.max_signals_per_bar,
            signal_confirmation_bars=req.signal_confirmation_bars,
            cooloff_days=req.cooloff_days,
            breakeven_trail_enabled=req.breakeven_trail_enabled,
            max_holding_days=req.max_holding_days,
            partial_tp_pct=req.partial_tp_pct,
            min_ev_dollars=req.min_ev_dollars,
            min_rr_ratio=req.min_rr_ratio,
            min_p_tp=req.min_p_tp,
            sizing_method=req.sizing_method,
            kelly_fraction=req.kelly_fraction,
            correlation_penalty_enabled=req.correlation_penalty_enabled,
            correlation_threshold=req.correlation_threshold,
            correlation_penalty_factor=req.correlation_penalty_factor,
            n_folds=req.n_folds,
            test_window_days=req.test_window_days,
            purge_days=req.purge_days,
            optimise_mc_params_on_train=req.optimise_mc_params_on_train,
            sl_quantile_grid=list(req.sl_quantile_grid),
            tp_quantile_grid=list(req.tp_quantile_grid),
            fill_price=req.fill_price,
            seed_base=req.seed_base,
            commission_bps=req.commission_bps,
            sl_commission_bps=req.sl_commission_bps,
        )

        return run_mc_walk_forward(asset_prices, benchmark_prices, params)

    try:
        result = await asyncio.to_thread(_execute)
    except AssertionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MC backtest failed: {e}")

    # Serialize — same structure as /api/backtest/run
    equity_dict    = {d.strftime("%Y-%m-%d"): round(v, 2) for d, v in result.equity_curve.items() if not math.isnan(v)}
    benchmark_dict = {d.strftime("%Y-%m-%d"): round(v, 2) for d, v in result.benchmark_curve.items() if not math.isnan(v)}

    fold_boundaries: list[str] = []
    for s in result.fold_returns:
        if len(s) > 0:
            fold_boundaries.append(s.index[0].strftime("%Y-%m-%d"))

    trade_log_summary = {
        "total_trades": result.metrics.get("total_trades", 0),
        "long_trades":  result.metrics.get("long_trades", 0),
        "short_trades": result.metrics.get("short_trades", 0),
    }

    trade_markers: list[dict] = []
    trade_log_rows: list[dict] = []
    if not result.trade_log.empty:
        for _, row in result.trade_log.iterrows():
            entry = row.get("entry_date") or row.get("entry_bar")
            exit_ = row.get("exit_date")  or row.get("exit_bar")
            if entry is not None and entry == entry:
                trade_markers.append({"date": str(entry)[:10], "type": "buy"})
            if exit_ is not None and exit_ == exit_:
                stopped = bool(row.get("stop_triggered", False))
                trade_markers.append({"date": str(exit_)[:10], "type": "stop" if stopped else "sell"})
            trade_log_rows.append({
                "asset":          row.get("asset", row.get("ticker", "")),
                "entry_date":     str(row.get("entry_date", row.get("entry_bar", "")))[:10],
                "exit_date":      str(row.get("exit_date",  row.get("exit_bar", "")))[:10],
                "entry_price":    round(float(row.get("entry_price", 0) or 0), 4),
                "exit_price":     round(float(row.get("exit_price",  0) or 0), 4),
                "return_pct":     round(float(row.get("return_pct",  0) or 0), 6),
                "pnl":            round(float(row.get("pnl", row.get("pnl_net", 0)) or 0), 2),
                "balance":        round(float(row.get("equity_at_exit", 0) or 0), 2),
                "stop_triggered": bool(row.get("stop_triggered", False)),
                # MC extras
                "exit_reason":    str(row.get("exit_reason", "")),
                "mc_sl_raw":      round(float(row.get("mc_sl_raw",    0) or 0), 4),
                "mc_sl_applied":  round(float(row.get("mc_sl_applied", 0) or 0), 4),
                "mc_tp":          round(float(row.get("mc_tp",        0) or 0), 4),
                "rr":             round(float(row.get("rr",           0) or 0), 3),
                "p_tp":           round(float(row.get("p_tp",         0) or 0), 3),
                "ev":             round(float(row.get("ev",           0) or 0), 4),
                "sigma_annual":   round(float(row.get("sigma_annual", 0) or 0), 4),
                "fold_id":        int(row.get("fold_id", 0) or 0),
            })

    # Positions chart
    wh = result.weights_history
    positions_chart = []
    if not wh.empty:
        sample_step = max(1, len(wh) // 150)
        wh_sampled = wh.iloc[::sample_step]
        active_cols = [c for c in wh_sampled.columns if (wh_sampled[c].abs() > 1e-4).any()]
        if active_cols:
            for date, row in wh_sampled[active_cols].iterrows():
                entry: dict = {"date": date.strftime("%Y-%m-%d")}
                entry.update({t: round(float(v), 4) for t, v in row.items()})
                positions_chart.append(entry)

    # Build buy-and-hold curve for single-ticker mode (rebased to initial_capital)
    buyhold_dict = None
    if is_single and result.buyhold_curve is not None:
        buyhold_dict = {d.strftime("%Y-%m-%d"): round(v, 2) for d, v in result.buyhold_curve.items() if not math.isnan(v)}

    return _clean_floats({
        "equity_curve":       equity_dict,
        "benchmark_curve":    benchmark_dict,
        "buyhold_curve":      buyhold_dict,
        "fold_boundaries":    fold_boundaries,
        "metrics":            result.metrics,
        "trade_log":          trade_log_rows,
        "trade_log_summary":  trade_log_summary,
        "trade_markers":      trade_markers,
        "positions_chart":    positions_chart,
        # MC extras
        "mc_trade_details":   result.mc_trade_details,
        "mc_aggregate_stats": result.mc_aggregate_stats,
    })


# ─────────────────────────────────────────────────────────────
# ROUTES — HMM REGIME
# ─────────────────────────────────────────────────────────────

@app.get("/api/hmm-regime", response_model=HMMRegimeResponse, tags=["HMM"])
async def get_hmm_regime(
    ticker:     str  = Query("^SET.BK"),
    start:      str  = Query("2000-01-01"),
    train_end:  str  = Query(None),
    test_start: str  = Query(None),
    refresh:    bool = Query(False),
):
    from src.hmm_regime import run_hmm_pipeline

    if train_end is None:
        y = int(start[:4]) + 10
        train_end = f"{y}{start[4:]}"
    if test_start is None:
        test_start = train_end

    cache_key = f"hmm:{ticker}:{start}:{train_end}"
    if not refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        data = await asyncio.to_thread(
            run_hmm_pipeline, ticker, start, train_end, test_start
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HMM pipeline failed: {e}")

    result = HMMRegimeResponse(**data)
    cache.set(cache_key, result, ttl_seconds=21 * 24 * 3600)
    return result


# ─────────────────────────────────────────────────────────────
# ROUTES — NEWS SENTIMENT
# ─────────────────────────────────────────────────────────────

@app.get("/api/news", tags=["News"])
async def get_news_sentiment(ticker: str = Query(..., description="Ticker symbol, e.g. AAPL or PTT.BK")):
    """Fetch news for a ticker and classify sentiment via Gemini (15-min cache)."""
    cache_key = f"news:{ticker.upper()}"
    if (cached := cache.get(cache_key)) is not None:
        return cached

    from src.agents.news_sentiment import (
        Sentiment,
        _aggregate_signal,
        _classify_with_gemini,
        _count_tiers,
    )
    from src.agents.news_pipeline import (
        fetch_gnews_ticker,
        fetch_macro_articles,
        fetch_yfinance_articles,
    )

    macro_seen: set[str] = set()
    macro_articles = fetch_macro_articles(macro_seen)

    seen: set[str] = set(macro_seen)
    yf_articles  = fetch_yfinance_articles(ticker, seen)
    gn_articles  = fetch_gnews_ticker(ticker, seen)
    all_articles = yf_articles + gn_articles + macro_articles

    sentiments: list[Sentiment] = []
    for start in range(0, len(all_articles), 20):
        sentiments.extend(_classify_with_gemini(ticker, all_articles[start : start + 20]))

    overall_signal, confidence = _aggregate_signal(sentiments)
    tier_counts = _count_tiers(sentiments)
    high_impact = tier_counts["tier1"] > 0

    articles_out = [
        {
            "title":         a["title"],
            "summary":       a.get("summary", ""),
            "lang":          a.get("lang", "en"),
            "ticker_source": a.get("ticker_source", ""),
            "source":        a.get("source", ""),
            "published_at":  a.get("published_at"),
            "sentiment":     s.sentiment,
            "confidence":    s.confidence,
            "impact_tier":   s.impact_tier,
        }
        for a, s in zip(all_articles, sentiments)
    ]

    payload: dict = {
        "ticker":     ticker.upper(),
        "signal":     overall_signal,
        "confidence": confidence,
        "articles":   articles_out,
        "metrics": {
            "total_articles":         len(sentiments),
            "yfinance_articles":      len(yf_articles),
            "gnews_ticker_articles":  len(gn_articles),
            "macro_articles":         len(macro_articles),
            "bullish_articles":       sum(1 for s in sentiments if s.sentiment == "positive"),
            "bearish_articles":       sum(1 for s in sentiments if s.sentiment == "negative"),
            "neutral_articles":       sum(1 for s in sentiments if s.sentiment == "neutral"),
            "impact_tiers":           tier_counts,
        },
    }
    if high_impact:
        payload["high_impact_alert"] = True

    result = _clean_floats(payload)
    cache.set(cache_key, result, ttl_seconds=900)
    return result


@app.get("/api/news/headlines", tags=["News"])
async def get_news_headlines():
    """
    Dual-section breaking news feed (5-min cache).
    Returns top global headlines and top Thai headlines,
    each sorted by impact tier (T1 first) then newest-first.
    """
    import time as _time

    cache_key = "news:headlines"
    if (cached := cache.get(cache_key)) is not None:
        return cached

    from src.agents.news_sentiment import Sentiment, _classify_with_gemini
    from src.agents.news_pipeline import (
        fetch_global_macro_articles,
        fetch_thai_macro_articles,
    )

    _TIER_ORDER = {
        "Tier 1: Systemic Catalyst": 0,
        "Tier 2: Sector Shock":      1,
        "Tier 3: Routine/Noise":     2,
    }

    def _classify_and_sort(articles: list[dict], context: str, max_items: int = 15) -> list[dict]:
        sentiments: list[Sentiment] = []
        for start in range(0, len(articles), 20):
            sentiments.extend(_classify_with_gemini(context, articles[start : start + 20]))
        paired = list(zip(articles, sentiments))
        paired.sort(key=lambda p: (
            _TIER_ORDER.get(p[1].impact_tier, 2),
            -(p[0].get("published_at") or 0),
        ))
        return [
            {
                "title":         a["title"],
                "summary":       a.get("summary", ""),
                "lang":          a.get("lang", "en"),
                "ticker_source": a.get("ticker_source", ""),
                "source":        a.get("source", ""),
                "published_at":  a.get("published_at"),
                "sentiment":     s.sentiment,
                "confidence":    s.confidence,
                "impact_tier":   s.impact_tier,
            }
            for a, s in paired[:max_items]
        ]

    global_seen: set[str] = set()
    thai_seen:   set[str] = set()

    global_articles = fetch_global_macro_articles(global_seen)
    thai_articles   = fetch_thai_macro_articles(thai_seen)

    global_out = _classify_and_sort(global_articles, "GLOBAL MARKET")
    thai_out   = _classify_and_sort(thai_articles,   "THAI STOCK MARKET (SET)")

    result = _clean_floats({
        "global":     global_out,
        "thai":       thai_out,
        "fetched_at": int(_time.time()),
    })
    cache.set(cache_key, result, ttl_seconds=300)
    return result


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


# ─────────────────────────────────────────────────────────────
# ROUTES — HMM REGIME DETECTOR
# ─────────────────────────────────────────────────────────────

@app.get("/api/hmm-regime", tags=["HMM"])
async def get_hmm_regime(
    ticker:       str  = Query("SPY",        description="Equity ETF to analyze"),
    start:        str  = Query("2000-01-01", description="Data start date (ISO)"),
    train_end:    str  = Query("2010-12-31", description="End of initial training window"),
    test_start:   str  = Query("2011-01-01", description="Start of walk-forward test window"),
    refresh:      bool = Query(False,         description="Bypass cache"),
):
    """
    HMM market regime detector — expanding-window walk-forward, zero lookahead.

    Returns per-day regime labels (bull/sideways/bear) and posterior probabilities
    for the full out-of-sample test window.  Cached for 6 hours.
    """
    cache_key = f"hmm_regime_{ticker}_{start}_{train_end}_{test_start}"
    if not refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    def _run():
        from src.hmm_regime.data_loader import load_raw_data
        from src.hmm_regime.features    import build_features
        from src.hmm_regime.walk_forward import run_walk_forward
        from src.hmm_regime.evaluate    import compute_regime_stats

        raw      = load_raw_data(spy_ticker=ticker, start=start)
        features = build_features(raw)
        result   = run_walk_forward(
            df_features       = features,
            train_end         = train_end,
            test_start        = test_start,
            retrain_freq_days = 21,
            n_components      = 3,
            covariance_type   = "diag",
            n_iter            = 200,
            n_restarts        = 5,
            random_state      = 42,
        )

        stats = compute_regime_stats(result, raw["spy_close"])
        last  = result.iloc[-1]

        series = [
            {
                "date":       str(idx.date()),
                "regime":     row["regime"],
                "p_bear":     round(row["p_bear"],     4),
                "p_sideways": round(row["p_sideways"], 4),
                "p_bull":     round(row["p_bull"],     4),
                "spy_close":  round(float(raw["spy_close"].get(idx, float("nan"))), 4),
            }
            for idx, row in result.iterrows()
        ]

        regime_stats = {
            regime: {
                "frequency_pct":     float(stats.loc[regime, "frequency_pct"]),
                "avg_duration_days": float(stats.loc[regime, "avg_duration_days"]),
                "ann_return_pct":    float(stats.loc[regime, "ann_return_pct"]),
                "ann_vol_pct":       float(stats.loc[regime, "ann_vol_pct"]),
            }
            for regime in ["bull", "sideways", "bear"]
        }

        return {
            "ticker":          ticker,
            "current_regime":  last["regime"],
            "current_p_bull":  round(float(last["p_bull"]),     4),
            "current_p_side":  round(float(last["p_sideways"]), 4),
            "current_p_bear":  round(float(last["p_bear"]),     4),
            "train_end":       train_end,
            "test_start":      test_start,
            "n_observations":  len(result),
            "regime_stats":    regime_stats,
            "series":          series,
        }

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        import traceback, sys
        print(f"[HMM ERROR] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=422, detail=f"{type(exc).__name__}: {exc}")
    result = _clean_floats(result)
    cache.set(cache_key, result, ttl_seconds=21600)  # 6-hour cache
    return result


# ─────────────────────────────────────────────────────────────
# ROUTES — SHANNON ENTROPY (Systemic Risk Indicator)
# ─────────────────────────────────────────────────────────────

@app.get("/api/market/entropy", tags=["Analysis"])
async def get_market_entropy(
    ticker:  str  = Query("^SET.BK", description="Ticker for return distribution"),
    days:    int  = Query(30, ge=10, le=252, description="Rolling window in trading days"),
    bins:    int  = Query(20, ge=5,  le=50,  description="Histogram bins for discretisation"),
    refresh: bool = Query(False),
):
    """
    Shannon Entropy H = -Σ p_i log₂(p_i) of the rolling return distribution.
    High entropy → noisy/high-uncertainty regime. Low → trending/directional.
    Cached 5 minutes (same frequency as market-overview).
    """
    cache_key = f"entropy_{ticker}_{days}_{bins}"
    if not refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    def _compute():
        import yfinance as yf
        import numpy as np

        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty:
            raise ValueError(f"No data for {ticker}")

        closes  = df["Close"].squeeze() if hasattr(df["Close"], "squeeze") else df["Close"]
        returns = closes.pct_change().dropna()
        if len(returns) < days + 1:
            raise ValueError(
                f"Insufficient history for {ticker} (need {days + 1} bars, got {len(returns)})"
            )

        max_entropy = math.log2(bins)

        def _entropy(arr: "np.ndarray") -> float:
            counts, _ = np.histogram(arr, bins=bins)
            probs = counts / counts.sum()
            probs = probs[probs > 0]
            return float(-np.sum(probs * np.log2(probs)))

        current_h    = _entropy(returns.tail(days).values)
        normalized_h = current_h / max_entropy

        # Rolling series: one point per bar over the last 90 bars
        ret_arr  = returns.values
        date_arr = returns.index
        series: list[dict] = []
        start = max(days, len(ret_arr) - 90)
        for i in range(start, len(ret_arr)):
            window = ret_arr[i - days: i]
            if len(window) < days // 2:
                continue
            h = _entropy(window)
            series.append({
                "date":       date_arr[i].strftime("%Y-%m-%d"),
                "entropy":    round(h, 4),
                "normalized": round(h / max_entropy, 4),
            })

        if normalized_h < 0.50:
            regime, interpretation = "LOW NOISE", "Trending regime — signal clarity elevated"
        elif normalized_h < 0.75:
            regime, interpretation = "MODERATE", "Mixed signals — moderate uncertainty"
        else:
            regime, interpretation = "HIGH NOISE", "Systemic noise — reduce position sizing"

        return {
            "ticker":             ticker,
            "current_entropy":    round(current_h, 4),
            "normalized_entropy": round(normalized_h, 4),
            "max_entropy":        round(max_entropy, 4),
            "regime":             regime,
            "interpretation":     interpretation,
            "window_days":        days,
            "series":             series,
            "timestamp":          datetime.utcnow().isoformat(),
        }

    try:
        result = await asyncio.to_thread(_compute)
        result = _clean_floats(result)
        cache.set(cache_key, result, ttl_seconds=300)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Entropy computation failed: {exc}")


# ─────────────────────────────────────────────────────────────
# ROUTES — MACRO CORRELATION MATRIX
# ─────────────────────────────────────────────────────────────

@app.get("/api/macro/correlation-matrix", tags=["Stage 1"])
async def get_correlation_matrix(
    benchmark: str  = Query("^SET.BK", description="Benchmark to correlate macro drivers against"),
    window:    int  = Query(30, ge=10, le=90, description="Rolling correlation window (trading days)"),
    refresh:   bool = Query(False),
):
    """
    Dynamic correlation matrix: US 10Y Yield (^TNX), DXY (DX-Y.NYB), Brent Crude (BZ=F),
    and USD/THB (THB=X) correlated against the SET50 benchmark on a rolling window.

    Data sourced entirely from yfinance — no additional API keys required.
    Missing drivers return null correlations with a DATA_MISSING signal.
    Same 5-minute cache frequency as /api/market-overview.
    """
    cache_key = f"corr_matrix_{benchmark}_{window}"
    if not refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    def _compute():
        import yfinance as yf
        import pandas as pd
        import numpy as np

        DRIVERS: dict[str, str] = {
            "US10Y":  "^TNX",
            "DXY":    "DX-Y.NYB",
            "BRENT":  "BZ=F",
            "USDTHB": "THB=X",
        }
        all_tickers = [benchmark] + list(DRIVERS.values())

        raw = yf.download(all_tickers, period="1y", progress=False, auto_adjust=True)
        if raw.empty:
            raise ValueError("yfinance returned no data for macro correlation matrix")

        closes  = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        returns = closes.pct_change().dropna(how="all")

        if benchmark not in returns.columns:
            raise ValueError(f"Benchmark {benchmark} unavailable from yfinance")

        bench = returns[benchmark].dropna()

        correlations: dict[str, dict] = {}
        for name, ticker in DRIVERS.items():
            if ticker not in returns.columns:
                correlations[name] = {
                    "ticker": ticker, "signal": "DATA_MISSING",
                    "current_corr": None, "corr_30d": None, "corr_60d": None, "series": [],
                }
                continue

            driver  = returns[ticker].dropna()
            aligned = pd.concat([bench, driver], axis=1).dropna()
            aligned.columns = pd.Index(["bench", "driver"])

            if len(aligned) < 10:
                correlations[name] = {
                    "ticker": ticker, "signal": "INSUFFICIENT_DATA",
                    "current_corr": None, "corr_30d": None, "corr_60d": None, "series": [],
                }
                continue

            corr_60 = float(aligned["bench"].tail(60).corr(aligned["driver"].tail(60)))
            corr_30 = float(aligned["bench"].tail(30).corr(aligned["driver"].tail(30)))

            # Rolling series for the last 90 bars
            n = len(aligned)
            series: list[dict] = []
            for i in range(max(window, n - 90), n):
                sl = aligned.iloc[max(0, i - window + 1): i + 1]
                if len(sl) >= max(5, window // 3):
                    c = float(sl["bench"].corr(sl["driver"]))
                    if not math.isnan(c):
                        series.append({
                            "date": aligned.index[i].strftime("%Y-%m-%d"),
                            "corr": round(c, 4),
                        })

            if abs(corr_30) < 0.20:
                signal = "DECOUPLED"
            elif corr_30 > 0.50:
                signal = "STRONG_POS"
            elif corr_30 < -0.50:
                signal = "STRONG_NEG"
            elif corr_30 > 0:
                signal = "MILD_POS"
            else:
                signal = "MILD_NEG"

            correlations[name] = {
                "ticker":       ticker,
                "signal":       signal,
                "current_corr": round(corr_30, 4),
                "corr_30d":     round(corr_30, 4),
                "corr_60d":     round(corr_60, 4),
                "series":       series,
            }

        return {
            "benchmark":    benchmark,
            "window":       window,
            "correlations": correlations,
            "timestamp":    datetime.utcnow().isoformat(),
        }

    try:
        result = await asyncio.to_thread(_compute)
        result = _clean_floats(result)
        cache.set(cache_key, result, ttl_seconds=300)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Correlation matrix failed: {exc}")
