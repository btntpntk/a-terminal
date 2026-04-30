"""
Institutional Market Fragility Monitor
Three-Layer Risk Framework: Regime → Fragility → Trigger
"""

import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from src.data.providers import fetch_all_data
from src.agents.calculator import get_fin_val, safe_scalar
from src.universes import SET100 as _THAI_LARGE_CAP
SET100_SECTOR_UNIVERSE = _THAI_LARGE_CAP.sectors

# ─────────────────────────────────────────────
# LAYER 1 — REGIME
# ─────────────────────────────────────────────

def calculate_spx_200dma_buffer(spx_data: dict) -> dict:
    """
    Distance of SPX from its 200-Day Moving Average.
    Edge: Prevents long exposure during secular bear markets.
    """
    prices = spx_data["prices"]["Close"]
    sma_200 = prices.rolling(window=200).mean()
    current_price = safe_scalar(prices.iloc[-1])
    current_sma = safe_scalar(sma_200.iloc[-1])

    if np.isnan(current_sma) or current_sma == 0:
        return {"value": np.nan, "signal": "NEUTRAL", "risk_score": 50}

    distance_pct = ((current_price - current_sma) / current_sma) * 100

    # Risk scoring: above 200DMA = lower risk; below = higher risk
    if distance_pct > 5:
        risk_score, signal = 15, "BULL"
    elif distance_pct > 0:
        risk_score, signal = 35, "NEUTRAL_BULL"
    elif distance_pct > -5:
        risk_score, signal = 65, "NEUTRAL_BEAR"
    else:
        risk_score, signal = 90, "BEAR"

    return {
        "current_price": round(current_price, 2),
        "sma_200": round(current_sma, 2),
        "distance_pct": round(distance_pct, 2),
        "signal": signal,
        "risk_score": risk_score
    }


def calculate_yield_curve_spread() -> dict:
    """
    2s/10s Treasury Yield Curve Spread.
    Edge: Leading indicator for bank profitability & credit availability.
    Spread = 10Y Yield − 2Y Yield
    """
    try:
        tnx = yf.Ticker("^TNX")   # 10Y
        irx = yf.Ticker("^IRX")   # 13-week (proxy for 2Y)
        tyx_2y = yf.Ticker("^FVX") # 5Y — fallback for 2Y

        hist_10y = tnx.history(period="5d")["Close"]
        hist_2y_raw = irx.history(period="5d")["Close"]

        if hist_2y_raw.empty:
            hist_2y_raw = tyx_2y.history(period="5d")["Close"]

        # yfinance returns ^TNX / ^IRX / ^FVX already in percentage points
        # (e.g. 4.5 means 4.50%). 1 pct-point = 100 bps.
        y10 = safe_scalar(hist_10y.iloc[-1])
        y2  = safe_scalar(hist_2y_raw.iloc[-1])

        spread_bps = (y10 - y2) * 100   # convert pct-points → basis points

        if spread_bps > 50:
            risk_score, signal = 20, "STEEP_GROWTH"
        elif spread_bps > 0:
            risk_score, signal = 40, "NORMAL"
        elif spread_bps > -25:
            risk_score, signal = 65, "FLAT_WARNING"
        else:
            risk_score, signal = 85, "INVERTED_RECESSION"

        return {
            "yield_10y_pct": round(y10, 3),
            "yield_2y_pct": round(y2, 3),
            "spread_bps": round(spread_bps, 1),
            "signal": signal,
            "risk_score": risk_score
        }
    except Exception as e:
        return {"error": str(e), "spread_bps": np.nan, "risk_score": 50, "signal": "DATA_ERROR"}


def calculate_hy_credit_spread() -> dict:
    """
    High Yield (HY) Credit Spread proxy via HYG vs IEI spread.
    Edge: Credit markets lead equity markets — widening OAS = equity fragility.
    """
    try:
        hyg = yf.Ticker("HYG")    # iShares HY Corp Bond ETF
        iei = yf.Ticker("IEI")    # 3-7Y Treasury (risk-free proxy)

        hyg_hist = hyg.history(period="60d")["Close"]
        iei_hist = iei.history(period="60d")["Close"]

        # 20-day price return divergence (used as fallback and as a direction signal)
        hyg_ret = hyg_hist.pct_change(20).iloc[-1] * 100
        iei_ret = iei_hist.pct_change(20).iloc[-1] * 100

        # Primary path: derive OAS from HYG trailing dividend yield vs current risk-free
        hyg_info = hyg.info
        hy_yield = (
            hyg_info.get("yield")
            or hyg_info.get("trailingAnnualDividendYield")
        )

        # Current 10Y yield as risk-free anchor (updated from hardcoded 4.5%)
        try:
            tnx_last = yf.Ticker("^TNX").history(period="5d")["Close"]
            risk_free = float(tnx_last.iloc[-1]) if not tnx_last.empty else 4.3
        except Exception:
            risk_free = 4.3   # 2026 fallback

        if hy_yield and hy_yield > 0:
            # hy_yield from yfinance is in decimal (e.g. 0.065 = 6.5%)
            hy_yield_pct = hy_yield * 100
            oas_bps = (hy_yield_pct - risk_free) * 100
        else:
            # Fallback: amplify 20d return divergence around a realistic HY OAS baseline.
            # Typical HY OAS range: 300–500 bps; 350 bps = neutral mid-cycle baseline.
            # Each 1% divergence between HYG and IEI is treated as ~100 bps of OAS movement.
            oas_bps = (hyg_ret - iei_ret) * 100 + 350

        if oas_bps < 300:
            risk_score, signal = 15, "TIGHT_BENIGN"
        elif oas_bps < 400:
            risk_score, signal = 40, "MODERATE_RISK"
        elif oas_bps < 600:
            risk_score, signal = 70, "ELEVATED_STRESS"
        else:
            risk_score, signal = 95, "ACUTE_CRISIS"

        return {
            "oas_bps": round(oas_bps, 1),
            "hyg_20d_return_pct": round(hyg_ret, 2),
            "iei_20d_return_pct": round(iei_ret, 2),
            "signal": signal,
            "risk_score": risk_score
        }
    except Exception as e:
        return {"error": str(e), "oas_bps": np.nan, "risk_score": 50, "signal": "DATA_ERROR"}


# ─────────────────────────────────────────────
# LAYER 2 — FRAGILITY
# ─────────────────────────────────────────────

def calculate_breadth_above_50dma(universe_tickers: list = None) -> dict:
    """
    % of S&P 500 stocks trading above their 50DMA.
    Edge: Breadth exhaustion is the most reliable precursor to sharp corrections.
    """
    if universe_tickers is None:
        universe_tickers = [
            t for s in SET100_SECTOR_UNIVERSE.values() for t in s["members"]
        ]

    above_50 = 0
    total = 0
    errors = 0

    for ticker in universe_tickers:
        try:
            hist = yf.Ticker(ticker).history(period="3mo")["Close"]
            if len(hist) < 50:
                continue
            sma50 = hist.rolling(50).mean().iloc[-1]
            current = hist.iloc[-1]
            total += 1
            if current > sma50:
                above_50 += 1
        except Exception:
            errors += 1
            continue

    if total == 0:
        return {"pct_above_50dma": np.nan, "risk_score": 50, "signal": "NO_DATA"}

    pct = (above_50 / total) * 100

    if pct >= 70:
        risk_score, signal = 15, "BROAD_PARTICIPATION"
    elif pct >= 55:
        risk_score, signal = 40, "MODERATE_PARTICIPATION"
    elif pct >= 40:
        risk_score, signal = 65, "NARROW_RALLY"
    else:
        risk_score, signal = 85, "BREADTH_COLLAPSE"

    return {
        "pct_above_50dma": round(pct, 1),
        "stocks_above": above_50,
        "total_checked": total,
        "signal": signal,
        "risk_score": risk_score
    }


def calculate_rsp_spy_ratio() -> dict:
    """
    RSP/SPY ratio: Equal-Weight vs Cap-Weight S&P 500.
    Edge: Extreme mega-cap concentration = idiosyncratic shock vulnerability.
    """
    try:
        rsp = yf.Ticker("RSP")
        spy = yf.Ticker("SPY")

        rsp_hist = rsp.history(period="1y")["Close"]
        spy_hist = spy.history(period="1y")["Close"]

        ratio = rsp_hist / spy_hist
        current_ratio = safe_scalar(ratio.iloc[-1])
        ratio_30d_ago = safe_scalar(ratio.iloc[-30]) if len(ratio) > 30 else current_ratio
        ratio_90d_ago = safe_scalar(ratio.iloc[-90]) if len(ratio) > 90 else current_ratio

        # Change in bps (1 unit = 100 bps)
        change_30d_bps = (current_ratio - ratio_30d_ago) / ratio_30d_ago * 10000

        # Z-score of ratio vs 1Y rolling mean
        rolling_mean = ratio.rolling(252).mean().iloc[-1]
        rolling_std = ratio.rolling(252).std().iloc[-1]
        z_score = (current_ratio - rolling_mean) / rolling_std if rolling_std > 0 else 0

        if z_score > 0.5:
            risk_score, signal = 15, "EQUAL_WEIGHT_LEADING"
        elif z_score > -0.5:
            risk_score, signal = 35, "BALANCED"
        elif z_score > -1.0:
            risk_score, signal = 60, "MEGA_CAP_DOMINANCE"
        else:
            risk_score, signal = 80, "EXTREME_CONCENTRATION"

        return {
            "current_ratio": round(current_ratio, 4),
            "change_30d_bps": round(change_30d_bps, 1),
            "z_score_1y": round(float(z_score), 2),
            "signal": signal,
            "risk_score": risk_score
        }
    except Exception as e:
        return {"error": str(e), "risk_score": 50, "signal": "DATA_ERROR"}


# ─────────────────────────────────────────────
# LAYER 3 — TRIGGER
# ─────────────────────────────────────────────

def calculate_vix_level() -> dict:
    """
    VIX Spot Level — 30-day implied vol of S&P 500 options.
    Edge: High VIX triggers systematic de-grossing from vol-targeting funds.
    """
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="1y")["Close"]
        current_vix = safe_scalar(hist.iloc[-1])

        # 1Y percentile rank
        percentile = (hist < current_vix).mean() * 100

        if current_vix < 15:
            risk_score, signal = 10, "COMPLACENCY"
        elif current_vix < 20:
            risk_score, signal = 30, "NORMAL_UNCERTAINTY"
        elif current_vix < 25:
            risk_score, signal = 55, "ELEVATED_FEAR"
        elif current_vix < 35:
            risk_score, signal = 75, "HIGH_STRESS"
        else:
            risk_score, signal = 95, "PANIC_REGIME"

        return {
            "vix_level": round(current_vix, 2),
            "percentile_1y": round(float(percentile), 1),
            "signal": signal,
            "risk_score": risk_score
        }
    except Exception as e:
        return {"error": str(e), "vix_level": np.nan, "risk_score": 50, "signal": "DATA_ERROR"}


def calculate_vix_term_structure() -> dict:
    """
    VIX Term Structure (M1/M2 Spread) — Roll Yield.
    Roll Yield = VIX_3M (long end) − VIX_9D (short end)
    Edge: Backwardation → liquidity providers pull back → vol vacuums form.

    Using VIX9D as the short-end M1 proxy and VIX3M as the long-end M2 proxy
    gives a purer term-structure slope than spot-vs-3M, since VIX spot (30-day)
    sits between the two and conflates both ends.
    """
    try:
        # VIX term structure via index proxies
        vix9d = yf.Ticker("^VIX9D").history(period="5d")["Close"]   # short end (M1 proxy)
        vix3m = yf.Ticker("^VIX3M").history(period="5d")["Close"]   # long end  (M2 proxy)
        vix_spot = yf.Ticker("^VIX").history(period="5d")["Close"]  # spot — kept for output

        spot     = safe_scalar(vix_spot.iloc[-1])
        m1_short = safe_scalar(vix9d.iloc[-1]) if not vix9d.empty else spot
        m2_long  = safe_scalar(vix3m.iloc[-1]) if not vix3m.empty else spot

        # Roll yield: long-end minus short-end (positive = contango, negative = backwardation)
        roll_yield = m2_long - m1_short

        if roll_yield > 3:
            risk_score, signal = 10, "STEEP_CONTANGO"
        elif roll_yield > 0:
            risk_score, signal = 30, "MILD_CONTANGO"
        elif roll_yield > -3:
            risk_score, signal = 60, "FLAT_WARNING"
        else:
            risk_score, signal = 90, "BACKWARDATION_PANIC"

        return {
            "vix_spot": round(spot, 2),
            "vix_9d": round(m1_short, 2),
            "vix_3m": round(m2_long, 2),
            "roll_yield": round(roll_yield, 2),
            "structure": "CONTANGO" if roll_yield > 0 else "BACKWARDATION",
            "signal": signal,
            "risk_score": risk_score
        }
    except Exception as e:
        return {"error": str(e), "roll_yield": np.nan, "risk_score": 50, "signal": "DATA_ERROR"}


# ─────────────────────────────────────────────
# COMPOSITE SCORING ENGINE
# ─────────────────────────────────────────────

def calculate_composite_risk(regime_scores: list, fragility_scores: list, trigger_scores: list) -> dict:
    """
    Composite Risk = (W_r × R) + (W_f × F) + (W_t × T)
    Weights: Regime 40%, Fragility 40%, Trigger 20%
    Edge: Heavier weights on structural layers avoids whipsawing on daily noise.
    """
    W_r, W_f, W_t = 0.40, 0.40, 0.20

    r_clean = [s for s in regime_scores if not np.isnan(s)]
    f_clean = [s for s in fragility_scores if not np.isnan(s)]
    t_clean = [s for s in trigger_scores if not np.isnan(s)]

    R = np.mean(r_clean) if r_clean else 50
    F = np.mean(f_clean) if f_clean else 50
    T = np.mean(t_clean) if t_clean else 50

    composite = (W_r * R) + (W_f * F) + (W_t * T)

    if composite < 25:
        regime_label = "LOW_RISK"
    elif composite < 45:
        regime_label = "MODERATE"
    elif composite < 65:
        regime_label = "ELEVATED"
    elif composite < 80:
        regime_label = "HIGH"
    else:
        regime_label = "CRITICAL"

    return {
        "composite_risk": round(composite, 1),
        "layer_scores": {"regime": round(R, 1), "fragility": round(F, 1), "trigger": round(T, 1)},
        "weights": {"regime": W_r, "fragility": W_f, "trigger": W_t},
        "regime_label": regime_label
    }


def calculate_confidence(all_normalized_scores: list) -> dict:
    """
    Confidence = Internal Convergence of signals (inverse of dispersion).
    High Confidence (90+): All signals clustered → strong directional read.
    Low Confidence (<50): Conflicted signals → mixed message market.
    """
    clean = [s for s in all_normalized_scores if not np.isnan(s)]
    if len(clean) < 2:
        return {"confidence": 50, "dispersion": np.nan, "signal": "INSUFFICIENT_DATA"}

    variance = np.var(clean)
    std_dev = np.std(clean)

    # Max possible std for 0-100 range ≈ 50
    # Confidence = 100 - normalized_dispersion
    max_std = 50.0
    confidence = max(0, min(100, 100 - (std_dev / max_std * 100)))

    if confidence >= 80:
        signal = "HIGH_CONVERGENCE"
    elif confidence >= 60:
        signal = "MODERATE_CONVERGENCE"
    elif confidence >= 40:
        signal = "MIXED_SIGNALS"
    else:
        signal = "CONFLICTED"

    return {
        "confidence": round(confidence, 1),
        "dispersion_std": round(std_dev, 2),
        "dispersion_variance": round(variance, 2),
        "num_signals": len(clean),
        "signal": signal
    }


# ─────────────────────────────────────────────
# MASTER ORCHESTRATOR
# ─────────────────────────────────────────────

def run_fragility_monitor(breadth_universe: list = None, verbose: bool = True) -> dict:
    """
    Full institutional three-layer fragility monitor.
    Returns a complete risk dashboard with all sub-signals and composite scores.
    """
    print("=" * 60)
    print("  INSTITUTIONAL MARKET FRAGILITY MONITOR")
    print("  Three-Layer Risk Framework")
    print("=" * 60)

    results = {}

    # ── LAYER 1: REGIME ──────────────────────────────────────
    print("\n[1/3] Fetching Regime Layer...")

    spx_data = fetch_all_data("^GSPC")
    dma_result = calculate_spx_200dma_buffer(spx_data)
    yc_result  = calculate_yield_curve_spread()
    hy_result  = calculate_hy_credit_spread()

    results["regime"] = {
        "spx_200dma": dma_result,
        "yield_curve": yc_result,
        "hy_credit_spread": hy_result
    }

    # ── LAYER 2: FRAGILITY ───────────────────────────────────
    print("[2/3] Fetching Fragility Layer (breadth scan)...")

    breadth_result = calculate_breadth_above_50dma(breadth_universe)
    rsp_spy_result = calculate_rsp_spy_ratio()

    results["fragility"] = {
        "breadth_50dma": breadth_result,
        "rsp_spy_ratio": rsp_spy_result
    }

    # ── LAYER 3: TRIGGER ─────────────────────────────────────
    print("[3/3] Fetching Trigger Layer...")

    vix_result  = calculate_vix_level()
    term_result = calculate_vix_term_structure()

    results["trigger"] = {
        "vix_spot": vix_result,
        "vix_term_structure": term_result
    }

    # ── COMPOSITE SCORING ────────────────────────────────────
    regime_scores    = [dma_result.get("risk_score", 50), yc_result.get("risk_score", 50), hy_result.get("risk_score", 50)]
    fragility_scores = [breadth_result.get("risk_score", 50), rsp_spy_result.get("risk_score", 50)]
    trigger_scores   = [vix_result.get("risk_score", 50), term_result.get("risk_score", 50)]
    all_scores       = regime_scores + fragility_scores + trigger_scores

    composite = calculate_composite_risk(regime_scores, fragility_scores, trigger_scores)
    confidence = calculate_confidence(all_scores)

    results["composite"] = composite
    results["confidence"] = confidence

    # ── PRINT DASHBOARD ──────────────────────────────────────
    if verbose:
        print("\n" + "=" * 60)
        print("  RESULTS DASHBOARD")
        print("=" * 60)

        print(f"\n▶ COMPOSITE RISK SCORE : {composite['composite_risk']} / 100  [{composite['regime_label']}]")
        print(f"▶ CONFIDENCE           : {confidence['confidence']} / 100  [{confidence['signal']}]")

        print("\n── REGIME LAYER (40% weight) ──────────────────")
        print(f"  SPX vs 200DMA  : {dma_result.get('distance_pct', 'N/A'):>6}%  | {dma_result.get('signal')}  | Risk: {dma_result.get('risk_score')}")
        print(f"  2s/10s Spread  : {yc_result.get('spread_bps', 'N/A'):>6} bps | {yc_result.get('signal')}  | Risk: {yc_result.get('risk_score')}")
        print(f"  HY OAS         : {hy_result.get('oas_bps', 'N/A'):>6} bps | {hy_result.get('signal')}  | Risk: {hy_result.get('risk_score')}")

        print("\n── FRAGILITY LAYER (40% weight) ───────────────")
        print(f"  Breadth>50DMA  : {breadth_result.get('pct_above_50dma', 'N/A'):>6}%  | {breadth_result.get('signal')}  | Risk: {breadth_result.get('risk_score')}")
        print(f"  RSP/SPY Z-Score: {rsp_spy_result.get('z_score_1y', 'N/A'):>6}σ  | {rsp_spy_result.get('signal')}  | Risk: {rsp_spy_result.get('risk_score')}")

        print("\n── TRIGGER LAYER (20% weight) ─────────────────")
        print(f"  VIX Spot       : {vix_result.get('vix_level', 'N/A'):>6}    | {vix_result.get('signal')}  | Risk: {vix_result.get('risk_score')}")
        print(f"  VIX Roll Yield : {term_result.get('roll_yield', 'N/A'):>6}    | {term_result.get('signal')}  | Risk: {term_result.get('risk_score')}")

        print(f"\n── LAYER AVERAGES ─────────────────────────────")
        ls = composite['layer_scores']
        print(f"  Regime Score   : {ls['regime']}")
        print(f"  Fragility Score: {ls['fragility']}")
        print(f"  Trigger Score  : {ls['trigger']}")
        print("=" * 60)

    return results


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    monitor_results = run_fragility_monitor()