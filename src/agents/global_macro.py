"""
src/agents/global_macro.py
Global Macro Signal Layer — commodities, dollar, cross-asset regime signals.

These indicators enrich the Stage 1 composite risk score and feed sector
alignment bonuses into Stage 2. Each function returns a standardised dict
with keys: value, signal, risk_score (0-100), macro_bias.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from src.agents.calculator import safe_scalar


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _fetch_close(ticker: str, period: str = "6mo") -> pd.Series:
    """Pull daily Close series; return empty Series on failure."""
    try:
        hist = yf.Ticker(ticker).history(period=period)["Close"]
        return hist.dropna()
    except Exception:
        return pd.Series(dtype=float)


def _momentum(series: pd.Series, window: int) -> float:
    """% return over `window` trading days. Positive = uptrend."""
    if len(series) < window + 1:
        return 0.0
    return float((series.iloc[-1] / series.iloc[-window] - 1) * 100)


def _zscore(series: pd.Series, window: int = 60) -> float:
    """Rolling z-score of the last observation vs a `window`-day history."""
    if len(series) < window:
        return 0.0
    roll = series.iloc[-window:]
    mu, sigma = roll.mean(), roll.std()
    return float((series.iloc[-1] - mu) / sigma) if sigma > 0 else 0.0


# ─────────────────────────────────────────────────────────────
# 1. GOLD  — risk-off barometer & inflation hedge
# ─────────────────────────────────────────────────────────────

def analyse_gold() -> dict:
    """
    Gold rising + real yields falling  → RISK_OFF  → reduce equity exposure.
    Gold falling + dollar rising       → RISK_ON    → equities favoured.

    Sector alignment:
      - Gold miners (GDX-like) benefit directly.
      - Financials, high-growth tech hurt when inflation fear is high.
    """
    prices = _fetch_close("GC=F", "6mo")           # Gold futures
    tnx    = _fetch_close("^TNX", "3mo")            # 10Y nominal yield (proxy real yield)

    if prices.empty:
        return {"value": np.nan, "signal": "DATA_ERROR", "risk_score": 50, "macro_bias": "NEUTRAL"}

    mom_20  = _momentum(prices, 20)
    mom_60  = _momentum(prices, 60)
    z_score = _zscore(prices, 60)

    # Real-yield proxy: falling 10Y while gold rises = classic risk-off
    tnx_mom = _momentum(tnx, 20) if not tnx.empty else 0.0
    risk_off_signal = (mom_20 > 2.0) and (tnx_mom < 0)

    # Risk scoring: rising gold = more cautious on equities
    if z_score > 1.5 and risk_off_signal:
        risk_score, signal, macro_bias = 75, "STRONG_RISK_OFF", "DEFENSIVE"
    elif z_score > 0.5 or mom_20 > 1.5:
        risk_score, signal, macro_bias = 55, "MILD_RISK_OFF", "CAUTIOUS"
    elif z_score < -1.0:
        risk_score, signal, macro_bias = 20, "RISK_ON_CONFIRMED", "AGGRESSIVE"
    else:
        risk_score, signal, macro_bias = 40, "NEUTRAL", "NEUTRAL"

    # Sector hints
    sector_tailwinds = ["MATERIALS", "ENERGY"] if macro_bias in ("DEFENSIVE", "CAUTIOUS") else ["TECH", "CONSUMER_DISC"]
    sector_headwinds = ["TECH", "FINANCIALS"] if macro_bias == "DEFENSIVE" else ["MATERIALS"]

    return {
        "ticker": "GC=F",
        "current_price": round(safe_scalar(prices.iloc[-1]), 2),
        "mom_20d_pct": round(mom_20, 2),
        "mom_60d_pct": round(mom_60, 2),
        "z_score_60d": round(z_score, 2),
        "signal": signal,
        "risk_score": risk_score,
        "macro_bias": macro_bias,
        "sector_tailwinds": sector_tailwinds,
        "sector_headwinds": sector_headwinds,
    }


# ─────────────────────────────────────────────────────────────
# 2. CRUDE OIL  — inflation + growth proxy
# ─────────────────────────────────────────────────────────────

def analyse_crude_oil() -> dict:
    """
    Oil surging  → input-cost inflation → margin pressure on non-energy.
    Oil collapsing → demand destruction signal → global growth concern.

    Sector alignment:
      - ENERGY benefits from rising oil.
      - AIRLINES, TRANSPORT, CONSUMER hurt by rising oil.
      - SET stocks: PTT, PTTEP benefit; airlines (THAI, AAV) hurt.
    """
    wti   = _fetch_close("CL=F", "6mo")             # WTI Crude futures
    brent = _fetch_close("BZ=F", "3mo")              # Brent — cross-check

    if wti.empty:
        return {"value": np.nan, "signal": "DATA_ERROR", "risk_score": 50, "macro_bias": "NEUTRAL"}

    current = safe_scalar(wti.iloc[-1])
    mom_20  = _momentum(wti, 20)
    mom_60  = _momentum(wti, 60)
    z_score = _zscore(wti, 60)

    # Regime classification
    if current > 90 and mom_20 > 3:
        risk_score, signal, macro_bias = 70, "STAGFLATION_RISK", "DEFENSIVE_ENERGY"
    elif mom_20 > 5:
        risk_score, signal, macro_bias = 60, "INFLATIONARY_SURGE", "ENERGY_OVERWEIGHT"
    elif mom_20 < -5 or z_score < -1.5:
        risk_score, signal, macro_bias = 65, "DEMAND_DESTRUCTION", "RISK_OFF"
    elif -2 < mom_20 < 2:
        risk_score, signal, macro_bias = 30, "STABLE_RANGE", "NEUTRAL"
    else:
        risk_score, signal, macro_bias = 45, "MODERATE_MOVE", "NEUTRAL"

    sector_tailwinds = ["ENERGY", "MATERIALS"] if mom_20 > 2 else ["CONSUMER_DISC", "TRANSPORT"]
    sector_headwinds = ["TRANSPORT", "CONSUMER_DISC", "AIRLINES"] if mom_20 > 2 else ["ENERGY"]

    return {
        "ticker": "CL=F",
        "current_price": round(current, 2),
        "mom_20d_pct": round(mom_20, 2),
        "mom_60d_pct": round(mom_60, 2),
        "z_score_60d": round(z_score, 2),
        "signal": signal,
        "risk_score": risk_score,
        "macro_bias": macro_bias,
        "sector_tailwinds": sector_tailwinds,
        "sector_headwinds": sector_headwinds,
    }


# ─────────────────────────────────────────────────────────────
# 3. US DOLLAR INDEX (DXY) — EM / SET pressure gauge
# ─────────────────────────────────────────────────────────────

def analyse_dxy() -> dict:
    """
    DXY strengthening → THB weakening → foreign outflows from SET.
    DXY weakening     → EM tailwind → SET benefits from inflows.

    Critical for SET50 universe: almost all Thai large-caps are priced
    in THB, and FX flows dominate short-term price action.
    """
    prices  = _fetch_close("DX-Y.NYB", "6mo")
    usdthb  = _fetch_close("USDTHB=X", "3mo")         # USD/THB direct pair

    if prices.empty:
        return {"value": np.nan, "signal": "DATA_ERROR", "risk_score": 50, "macro_bias": "NEUTRAL"}

    mom_20  = _momentum(prices, 20)
    mom_60  = _momentum(prices, 60)
    z_score = _zscore(prices, 60)

    # DXY rising = bad for EM/SET
    if z_score > 1.5 and mom_20 > 1.5:
        risk_score, signal, macro_bias = 80, "STRONG_USD_HEADWIND", "REDUCE_EM"
    elif mom_20 > 0.5:
        risk_score, signal, macro_bias = 55, "MILD_USD_STRENGTH", "CAUTIOUS_EM"
    elif z_score < -1.0:
        risk_score, signal, macro_bias = 15, "USD_WEAKNESS_EM_TAILWIND", "ADD_EM"
    else:
        risk_score, signal, macro_bias = 35, "STABLE_USD", "NEUTRAL"

    thb_pressure = safe_scalar(usdthb.iloc[-1]) if not usdthb.empty else np.nan

    return {
        "ticker": "DX-Y.NYB",
        "current_price": round(safe_scalar(prices.iloc[-1]), 2),
        "usdthb_rate": round(thb_pressure, 2) if not np.isnan(thb_pressure) else "N/A",
        "mom_20d_pct": round(mom_20, 2),
        "z_score_60d": round(z_score, 2),
        "signal": signal,
        "risk_score": risk_score,
        "macro_bias": macro_bias,
        "note": "Strong DXY = EM outflow pressure on SET50 universe",
    }


# ─────────────────────────────────────────────────────────────
# 4. COPPER  — "Dr. Copper" industrial demand barometer
# ─────────────────────────────────────────────────────────────

def analyse_copper() -> dict:
    """
    Copper rising  → industrial expansion, global growth optimism.
    Copper falling → leading recession warning (leads GDP by ~6 months).

    Sector alignment: Industrials, Materials benefit when copper is rising.
    """
    prices = _fetch_close("HG=F", "6mo")             # Copper futures

    if prices.empty:
        return {"value": np.nan, "signal": "DATA_ERROR", "risk_score": 50, "macro_bias": "NEUTRAL"}

    mom_20  = _momentum(prices, 20)
    mom_60  = _momentum(prices, 60)
    z_score = _zscore(prices, 60)

    if z_score > 1.0 and mom_60 > 5:
        risk_score, signal, macro_bias = 15, "GLOBAL_EXPANSION", "CYCLICAL_OVERWEIGHT"
    elif mom_20 > 2:
        risk_score, signal, macro_bias = 30, "GROWTH_POSITIVE", "MILD_CYCLICAL"
    elif z_score < -1.0 and mom_60 < -5:
        risk_score, signal, macro_bias = 80, "RECESSION_WARNING", "DEFENSIVE"
    elif mom_20 < -2:
        risk_score, signal, macro_bias = 60, "GROWTH_SLOWING", "CAUTIOUS"
    else:
        risk_score, signal, macro_bias = 40, "NEUTRAL", "NEUTRAL"

    return {
        "ticker": "HG=F",
        "current_price": round(safe_scalar(prices.iloc[-1]), 4),
        "mom_20d_pct": round(mom_20, 2),
        "mom_60d_pct": round(mom_60, 2),
        "z_score_60d": round(z_score, 2),
        "signal": signal,
        "risk_score": risk_score,
        "macro_bias": macro_bias,
        "note": "Copper leads GDP by ~6 months — best early-cycle indicator",
    }


# ─────────────────────────────────────────────────────────────
# 5. COMPOSITE GLOBAL MACRO SCORE
# ─────────────────────────────────────────────────────────────

# Macro-to-sector alignment table.
# For each sector code, the value is how much to ADD to the alpha score
# based on macro signals. Positive = tailwind, negative = headwind.
SECTOR_MACRO_ADJUSTMENT = {
    "ENERGY":        {"oil_up": +8,  "oil_down": -12, "gold_up": +3,  "dxy_up": -2,  "copper_up": +4},
    "MATERIALS":     {"oil_up": +4,  "oil_down": -5,  "gold_up": +6,  "dxy_up": -4,  "copper_up": +8},
    "FINANCIALS":    {"oil_up": -2,  "oil_down": +3,  "gold_up": -5,  "dxy_up": +5,  "copper_up": +3},
    "CONSUMER_DISC": {"oil_up": -6,  "oil_down": +6,  "gold_up": -2,  "dxy_up": -3,  "copper_up": +2},
    "CONSUMER_STAP": {"oil_up": -3,  "oil_down": +4,  "gold_up": +4,  "dxy_up": -1,  "copper_up": 0},
    "TECH":          {"oil_up": -2,  "oil_down": +3,  "gold_up": -6,  "dxy_up": -2,  "copper_up": +2},
    "HEALTH":        {"oil_up": -1,  "oil_down": +2,  "gold_up": +3,  "dxy_up": -1,  "copper_up": 0},
    "INDUSTRIALS":   {"oil_up": -4,  "oil_down": +2,  "gold_up": 0,   "dxy_up": -3,  "copper_up": +7},
    "UTILITIES":     {"oil_up": -3,  "oil_down": +5,  "gold_up": +2,  "dxy_up": -1,  "copper_up": +1},
    "REIT":          {"oil_up": -2,  "oil_down": +3,  "gold_up": +1,  "dxy_up": -4,  "copper_up": +1},
    "TRANSPORT":     {"oil_up": -8,  "oil_down": +8,  "gold_up": -1,  "dxy_up": -2,  "copper_up": +3},
}


def run_global_macro_analysis() -> dict:
    """
    Master orchestrator. Run all macro analyses, build a composite macro
    risk score, and return sector adjustment scores.

    Returns
    -------
    dict with keys:
        gold, crude_oil, dxy, copper,
        composite_macro_risk (0–100),
        macro_regime (str),
        sector_adjustments (dict: sector → int score delta),
        macro_bias_summary (str)
    """
    gold   = analyse_gold()
    oil    = analyse_crude_oil()
    dxy    = analyse_dxy()
    copper = analyse_copper()

    scores = [
        gold.get("risk_score", 50),
        oil.get("risk_score", 50),
        dxy.get("risk_score", 50),
        copper.get("risk_score", 50),
    ]
    composite_macro_risk = round(float(np.mean(scores)), 1)

    # Determine macro regime
    if composite_macro_risk < 30:
        macro_regime = "RISK_ON_EXPANSION"
    elif composite_macro_risk < 50:
        macro_regime = "NEUTRAL_GROWTH"
    elif composite_macro_risk < 65:
        macro_regime = "CAUTIOUS_ELEVATED"
    elif composite_macro_risk < 80:
        macro_regime = "RISK_OFF_DEFENSIVE"
    else:
        macro_regime = "CRISIS_PRESERVE_CAPITAL"

    # Build macro event flags for sector adjustment lookup
    oil_up    = oil.get("mom_20d_pct", 0) > 2
    oil_down  = oil.get("mom_20d_pct", 0) < -2
    gold_up   = gold.get("macro_bias") in ("DEFENSIVE", "CAUTIOUS")
    dxy_up    = dxy.get("mom_20d_pct", 0) > 0.5
    copper_up = copper.get("mom_20d_pct", 0) > 2

    # Compute sector adjustment points
    sector_adjustments = {}
    for sector, weights in SECTOR_MACRO_ADJUSTMENT.items():
        adj = 0
        if oil_up:   adj += weights["oil_up"]
        if oil_down: adj += weights["oil_down"]
        if gold_up:  adj += weights["gold_up"]
        if dxy_up:   adj += weights["dxy_up"]
        if copper_up:adj += weights["copper_up"]
        sector_adjustments[sector] = int(np.clip(adj, -20, +20))

    # Human-readable summary
    biases = [gold.get("macro_bias"), oil.get("macro_bias"),
              dxy.get("macro_bias"), copper.get("macro_bias")]
    defensive_count = sum(1 for b in biases if "DEFENSIVE" in str(b) or "RISK_OFF" in str(b))
    if defensive_count >= 3:
        macro_bias_summary = "BROADLY_DEFENSIVE — reduce exposure, prefer cash & hard assets"
    elif defensive_count >= 2:
        macro_bias_summary = "MIXED_LEAN_DEFENSIVE — selective, favour quality & low-beta"
    elif defensive_count == 0:
        macro_bias_summary = "RISK_ON — full exposure, favour cyclicals & growth"
    else:
        macro_bias_summary = "NEUTRAL — sector selection is the alpha driver"

    return {
        "gold":                  gold,
        "crude_oil":             oil,
        "dxy":                   dxy,
        "copper":                copper,
        "composite_macro_risk":  composite_macro_risk,
        "macro_regime":          macro_regime,
        "macro_bias_summary":    macro_bias_summary,
        "sector_adjustments":    sector_adjustments,
    }