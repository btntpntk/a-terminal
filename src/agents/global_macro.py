"""
src/agents/global_macro.py
Global Macro Signal Layer — eight cross-asset signals covering rates, dollar,
commodities, EM flows, and China.

Signal catalogue:
  1. Real Yield       (^TNX / TIP)    — equity valuation & rate regime
  2. DXY              (DX-Y.NYB)      — EM FX pressure on SET
  3. USD/THB          (USDTHB=X)      — direct Thai FX signal
  4. Crude Oil        (CL=F)          — inflation & cost-push
  5. Copper           (HG=F)          — global growth barometer
  6. Gold             (GC=F)          — risk-off hedge
  7. EM Flows         (EEM / THD)     — foreign fund flow into SET universe
  8. China Pulse      (MCHI / KWEB)   — Thailand's #1 trading partner

Composite = weighted average (not equal-weight):
  Real Yield 20%  ·  DXY 20%  ·  EM Flows 15%  ·  Copper 15%
  Oil 12%  ·  China 10%  ·  THB 5%  ·  Gold 3%

Growth/Inflation quadrant is derived from the signals and drives
cycle-aware sector rotation advice.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from src.agents.calculator import safe_scalar


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _fetch_close(ticker: str, period: str = "6mo") -> pd.Series:
    try:
        hist = yf.Ticker(ticker).history(period=period)["Close"]
        return hist.dropna()
    except Exception:
        return pd.Series(dtype=float)


def _momentum(series: pd.Series, window: int) -> float:
    if len(series) < window + 1:
        return 0.0
    return float((series.iloc[-1] / series.iloc[-window] - 1) * 100)


def _zscore(series: pd.Series, window: int = 60) -> float:
    if len(series) < window:
        return 0.0
    roll = series.iloc[-window:]
    mu, sigma = roll.mean(), roll.std()
    return float((series.iloc[-1] - mu) / sigma) if sigma > 0 else 0.0


def _abs_change(series: pd.Series, window: int) -> float:
    """Absolute change over window (useful for yield series in %)."""
    if len(series) < window + 1:
        return 0.0
    return float(series.iloc[-1] - series.iloc[-window])


# ─────────────────────────────────────────────────────────────
# 1. REAL YIELD  — equity valuation & rate regime
# ─────────────────────────────────────────────────────────────

def analyse_real_yield() -> dict:
    """
    10Y nominal yield level + direction as equity valuation signal.
    TIP ETF (iShares TIPS Bond) used as real-yield direction proxy:
      TIP falling → real yields rising → PE compression signal.

    >4.5% nominal = historically restrictive for equities.
    Rising yields + TIP selling = strongest headwind signal.

    Sector impact:
      Headwinds: TECH (long duration), REIT, UTILITIES
      Tailwinds: FINANCIALS (NIM expansion), ENERGY (inflation hedge)
    """
    tnx = _fetch_close("^TNX", "1y")
    tip = _fetch_close("TIP", "6mo")

    if tnx.empty:
        return {"value": np.nan, "signal": "DATA_ERROR", "risk_score": 50,
                "macro_bias": "NEUTRAL", "yield_level": np.nan}

    current_yield  = safe_scalar(tnx.iloc[-1])
    mom_20         = _momentum(tnx, 20)          # % change in yield level
    z_score        = _zscore(tnx, min(len(tnx), 252))
    yield_chg_20d  = _abs_change(tnx, 20)        # absolute bps-equivalent move
    tip_mom_20     = _momentum(tip, 20) if not tip.empty else 0.0

    # Real yields rising when: yield level rising AND TIP ETF falling
    real_yield_rising = (yield_chg_20d > 0.15) or (tip_mom_20 < -1.5)

    if current_yield > 4.5 and real_yield_rising:
        risk_score, signal, macro_bias = 85, "HIGHLY_RESTRICTIVE_RISING", "REDUCE_DURATION"
    elif current_yield > 4.0 and real_yield_rising:
        risk_score, signal, macro_bias = 70, "RESTRICTIVE_RISING", "CAUTIOUS"
    elif current_yield > 4.0:
        risk_score, signal, macro_bias = 55, "RESTRICTIVE_STABLE", "SELECTIVE"
    elif real_yield_rising:
        risk_score, signal, macro_bias = 55, "YIELDS_RISING", "CAUTIOUS"
    elif current_yield < 3.5 and not real_yield_rising:
        risk_score, signal, macro_bias = 20, "ACCOMMODATIVE", "GROWTH_FAVOURED"
    else:
        risk_score, signal, macro_bias = 35, "NEUTRAL_YIELDS", "NEUTRAL"

    return {
        "ticker":            "^TNX / TIP",
        "current_price":     round(current_yield, 2),
        "yield_level":       round(current_yield, 2),
        "yield_chg_20d":     round(yield_chg_20d, 3),
        "tip_mom_20d":       round(tip_mom_20, 2),
        "mom_20d_pct":       round(mom_20, 2),
        "z_score_60d":       round(z_score, 2),
        "real_yield_rising": real_yield_rising,
        "signal":            signal,
        "risk_score":        risk_score,
        "macro_bias":        macro_bias,
    }


# ─────────────────────────────────────────────────────────────
# 2. DXY  — EM / SET pressure gauge
# ─────────────────────────────────────────────────────────────

def analyse_dxy() -> dict:
    """
    DXY strengthening → THB weakening → foreign outflows from SET.
    DXY weakening     → EM tailwind   → SET benefits from inflows.
    """
    prices = _fetch_close("DX-Y.NYB", "6mo")

    if prices.empty:
        return {"value": np.nan, "signal": "DATA_ERROR", "risk_score": 50, "macro_bias": "NEUTRAL"}

    mom_20  = _momentum(prices, 20)
    mom_60  = _momentum(prices, 60)
    z_score = _zscore(prices, 60)

    if z_score > 1.5 and mom_20 > 1.5:
        risk_score, signal, macro_bias = 80, "STRONG_USD_HEADWIND", "REDUCE_EM"
    elif mom_20 > 0.5:
        risk_score, signal, macro_bias = 55, "MILD_USD_STRENGTH", "CAUTIOUS_EM"
    elif z_score < -1.0:
        risk_score, signal, macro_bias = 15, "USD_WEAKNESS_EM_TAILWIND", "ADD_EM"
    else:
        risk_score, signal, macro_bias = 35, "STABLE_USD", "NEUTRAL"

    return {
        "ticker":        "DX-Y.NYB",
        "current_price": round(safe_scalar(prices.iloc[-1]), 2),
        "mom_20d_pct":   round(mom_20, 2),
        "mom_60d_pct":   round(mom_60, 2),
        "z_score_60d":   round(z_score, 2),
        "signal":        signal,
        "risk_score":    risk_score,
        "macro_bias":    macro_bias,
        "note":          "Strong DXY = EM outflow pressure on SET universe",
    }


# ─────────────────────────────────────────────────────────────
# 3. USD/THB  — direct Thai FX signal
# ─────────────────────────────────────────────────────────────

def analyse_thb() -> dict:
    """
    Fully scored USD/THB signal. Rising USDTHB = THB weakening.

    THB direction determines:
      - Foreign fund re-valuation of Thai equity holdings (FX mark-to-market)
      - Export vs import sector divergence
      - BOT rate policy pressure

    THB weakening tailwinds:  energy exporters (PTT, PTTEP), hard-commodity exporters
    THB weakening headwinds:  importers (CONSUMER_DISC, TECH hardware), REIT (foreign debt)
    """
    prices = _fetch_close("USDTHB=X", "6mo")

    if prices.empty:
        return {"value": np.nan, "signal": "DATA_ERROR", "risk_score": 50,
                "macro_bias": "NEUTRAL", "usdthb_rate": np.nan}

    current_rate = safe_scalar(prices.iloc[-1])
    mom_20       = _momentum(prices, 20)
    mom_60       = _momentum(prices, 60)
    z_score      = _zscore(prices, 60)

    # USDTHB rising = THB weakening = SET headwind for foreign holders
    if z_score > 1.5 and mom_20 > 1.0:
        risk_score, signal, macro_bias = 75, "THB_SHARP_DEPRECIATION", "REDUCE_IMPORTERS"
    elif mom_20 > 0.5:
        risk_score, signal, macro_bias = 55, "THB_MILD_WEAKNESS", "CAUTIOUS"
    elif z_score < -1.0 and mom_20 < -0.5:
        risk_score, signal, macro_bias = 20, "THB_APPRECIATING", "EM_TAILWIND"
    else:
        risk_score, signal, macro_bias = 35, "THB_STABLE", "NEUTRAL"

    return {
        "ticker":        "USDTHB=X",
        "current_price": round(current_rate, 2),
        "usdthb_rate":   round(current_rate, 2),
        "mom_20d_pct":   round(mom_20, 2),
        "mom_60d_pct":   round(mom_60, 2),
        "z_score_60d":   round(z_score, 2),
        "signal":        signal,
        "risk_score":    risk_score,
        "macro_bias":    macro_bias,
        "note":          "Rising = THB weakening. Critical for SET foreign-holder returns.",
    }


# ─────────────────────────────────────────────────────────────
# 4. CRUDE OIL  — inflation + growth proxy
# ─────────────────────────────────────────────────────────────

def analyse_crude_oil() -> dict:
    """
    Oil surging  → input-cost inflation → margin pressure on non-energy.
    Oil collapsing → demand destruction signal → global growth concern.
    """
    wti   = _fetch_close("CL=F", "6mo")
    brent = _fetch_close("BZ=F", "3mo")

    if wti.empty:
        return {"value": np.nan, "signal": "DATA_ERROR", "risk_score": 50, "macro_bias": "NEUTRAL"}

    current = safe_scalar(wti.iloc[-1])
    mom_20  = _momentum(wti, 20)
    mom_60  = _momentum(wti, 60)
    z_score = _zscore(wti, 60)

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

    return {
        "ticker":        "CL=F",
        "current_price": round(current, 2),
        "mom_20d_pct":   round(mom_20, 2),
        "mom_60d_pct":   round(mom_60, 2),
        "z_score_60d":   round(z_score, 2),
        "signal":        signal,
        "risk_score":    risk_score,
        "macro_bias":    macro_bias,
    }


# ─────────────────────────────────────────────────────────────
# 5. COPPER  — "Dr. Copper" industrial demand barometer
# ─────────────────────────────────────────────────────────────

def analyse_copper() -> dict:
    """
    Copper rising  → industrial expansion, global growth optimism.
    Copper falling → leading recession warning (~6 month lead on GDP).
    """
    prices = _fetch_close("HG=F", "6mo")

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
        "ticker":        "HG=F",
        "current_price": round(safe_scalar(prices.iloc[-1]), 4),
        "mom_20d_pct":   round(mom_20, 2),
        "mom_60d_pct":   round(mom_60, 2),
        "z_score_60d":   round(z_score, 2),
        "signal":        signal,
        "risk_score":    risk_score,
        "macro_bias":    macro_bias,
        "note":          "Copper leads GDP by ~6 months — best early-cycle indicator",
    }


# ─────────────────────────────────────────────────────────────
# 6. GOLD  — risk-off barometer & inflation hedge
# ─────────────────────────────────────────────────────────────

def analyse_gold() -> dict:
    """
    Gold rising + real yields falling  → RISK_OFF  → reduce equity exposure.
    Gold falling + dollar rising       → RISK_ON    → equities favoured.
    """
    prices = _fetch_close("GC=F", "6mo")
    tnx    = _fetch_close("^TNX", "3mo")

    if prices.empty:
        return {"value": np.nan, "signal": "DATA_ERROR", "risk_score": 50, "macro_bias": "NEUTRAL"}

    mom_20    = _momentum(prices, 20)
    mom_60    = _momentum(prices, 60)
    z_score   = _zscore(prices, 60)
    tnx_mom   = _momentum(tnx, 20) if not tnx.empty else 0.0
    risk_off_signal = (mom_20 > 2.0) and (tnx_mom < 0)

    if z_score > 1.5 and risk_off_signal:
        risk_score, signal, macro_bias = 75, "STRONG_RISK_OFF", "DEFENSIVE"
    elif z_score > 0.5 or mom_20 > 1.5:
        risk_score, signal, macro_bias = 55, "MILD_RISK_OFF", "CAUTIOUS"
    elif z_score < -1.0:
        risk_score, signal, macro_bias = 20, "RISK_ON_CONFIRMED", "AGGRESSIVE"
    else:
        risk_score, signal, macro_bias = 40, "NEUTRAL", "NEUTRAL"

    return {
        "ticker":        "GC=F",
        "current_price": round(safe_scalar(prices.iloc[-1]), 2),
        "mom_20d_pct":   round(mom_20, 2),
        "mom_60d_pct":   round(mom_60, 2),
        "z_score_60d":   round(z_score, 2),
        "signal":        signal,
        "risk_score":    risk_score,
        "macro_bias":    macro_bias,
    }


# ─────────────────────────────────────────────────────────────
# 7. EM FLOWS  — foreign fund flow into SET universe
# ─────────────────────────────────────────────────────────────

def analyse_em_flows() -> dict:
    """
    EEM (MSCI EM ETF) relative to SPY: measures whether global funds
    are rotating into or out of emerging markets broadly.

    THD (iShares MSCI Thailand ETF): direct proxy for foreign demand
    for Thai equities — the most SET-specific signal available.

    EM inflow  → SET liquidity tailwind, foreign buying pressure
    EM outflow → SET liquidity headwind, indiscriminate selling
    """
    eem = _fetch_close("EEM", "6mo")
    spy = _fetch_close("SPY", "6mo")
    thd = _fetch_close("THD", "6mo")

    if eem.empty:
        return {"value": np.nan, "signal": "DATA_ERROR", "risk_score": 50,
                "macro_bias": "NEUTRAL", "eem_mom": 0.0, "thd_mom": 0.0}

    eem_mom_20 = _momentum(eem, 20)
    spy_mom_20 = _momentum(spy, 20) if not spy.empty else 0.0
    thd_mom_20 = _momentum(thd, 20) if not thd.empty else 0.0
    eem_z      = _zscore(eem, 60)

    # EM alpha = EEM return minus SPY return over 20 days
    em_alpha = eem_mom_20 - spy_mom_20

    # Signal logic
    if em_alpha > 2.0 and thd_mom_20 > 1.0:
        risk_score, signal, macro_bias = 15, "STRONG_EM_INFLOW", "ADD_EM"
    elif em_alpha > 0 or thd_mom_20 > 1.0:
        risk_score, signal, macro_bias = 30, "MILD_EM_INFLOW", "OVERWEIGHT_EM"
    elif em_alpha < -3.0 and thd_mom_20 < -1.0:
        risk_score, signal, macro_bias = 80, "EM_OUTFLOW_PRESSURE", "REDUCE_EM"
    elif em_alpha < -1.0:
        risk_score, signal, macro_bias = 60, "EM_UNDERPERFORMING", "CAUTIOUS_EM"
    else:
        risk_score, signal, macro_bias = 40, "EM_NEUTRAL", "NEUTRAL"

    return {
        "ticker":        "EEM / THD",
        "current_price": round(safe_scalar(eem.iloc[-1]), 2),
        "eem_mom_20d":   round(eem_mom_20, 2),
        "spy_mom_20d":   round(spy_mom_20, 2),
        "em_alpha_20d":  round(em_alpha, 2),
        "thd_mom_20d":   round(thd_mom_20, 2),
        "mom_20d_pct":   round(em_alpha, 2),    # standardised key for display
        "z_score_60d":   round(eem_z, 2),
        "signal":        signal,
        "risk_score":    risk_score,
        "macro_bias":    macro_bias,
        "note":          "EEM alpha vs SPY + THD direct Thailand flow proxy",
    }


# ─────────────────────────────────────────────────────────────
# 8. CHINA PULSE  — Thailand's #1 trading partner
# ─────────────────────────────────────────────────────────────

def analyse_china_pulse() -> dict:
    """
    MCHI (iShares MSCI China ETF): broad China equity proxy covering
    A-shares, H-shares, and ADRs.

    KWEB (KraneShares China Internet ETF): higher-beta, credit-sensitive
    tech proxy — early warning on Chinese credit stress / stimulus.

    China accelerating → Thai exports (materials, industrials, tourism) benefit.
    China contracting  → Thai export recession risk.
    """
    mchi = _fetch_close("MCHI", "6mo")
    kweb = _fetch_close("KWEB", "6mo")

    if mchi.empty:
        return {"value": np.nan, "signal": "DATA_ERROR", "risk_score": 50,
                "macro_bias": "NEUTRAL", "mchi_mom": 0.0, "kweb_mom": 0.0}

    mchi_mom_20 = _momentum(mchi, 20)
    mchi_mom_60 = _momentum(mchi, 60)
    kweb_mom_20 = _momentum(kweb, 20) if not kweb.empty else 0.0
    mchi_z      = _zscore(mchi, 60)

    # Composite China signal: both MCHI and KWEB rising = broad acceleration
    china_accelerating = (mchi_mom_20 > 3.0) and (kweb_mom_20 > 2.0)
    china_contracting  = (mchi_mom_20 < -3.0) or (mchi_mom_60 < -8.0)

    if china_accelerating:
        risk_score, signal, macro_bias = 15, "CHINA_ACCELERATING", "CYCLICAL_TAILWIND"
    elif mchi_mom_20 > 1.5:
        risk_score, signal, macro_bias = 30, "CHINA_RECOVERY", "MILD_CYCLICAL"
    elif china_contracting and kweb_mom_20 < -3.0:
        risk_score, signal, macro_bias = 80, "CHINA_CONTRACTION", "DEFENSIVE"
    elif china_contracting:
        risk_score, signal, macro_bias = 60, "CHINA_SLOWING", "CAUTIOUS"
    else:
        risk_score, signal, macro_bias = 45, "CHINA_NEUTRAL", "NEUTRAL"

    return {
        "ticker":        "MCHI / KWEB",
        "current_price": round(safe_scalar(mchi.iloc[-1]), 2),
        "mchi_mom_20d":  round(mchi_mom_20, 2),
        "mchi_mom_60d":  round(mchi_mom_60, 2),
        "kweb_mom_20d":  round(kweb_mom_20, 2),
        "mom_20d_pct":   round(mchi_mom_20, 2),     # standardised key for display
        "z_score_60d":   round(mchi_z, 2),
        "signal":        signal,
        "risk_score":    risk_score,
        "macro_bias":    macro_bias,
        "note":          "MCHI broad + KWEB credit-sensitive. Thailand export ~25% to China.",
    }


# ─────────────────────────────────────────────────────────────
# SECTOR MACRO ADJUSTMENT TABLE
# Expanded with new event flags and watchlist-specific sectors.
# ─────────────────────────────────────────────────────────────

SECTOR_MACRO_ADJUSTMENT = {
    #                     ── original flags ──────────────────────────────────────────  ── new flags ───────────────────────────────────────────────────
    #                     oil_up  oil_dn  gold_up dxy_up  cop_up  | ry_rise china_up em_in  thb_wk
    "ENERGY":          {"oil_up": +8,  "oil_down": -12, "gold_up": +3,  "dxy_up": -2, "copper_up": +4,
                        "real_yield_rising": -3, "china_up": +5, "em_inflow": +3, "thb_weakening": +6},
    "FINANCIALS":      {"oil_up": -2,  "oil_down": +3,  "gold_up": -5,  "dxy_up": +5, "copper_up": +3,
                        "real_yield_rising": +6, "china_up": +2, "em_inflow": +5, "thb_weakening": -3},
    "TECH":            {"oil_up": -2,  "oil_down": +3,  "gold_up": -6,  "dxy_up": -2, "copper_up": +2,
                        "real_yield_rising": -8, "china_up": +3, "em_inflow": +3, "thb_weakening": -2},
    "CONSUMER_DISC":   {"oil_up": -6,  "oil_down": +6,  "gold_up": -2,  "dxy_up": -3, "copper_up": +2,
                        "real_yield_rising": -4, "china_up": +4, "em_inflow": +4, "thb_weakening": -5},
    "CONSUMER_STAP":   {"oil_up": -3,  "oil_down": +4,  "gold_up": +4,  "dxy_up": -1, "copper_up":  0,
                        "real_yield_rising": -2, "china_up": +1, "em_inflow": +2, "thb_weakening": -3},
    "HEALTH":          {"oil_up": -1,  "oil_down": +2,  "gold_up": +3,  "dxy_up": -1, "copper_up":  0,
                        "real_yield_rising": -2, "china_up": +2, "em_inflow": +2, "thb_weakening": -1},
    "MATERIALS":       {"oil_up": +4,  "oil_down": -5,  "gold_up": +6,  "dxy_up": -4, "copper_up": +8,
                        "real_yield_rising": -3, "china_up": +8, "em_inflow": +3, "thb_weakening": +5},
    "INDUSTRIALS":     {"oil_up": -4,  "oil_down": +2,  "gold_up":  0,  "dxy_up": -3, "copper_up": +7,
                        "real_yield_rising": -3, "china_up": +7, "em_inflow": +3, "thb_weakening": +3},
    "UTILITIES":       {"oil_up": -3,  "oil_down": +5,  "gold_up": +2,  "dxy_up": -1, "copper_up": +1,
                        "real_yield_rising": -6, "china_up":  0, "em_inflow": +2, "thb_weakening": -2},
    "REIT":            {"oil_up": -2,  "oil_down": +3,  "gold_up": +1,  "dxy_up": -4, "copper_up": +1,
                        "real_yield_rising": -7, "china_up": +1, "em_inflow": +3, "thb_weakening": -3},
    "TRANSPORT":       {"oil_up": -8,  "oil_down": +8,  "gold_up": -1,  "dxy_up": -2, "copper_up": +3,
                        "real_yield_rising": -3, "china_up": +4, "em_inflow": +2, "thb_weakening": +2},
    # Watchlist-specific
    "REIT_PROPERTY":   {"oil_up": -2,  "oil_down": +3,  "gold_up": +1,  "dxy_up": -5, "copper_up": +1,
                        "real_yield_rising": -8, "china_up": +1, "em_inflow": +3, "thb_weakening": -4},
    "WATCHLIST_OTHER": {"oil_up": -2,  "oil_down": +2,  "gold_up": +1,  "dxy_up": -2, "copper_up": +2,
                        "real_yield_rising": -2, "china_up": +2, "em_inflow": +2, "thb_weakening":  0},
}


# ─────────────────────────────────────────────────────────────
# COMPOSITE ORCHESTRATOR
# ─────────────────────────────────────────────────────────────

# Weights reflect importance for a SET-focused fund
_COMPOSITE_WEIGHTS = {
    "real_yield": 0.20,
    "dxy":        0.20,
    "em_flows":   0.15,
    "copper":     0.15,
    "oil":        0.12,
    "china":      0.10,
    "thb":        0.05,
    "gold":       0.03,
}


def run_global_macro_analysis() -> dict:
    """
    Run all 8 macro analyses, compute a weighted composite risk score,
    determine the growth/inflation cycle quadrant, and return sector
    adjustment scores for Stage 2 and Stage 3.

    Returns
    -------
    dict with keys:
        real_yield, dxy, thb, crude_oil, copper, gold, em_flows, china,
        composite_macro_risk, macro_regime, cycle_quadrant,
        sector_adjustments, macro_bias_summary,
        copper_gold_ratio (derived signal)
    """
    real_yield = analyse_real_yield()
    dxy        = analyse_dxy()
    thb        = analyse_thb()
    oil        = analyse_crude_oil()
    copper     = analyse_copper()
    gold       = analyse_gold()
    em_flows   = analyse_em_flows()
    china      = analyse_china_pulse()

    # ── Weighted composite ────────────────────────────────────
    raw_scores = {
        "real_yield": real_yield.get("risk_score", 50),
        "dxy":        dxy.get("risk_score", 50),
        "em_flows":   em_flows.get("risk_score", 50),
        "copper":     copper.get("risk_score", 50),
        "oil":        oil.get("risk_score", 50),
        "china":      china.get("risk_score", 50),
        "thb":        thb.get("risk_score", 50),
        "gold":       gold.get("risk_score", 50),
    }
    composite_macro_risk = round(
        sum(_COMPOSITE_WEIGHTS[k] * v for k, v in raw_scores.items()), 1
    )

    # ── Macro regime label ────────────────────────────────────
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

    # ── Copper/Gold ratio (derived risk appetite signal) ──────
    copper_price = copper.get("current_price", 0) or 0
    gold_price   = gold.get("current_price", 1) or 1
    copper_gold_ratio = round(copper_price / gold_price * 1000, 4)  # normalised ×1000

    # ── Growth / Inflation quadrant ───────────────────────────
    # Growth proxy: copper z-score, EM alpha, China momentum
    growth_proxy = np.mean([
        50 + copper.get("z_score_60d", 0) * 12,
        100 - em_flows.get("risk_score", 50),
        100 - china.get("risk_score", 50),
    ])
    growth_rising = growth_proxy > 58

    # Inflation proxy: oil momentum + real yield level
    inflation_proxy = np.mean([
        oil.get("risk_score", 50),
        real_yield.get("risk_score", 50),
    ])
    inflation_rising = inflation_proxy > 52

    if growth_rising and not inflation_rising:
        cycle_quadrant       = "GOLDILOCKS"
        quadrant_advice      = "Full cyclical exposure — growth equities, EM overweight"
    elif growth_rising and inflation_rising:
        cycle_quadrant       = "OVERHEAT"
        quadrant_advice      = "Commodities, energy, short duration — reduce growth/tech"
    elif not growth_rising and inflation_rising:
        cycle_quadrant       = "STAGFLATION"
        quadrant_advice      = "Most dangerous — energy/gold only, cash, maximum caution"
    else:
        cycle_quadrant       = "RECESSION_RISK"
        quadrant_advice      = "Defensives, cash, low-beta — avoid cyclicals and EM"

    # ── Event flags for sector adjustment lookup ──────────────
    oil_up            = oil.get("mom_20d_pct", 0) > 2
    oil_down          = oil.get("mom_20d_pct", 0) < -2
    gold_up           = gold.get("macro_bias") in ("DEFENSIVE", "CAUTIOUS")
    dxy_up            = dxy.get("mom_20d_pct", 0) > 0.5
    copper_up         = copper.get("mom_20d_pct", 0) > 2
    real_yield_rising = real_yield.get("real_yield_rising", False)
    china_up          = china.get("signal") in ("CHINA_ACCELERATING", "CHINA_RECOVERY")
    em_inflow         = em_flows.get("signal") in ("STRONG_EM_INFLOW", "MILD_EM_INFLOW")
    thb_weakening     = thb.get("signal") in ("THB_SHARP_DEPRECIATION", "THB_MILD_WEAKNESS")

    # ── Sector adjustment scores ──────────────────────────────
    sector_adjustments = {}
    for sector, weights in SECTOR_MACRO_ADJUSTMENT.items():
        adj = 0
        if oil_up:            adj += weights.get("oil_up", 0)
        if oil_down:          adj += weights.get("oil_down", 0)
        if gold_up:           adj += weights.get("gold_up", 0)
        if dxy_up:            adj += weights.get("dxy_up", 0)
        if copper_up:         adj += weights.get("copper_up", 0)
        if real_yield_rising: adj += weights.get("real_yield_rising", 0)
        if china_up:          adj += weights.get("china_up", 0)
        if em_inflow:         adj += weights.get("em_inflow", 0)
        if thb_weakening:     adj += weights.get("thb_weakening", 0)
        sector_adjustments[sector] = int(np.clip(adj, -20, +20))

    # ── Human-readable bias summary ───────────────────────────
    biases          = [s.get("macro_bias", "") for s in
                       [real_yield, dxy, thb, oil, copper, gold, em_flows, china]]
    defensive_count = sum(1 for b in biases if "DEFENSIVE" in b or "RISK_OFF" in b or "REDUCE" in b)
    bullish_count   = sum(1 for b in biases if "GROWTH" in b or "ADD_EM" in b or "CYCLICAL" in b
                          or "OVERWEIGHT" in b or "AGGRESSIVE" in b)

    if defensive_count >= 5:
        macro_bias_summary = "BROADLY_DEFENSIVE — reduce exposure, prefer cash & hard assets"
    elif defensive_count >= 3:
        macro_bias_summary = "MIXED_LEAN_DEFENSIVE — selective, favour quality & low-beta"
    elif bullish_count >= 5:
        macro_bias_summary = "RISK_ON — full exposure, favour cyclicals & growth"
    elif bullish_count >= 3:
        macro_bias_summary = "MILD_RISK_ON — overweight cyclicals, reduce cash"
    else:
        macro_bias_summary = "NEUTRAL — sector selection is the alpha driver"

    return {
        "real_yield":           real_yield,
        "dxy":                  dxy,
        "thb":                  thb,
        "crude_oil":            oil,
        "copper":               copper,
        "gold":                 gold,
        "em_flows":             em_flows,
        "china":                china,
        "composite_macro_risk": composite_macro_risk,
        "macro_regime":         macro_regime,
        "cycle_quadrant":       cycle_quadrant,
        "quadrant_advice":      quadrant_advice,
        "copper_gold_ratio":    copper_gold_ratio,
        "macro_bias_summary":   macro_bias_summary,
        "sector_adjustments":   sector_adjustments,
        "signal_weights":       _COMPOSITE_WEIGHTS,
        "raw_scores":           raw_scores,
    }
