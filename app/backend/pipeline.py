"""
backend/pipeline.py
Clean adapter layer between FastAPI routes and the pipeline agents.

All functions are synchronous and designed to run inside asyncio.to_thread().
No Rich / CLI dependencies — pure data in, pure dict out.
"""

from __future__ import annotations
import yfinance as yf
import numpy as np

from src.agents.market_risk import (
    calculate_spx_200dma_buffer,
    calculate_yield_curve_spread,
    calculate_hy_credit_spread,
    calculate_breadth_above_50dma,
    calculate_rsp_spy_ratio,
    calculate_vix_level,
    calculate_vix_term_structure,
    calculate_composite_risk,
    calculate_confidence,
)
from src.agents.global_macro import run_global_macro_analysis
from src.agents.sector_screener import (
    run_sector_screener,
    get_sector_for_ticker,
    UNIVERSE_REGISTRY,
)
from src.agents.calculator import (
    calculate_sloan_ratio,
    calculate_cvar_95,
    calculate_wacc,
    calculate_roic,
    calculate_rolling_sortino,
    calculate_asset_turnover,
    calculate_altman_z,
    calculate_ccc,
    calculate_fcf_quality,
    generate_alpha_score,
)
from src.agents.technical import run_technical_analysis


# ─────────────────────────────────────────────────────────────
# STAGE 0
# ─────────────────────────────────────────────────────────────

def fetch_regime() -> dict:
    """
    Run all Stage 0 market fragility calculations.
    Returns a flat dict ready for RegimeResponse schema.
    """
    # Fetch SPX for 200DMA calculation
    spx_obj  = yf.Ticker("^GSPC")
    spx_hist = spx_obj.history(period="1y")
    spx_data = {"raw_stock_obj": spx_obj, "prices": spx_hist,
                "returns": spx_hist["Close"].pct_change().dropna()}

    dma_r  = calculate_spx_200dma_buffer(spx_data)
    yc_r   = calculate_yield_curve_spread()
    hy_r   = calculate_hy_credit_spread()
    brd_r  = calculate_breadth_above_50dma()
    rsp_r  = calculate_rsp_spy_ratio()
    vix_r  = calculate_vix_level()
    term_r = calculate_vix_term_structure()

    reg_sc = [dma_r.get("risk_score", 50), yc_r.get("risk_score", 50), hy_r.get("risk_score", 50)]
    fra_sc = [brd_r.get("risk_score", 50), rsp_r.get("risk_score", 50)]
    tri_sc = [vix_r.get("risk_score", 50), term_r.get("risk_score", 50)]

    composite  = calculate_composite_risk(reg_sc, fra_sc, tri_sc)
    confidence = calculate_confidence(reg_sc + fra_sc + tri_sc)

    cr = composite["composite_risk"]

    def _scale(r: float) -> str:
        if r <= 30: return "100% — Full Kelly"
        if r <= 45: return "80%"
        if r <= 60: return "60%"
        if r <= 74: return "40%"
        return "25% — Capital Preservation"

    return {
        "composite_risk":     cr,
        "regime_label":       composite["regime_label"],
        "layer_scores":       composite["layer_scores"],
        "confidence":         confidence["confidence"],
        "confidence_signal":  confidence["signal"],
        "position_scale":     _scale(cr),
        # SPX
        "spx_distance_pct":   dma_r.get("distance_pct"),
        "spx_signal":         dma_r.get("signal", "N/A"),
        "spx_risk_score":     dma_r.get("risk_score", 50),
        # Yield curve
        "yield_spread_bps":   yc_r.get("spread_bps"),
        "yield_signal":       yc_r.get("signal", "N/A"),
        "yield_risk_score":   yc_r.get("risk_score", 50),
        # HY credit
        "hy_oas_bps":         hy_r.get("oas_bps"),
        "hy_signal":          hy_r.get("signal", "N/A"),
        "hy_risk_score":      hy_r.get("risk_score", 50),
        # Breadth
        "breadth_pct":        brd_r.get("pct_above_50dma"),
        "breadth_signal":     brd_r.get("signal", "N/A"),
        "breadth_risk_score": brd_r.get("risk_score", 50),
        # RSP/SPY
        "rsp_z_score":        rsp_r.get("z_score_1y"),
        "rsp_signal":         rsp_r.get("signal", "N/A"),
        "rsp_risk_score":     rsp_r.get("risk_score", 50),
        # VIX
        "vix_level":          vix_r.get("vix_level"),
        "vix_percentile":     vix_r.get("percentile_1y"),
        "vix_signal":         vix_r.get("signal", "N/A"),
        "vix_risk_score":     vix_r.get("risk_score", 50),
        # VIX term
        "vix_roll_yield":     term_r.get("roll_yield"),
        "vix_term_signal":    term_r.get("signal", "N/A"),
        "vix_term_risk_score": term_r.get("risk_score", 50),
    }


# ─────────────────────────────────────────────────────────────
# STAGE 1
# ─────────────────────────────────────────────────────────────

def fetch_macro() -> dict:
    """Run Stage 1 global macro analysis. Returns raw dict from global_macro.py."""
    return run_global_macro_analysis()


# ─────────────────────────────────────────────────────────────
# STAGE 2
# ─────────────────────────────────────────────────────────────

def fetch_sectors(universe_key: str, macro_results: dict) -> dict:
    """Run Stage 2 sector screener for the given universe."""
    cfg     = UNIVERSE_REGISTRY[universe_key]
    result  = run_sector_screener(
        macro_results    = macro_results,
        custom_universe  = cfg["universe"],
        benchmark_ticker = cfg["benchmark"],
    )
    return {
        "universe":        cfg["display_name"],
        "sector_gate":     result["sector_gate"],
        "sector_rotation": result["sector_rotation"],
        "top_sectors":     result["top_sectors"],
        "avoid_sectors":   [s["sector"] for s in result["ranked_sectors"] if not s["gate_pass"]],
        "ranked_sectors":  result["ranked_sectors"],
    }


# ─────────────────────────────────────────────────────────────
# STAGES 3 + 4  — per ticker
# ─────────────────────────────────────────────────────────────

def analyze_ticker(
    ticker:        str,
    composite_risk: float,
    macro_results: dict,
    sector_scores: dict,
    universe:      dict,
) -> dict:
    """
    Runs Stage 3 (fundamentals) + Stage 4 (technical) for one ticker.
    Pure synchronous — safe for asyncio.to_thread.
    Returns a result row dict or {"ok": False, "ticker": ..., "error": ...}.
    """
    try:
        stock   = yf.Ticker(ticker)
        history = stock.history(period="1y")
        if history.empty:
            return {"ok": False, "ticker": ticker, "error": "No price history"}

        returns = history["Close"].pct_change().dropna()
        price   = float(history["Close"].iloc[-1])
        fin, bs, cf, info = stock.financials, stock.balance_sheet, stock.cashflow, stock.info

        # ── Stage 3 ───────────────────────────────────────────
        sector_name  = get_sector_for_ticker(ticker, universe=universe)
        sector_adj   = macro_results.get("sector_adjustments", {}).get(sector_name, 0)
        sector_score = sector_scores.get(sector_name, 50.0)

        roic    = calculate_roic(fin, bs)
        wacc    = calculate_wacc(info, fin, bs, cf)
        sloan   = calculate_sloan_ratio(fin, cf, bs)
        fcf_q   = calculate_fcf_quality(fin, cf)
        z       = calculate_altman_z(fin, bs, info)
        cvar    = calculate_cvar_95(returns)
        sortino = calculate_rolling_sortino(returns)
        a_turn  = calculate_asset_turnover(fin, bs)
        ccc_val = calculate_ccc(fin, bs)
        beta    = float(info.get("beta", 1.0) or 1.0)

        alpha = generate_alpha_score(
            roic=roic, wacc=wacc, sloan=sloan, z_score=z,
            sortino=sortino, beta=beta, fcf_quality=fcf_q,
            composite_risk=composite_risk, sector_macro_adj=sector_adj,
        )
        gate3 = alpha >= 50 and z > 1.81

        # ── Stage 4 ───────────────────────────────────────────
        try:
            sig   = run_technical_analysis(ticker, composite_risk=composite_risk)
            gate4 = sig.rr_ratio >= 1.5 and sig.signal_strength >= 40
        except Exception:
            sig   = None
            gate4 = False

        rr_score  = min((sig.rr_ratio / 3.0) * 100, 100.0) if sig else 0.0
        ss_score  = float(sig.signal_strength) if sig else 0.0
        rank_score = (
            alpha        * 0.45
            + ss_score   * 0.30
            + sector_score * 0.15
            + rr_score   * 0.10
        )

        # verdict label for frontend
        if gate3 and gate4:
            verdict = "BUY"
        elif gate3:
            verdict = "FUND_ONLY"
        elif gate4:
            verdict = "TECH_ONLY"
        else:
            verdict = "FAIL"

        return {
            "ok":           True,
            "ticker":       ticker,
            "sector":       sector_name,
            "price":        price,
            "alpha":        alpha,
            "roic":         roic,
            "wacc":         wacc,
            "moat":         roic - wacc,
            "z":            z,
            "sloan":        sloan,
            "fcf_q":        fcf_q,
            "beta":         beta,
            "cvar":         cvar,
            "sortino":      sortino,
            "a_turn":       a_turn,
            "ccc":          ccc_val,
            "sector_score": sector_score,
            "sector_adj":   sector_adj,
            "strategy":     sig.strategy      if sig else "N/A",
            "regime_fit":   sig.regime_fit    if sig else "N/A",
            "signal_str":   int(ss_score),
            "rr":           sig.rr_ratio      if sig else 0.0,
            "entry":        sig.entry_price   if sig else None,
            "tp":           sig.tp_price      if sig else None,
            "sl":           sig.sl_price      if sig else None,
            "atr":          sig.atr_14        if sig else None,
            "gate3":        gate3,
            "gate4":        gate4,
            "rank_score":   rank_score,
            "verdict":      verdict,
        }

    except Exception as exc:
        return {"ok": False, "ticker": ticker, "error": str(exc)}


def get_universe_info() -> list[dict]:
    """Return metadata for all registered universes."""
    result = []
    for key, cfg in UNIVERSE_REGISTRY.items():
        tickers = list(dict.fromkeys(
            t for s in cfg["universe"].values() for t in s["members"]
        ))
        result.append({
            "key":          key,
            "display_name": cfg["display_name"],
            "ticker_count": len(tickers),
            "sector_count": len(cfg["universe"]),
            "benchmark":    cfg["benchmark"],
        })
    return result
