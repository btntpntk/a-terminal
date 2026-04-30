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
from src.universes import UNIVERSE_REGISTRY  # noqa: F401  (re-exported for legacy imports)


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