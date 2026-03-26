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
    allow_origins     = ["http://localhost:3000", "http://localhost:5173",
                         "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
    allow_credentials = True,
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
