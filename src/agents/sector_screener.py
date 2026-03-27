"""
src/agents/sector_screener.py
Stage 2 — Sector Overall

Ranks sectors by relative strength, momentum, and breadth.
Applies macro alignment bonuses from global_macro.py.
Outputs a ranked list with per-sector scores and a sector_gate decision.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from src.agents.calculator import safe_scalar
from src.agents.global_macro import run_global_macro_analysis


# ─────────────────────────────────────────────────────────────
# SECTOR UNIVERSE DEFINITIONS
# ─────────────────────────────────────────────────────────────

# SET-focused sector ETF proxies (using available yfinance tickers).
# Where a Thai-specific ETF doesn't exist we use the global equivalent
# as a directional proxy and mark it with (PROXY).
SET_SECTOR_UNIVERSE = {
    "ENERGY":        {"etf": "PTT.BK",     "members": ["PTT.BK", "PTTEP.BK", "TOP.BK", "EGCO.BK", "RATCH.BK"]},
    "FINANCIALS":    {"etf": "KBANK.BK",   "members": ["KBANK.BK", "SCB.BK", "BBL.BK", "KTB.BK", "TISCO.BK", "KKP.BK", "KTC.BK", "MTC.BK", "TIDLOR.BK"]},
    "TECH":          {"etf": "DELTA.BK",   "members": ["DELTA.BK", "ADVANC.BK", "TRUE.BK", "COM7.BK"]},
    "CONSUMER_DISC": {"etf": "CPALL.BK",   "members": ["CPALL.BK", "BJC.BK", "HMPRO.BK", "CENTEL.BK", "MINT.BK", "CRC.BK", "GLOBAL.BK", "OSP.BK", "CBG.BK"]},
    "CONSUMER_STAP": {"etf": "CPF.BK",     "members": ["CPF.BK", "TU.BK"]},
    "HEALTH":        {"etf": "BDMS.BK",    "members": ["BDMS.BK", "BH.BK"]},
    "MATERIALS":     {"etf": "SCC.BK",     "members": ["SCC.BK", "IVL.BK", "PTTGC.BK", "SCGP.BK"]},
    "INDUSTRIALS":   {"etf": "BEM.BK",     "members": ["BEM.BK", "BTS.BK", "AOT.BK"]},
    "UTILITIES":     {"etf": "BGRIM.BK",   "members": ["BGRIM.BK", "GPSC.BK", "GULF.BK", "EA.BK"]},
    "REIT":          {"etf": "WHA.BK",     "members": ["WHA.BK", "CPN.BK", "AWC.BK", "LH.BK"]},
    "TRANSPORT":     {"etf": "BANPU.BK",   "members": ["BANPU.BK"]},
}

# SET50 index as the benchmark for relative-strength calculations
SET_BENCHMARK = "^SET.BK"
# Fallback benchmark if SET is unavailable
FALLBACK_BENCHMARK = "EWY"   # iShares MSCI South Korea ETF — closest EM proxy


# ─────────────────────────────────────────────────────────────
# SET100 UNIVERSE  (expanded from SET50 + ~30 additional stocks)
# ─────────────────────────────────────────────────────────────

SET100_SECTOR_UNIVERSE = {
    "ENERGY":        {"etf": "PTT.BK",   "members": ["PTT.BK", "PTTEP.BK", "TOP.BK", "EGCO.BK", "RATCH.BK", "OR.BK", "IRPC.BK"]},
    "FINANCIALS":    {"etf": "KBANK.BK", "members": ["KBANK.BK", "SCB.BK", "BBL.BK", "KTB.BK", "TISCO.BK", "KKP.BK", "KTC.BK", "MTC.BK", "TIDLOR.BK", "BAY.BK", "TCAP.BK"]},
    "TECH":          {"etf": "DELTA.BK", "members": ["DELTA.BK", "ADVANC.BK", "TRUE.BK", "COM7.BK", "HANA.BK", "INSET.BK"]},
    "CONSUMER_DISC": {"etf": "CPALL.BK", "members": ["CPALL.BK", "BJC.BK", "HMPRO.BK", "CENTEL.BK", "MINT.BK", "CRC.BK", "GLOBAL.BK", "OSP.BK", "CBG.BK", "BEAUTY.BK"]},
    "CONSUMER_STAP": {"etf": "CPF.BK",   "members": ["CPF.BK", "TU.BK", "GFPT.BK", "TFG.BK"]},
    "HEALTH":        {"etf": "BDMS.BK",  "members": ["BDMS.BK", "BH.BK", "BCH.BK", "CHG.BK", "PRINC.BK"]},
    "MATERIALS":     {"etf": "SCC.BK",   "members": ["SCC.BK", "IVL.BK", "PTTGC.BK", "SCGP.BK", "SCCC.BK"]},
    "INDUSTRIALS":   {"etf": "BEM.BK",   "members": ["BEM.BK", "BTS.BK", "AOT.BK", "AMATA.BK", "CK.BK"]},
    "UTILITIES":     {"etf": "BGRIM.BK", "members": ["BGRIM.BK", "GPSC.BK", "GULF.BK", "EA.BK", "GUNKUL.BK", "BCPG.BK", "DEMCO.BK"]},
    "REIT":          {"etf": "WHA.BK",   "members": ["WHA.BK", "CPN.BK", "AWC.BK", "LH.BK", "SPALI.BK", "AP.BK", "SC.BK", "LPN.BK"]},
    "TRANSPORT":     {"etf": "BANPU.BK", "members": ["BANPU.BK", "AAV.BK"]},
}


# ─────────────────────────────────────────────────────────────
# PERSONAL WATCHLIST UNIVERSE
# ─────────────────────────────────────────────────────────────

WATCHLIST_SECTOR_UNIVERSE = {
    "ENERGY":          {"etf": "PTT.BK",   "members": ["PTT.BK", "PTTEP.BK", "EGCO.BK", "RATCH.BK", "OR.BK", "BANPU.BK", "GULF.BK", "BKV"]},
    "FINANCIALS":      {"etf": "KBANK.BK", "members": ["BBL.BK", "KBANK.BK", "KTB.BK", "SCB.BK", "TIDLOR.BK", "TTB.BK", "NEO.BK"]},
    "TECH":            {"etf": "DELTA.BK", "members": ["DELTA.BK", "ADVANC.BK", "KCE.BK", "SIS.BK", "SFLEX.BK"]},
    "CONSUMER_DISC":   {"etf": "CPALL.BK", "members": ["CPALL.BK", "CPAXT.BK", "CRC.BK", "HMPRO.BK", "GLOBAL.BK", "OSP.BK", "ERW.BK", "MINT.BK", "SABINA.BK"]},
    "HEALTH":          {"etf": "BDMS.BK",  "members": ["BDMS.BK", "BH.BK", "BCH.BK", "MEGA.BK"]},
    "MATERIALS":       {"etf": "SCC.BK",   "members": ["SCC.BK"]},
    "REIT_PROPERTY":   {"etf": "CPN.BK",   "members": ["CPN.BK", "LH.BK", "WHA.BK", "SPALI.BK", "PF.BK"]},
    "INDUSTRIALS":     {"etf": "AOT.BK",   "members": ["AOT.BK"]},
    "WATCHLIST_OTHER": {"etf": "HL.BK",    "members": ["HL.BK", "NKT.BK", "PR9.BK", "RBF.BK", "SISB.BK"]},
}


# ─────────────────────────────────────────────────────────────
# S&P 500 UNIVERSE  (11 GICS sectors, ~10 large-caps each)
# ETF proxies: SPDR Select Sector ETFs (XL*)
# ─────────────────────────────────────────────────────────────

SP500_SECTOR_UNIVERSE = {
    "TECH":            {"etf": "XLK",  "members": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "CSCO", "AMAT", "QCOM"]},
    "HEALTH":          {"etf": "XLV",  "members": ["UNH", "LLY", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "AMGN", "ISRG"]},
    "FINANCIALS":      {"etf": "XLF",  "members": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BLK", "AXP"]},
    "CONSUMER_DISC":   {"etf": "XLY",  "members": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "BKNG", "TGT", "GM"]},
    "COMM_SERVICES":   {"etf": "XLC",  "members": ["META", "GOOGL", "NFLX", "DIS", "TMUS", "VZ", "T", "CMCSA", "EA", "TTWO"]},
    "INDUSTRIALS":     {"etf": "XLI",  "members": ["GE", "CAT", "HON", "RTX", "UPS", "LMT", "DE", "BA", "FDX", "CSX"]},
    "CONSUMER_STAP":   {"etf": "XLP",  "members": ["WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "CL", "MDLZ", "KHC"]},
    "ENERGY":          {"etf": "XLE",  "members": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL"]},
    "UTILITIES":       {"etf": "XLU",  "members": ["NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "ED", "ETR"]},
    "REAL_ESTATE":     {"etf": "XLRE", "members": ["PLD", "AMT", "EQIX", "CCI", "PSA", "SPG", "WELL", "DLR", "O", "AVB"]},
    "MATERIALS":       {"etf": "XLB",  "members": ["LIN", "APD", "ECL", "SHW", "FCX", "NEM", "NUE", "VMC", "MLM", "ALB"]},
}


# ─────────────────────────────────────────────────────────────
# UNIVERSE REGISTRY  (used by cli4.py for runtime selection)
# ─────────────────────────────────────────────────────────────

UNIVERSE_REGISTRY = {
    "SET100": {
        "display_name":       "SET100 Thailand",
        "universe":           SET100_SECTOR_UNIVERSE,
        "benchmark":          "^SET.BK",
        "fallback_benchmark": "EWY",
    },
    "WATCHLIST": {
        "display_name":       "Personal Watchlist",
        "universe":           WATCHLIST_SECTOR_UNIVERSE,
        "benchmark":          "^SET.BK",
        "fallback_benchmark": "EWY",
    },
    "SP500": {
        "display_name":       "S&P 500 Large-Cap",
        "universe":           SP500_SECTOR_UNIVERSE,
        "benchmark":          "SPY",
        "fallback_benchmark": "^GSPC",
    },
}


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _fetch(ticker: str, period: str = "6mo") -> pd.Series:
    try:
        s = yf.Ticker(ticker).history(period=period)["Close"].dropna()
        return s
    except Exception:
        return pd.Series(dtype=float)


def _momentum(series: pd.Series, window: int) -> float:
    if len(series) <= window:
        return 0.0
    return float((series.iloc[-1] / series.iloc[-window] - 1) * 100)


def _relative_strength(sector: pd.Series, benchmark: pd.Series) -> float:
    """
    RS Ratio: (sector 20d return) − (benchmark 20d return).
    Positive = outperforming the index.
    """
    combined = pd.concat([sector, benchmark], axis=1).dropna()
    if len(combined) < 21:
        return 0.0
    s_ret = (combined.iloc[-1, 0] / combined.iloc[-21, 0] - 1) * 100
    b_ret = (combined.iloc[-1, 1] / combined.iloc[-21, 1] - 1) * 100
    return round(float(s_ret - b_ret), 2)


def _breadth_above_50dma(tickers: list) -> float:
    """% of sector members trading above their 50DMA."""
    above, total = 0, 0
    for t in tickers:
        try:
            hist = _fetch(t, "3mo")
            if len(hist) < 50:
                continue
            sma50 = hist.rolling(50).mean().iloc[-1]
            total += 1
            if hist.iloc[-1] > sma50:
                above += 1
        except Exception:
            continue
    return round((above / total * 100), 1) if total > 0 else 50.0


def _volume_flow(ticker: str) -> float:
    """
    Simple OBV-style volume flow: +1 if price up on high vol, -1 if down.
    Returns average over last 10 days (range -1 to +1).
    """
    try:
        df = yf.Ticker(ticker).history(period="1mo")[["Close", "Volume"]].dropna()
        if len(df) < 10:
            return 0.0
        df = df.tail(10).copy()
        df["ret"] = df["Close"].pct_change()
        df["avg_vol"] = df["Volume"].mean()
        df["flow"] = np.where(df["ret"] > 0, 1, -1) * (df["Volume"] / df["avg_vol"])
        return round(float(df["flow"].mean()), 3)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────
# SECTOR ANALYSER
# ─────────────────────────────────────────────────────────────

def analyse_sector(sector_name: str, config: dict, benchmark: pd.Series,
                   macro_adjustment: int = 0) -> dict:
    """
    Score a single sector across 4 dimensions:
      1. Momentum (20d, 60d)
      2. Relative strength vs benchmark
      3. Internal breadth (% above 50DMA)
      4. Volume flow
    Then apply global macro adjustment from global_macro.py.

    Returns a dict with raw metrics and a composite sector_score (0-100).
    """
    etf_prices = _fetch(config["etf"], "6mo")
    if etf_prices.empty:
        return {"sector": sector_name, "sector_score": 50, "signal": "NO_DATA",
                "gate_pass": False, "macro_adj": macro_adjustment}

    mom_20  = _momentum(etf_prices, 20)
    mom_60  = _momentum(etf_prices, 60)
    rs      = _relative_strength(etf_prices, benchmark)
    breadth = _breadth_above_50dma(config["members"])
    vol_flow = _volume_flow(config["etf"])

    # ── Base scoring (0–100 before macro adj) ────────────────
    score = 50.0   # neutral anchor

    # 1. Momentum (max ±20)
    score += np.clip(mom_20 * 1.5, -20, 20)

    # 2. Relative strength (max ±20)
    score += np.clip(rs * 2.0, -20, 20)

    # 3. Breadth (max ±15)
    score += (breadth - 50) * 0.30   # 50% breadth = neutral

    # 4. Volume flow (max ±10)
    score += np.clip(vol_flow * 8, -10, 10)

    # 5. Macro alignment adjustment (max ±20, from global_macro)
    score += macro_adjustment

    score = float(np.clip(score, 0, 100))

    # ── Signal label ─────────────────────────────────────────
    if score >= 70:
        signal, gate_pass = "STRONG_BUY_SECTOR", True
    elif score >= 58:
        signal, gate_pass = "MILD_OVERWEIGHT", True
    elif score >= 45:
        signal, gate_pass = "NEUTRAL_HOLD", False
    elif score >= 35:
        signal, gate_pass = "MILD_UNDERWEIGHT", False
    else:
        signal, gate_pass = "AVOID_SECTOR", False

    return {
        "sector":        sector_name,
        "etf":           config["etf"],
        "mom_20d_pct":   round(mom_20, 2),
        "mom_60d_pct":   round(mom_60, 2),
        "rs_vs_index":   round(rs, 2),
        "breadth_pct":   breadth,
        "volume_flow":   round(vol_flow, 3),
        "macro_adj":     macro_adjustment,
        "sector_score":  round(score, 1),
        "signal":        signal,
        "gate_pass":     gate_pass,
    }


# ─────────────────────────────────────────────────────────────
# MASTER ORCHESTRATOR
# ─────────────────────────────────────────────────────────────

def run_sector_screener(macro_results: dict = None,
                        custom_universe: dict = None,
                        benchmark_ticker: str = None) -> dict:
    """
    Run the full sector screen.

    Parameters
    ----------
    macro_results : dict, optional
        Output from run_global_macro_analysis(). If None, runs internally.
    custom_universe : dict, optional
        Override SET_SECTOR_UNIVERSE with a custom sector/ETF mapping.

    Returns
    -------
    dict with keys:
        ranked_sectors  : list of sector dicts sorted by sector_score desc
        top_sectors     : list[str] — top 3 sector names
        avoid_sectors   : list[str] — sectors with gate_pass=False
        sector_gate     : bool — True if at least 2 sectors pass
        sector_rotation : str — regime label (EARLY_CYCLE, LATE_CYCLE, etc.)
        macro_used      : dict — the macro analysis used
    """
    universe = custom_universe or SET_SECTOR_UNIVERSE

    # ── 1. Get macro sector adjustments ──────────────────────
    if macro_results is None:
        macro_results = run_global_macro_analysis()
    sector_adjustments = macro_results.get("sector_adjustments", {})

    # ── 2. Fetch benchmark ───────────────────────────────────
    primary   = benchmark_ticker or SET_BENCHMARK
    benchmark = _fetch(primary, "6mo")
    if benchmark.empty:
        benchmark = _fetch(FALLBACK_BENCHMARK, "6mo")

    # ── 3. Score each sector ─────────────────────────────────
    results = []
    for name, config in universe.items():
        adj = sector_adjustments.get(name, 0)
        result = analyse_sector(name, config, benchmark, macro_adjustment=adj)
        results.append(result)

    # ── 4. Rank ───────────────────────────────────────────────
    ranked = sorted(results, key=lambda x: x["sector_score"], reverse=True)
    top_sectors   = [s["sector"] for s in ranked if s["gate_pass"]][:3]
    avoid_sectors = [s["sector"] for s in ranked if not s["gate_pass"]]

    # ── 5. Sector rotation regime detection ──────────────────
    top_names_set = set(top_sectors)
    if "TECH" in top_names_set and "CONSUMER_DISC" in top_names_set:
        rotation = "EARLY_CYCLE_GROWTH"
    elif "ENERGY" in top_names_set and "MATERIALS" in top_names_set:
        rotation = "LATE_CYCLE_INFLATIONARY"
    elif "UTILITIES" in top_names_set and "HEALTH" in top_names_set:
        rotation = "DEFENSIVE_LATE_BEAR"
    elif "FINANCIALS" in top_names_set:
        rotation = "MID_CYCLE_EXPANSION"
    else:
        rotation = "TRANSITION_MIXED"

    return {
        "ranked_sectors":  ranked,
        "top_sectors":     top_sectors,
        "avoid_sectors":   avoid_sectors,
        "sector_gate":     len(top_sectors) >= 1,
        "sector_rotation": rotation,
        "macro_used":      macro_results,
    }


def get_sector_for_ticker(ticker: str,
                          universe: dict = None) -> str:
    """
    Look up which sector a ticker belongs to.
    Returns 'UNKNOWN' if not found.
    Used in Stage 3 to apply macro sector adjustments to the alpha score.
    """
    u = universe or SET_SECTOR_UNIVERSE
    for sector, config in u.items():
        if ticker.upper() in [m.upper() for m in config["members"]]:
            return sector
    return "UNKNOWN"