"""
src/agents/technical.py
Stage 4 — Technical Indicator Engine with Adaptive Strategy Selection

Architecture:
  1. Three strategy families: MOMENTUM, MEAN_REVERSION, BREAKOUT
  2. Strategy selector: picks the best family for current market regime
  3. Each strategy produces: entry, TP, SL, R:R, signal_strength
  4. Optimiser: ranks strategies by rolling Sharpe on recent price history
  5. Output: the highest-Sharpe strategy's signals for the current regime
"""

import yfinance as yf
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from src.agents.calculator import safe_scalar


# ─────────────────────────────────────────────────────────────
# OUTPUT DATACLASS
# ─────────────────────────────────────────────────────────────

@dataclass
class TechnicalSignal:
    strategy:        str
    regime_fit:      str        # why this strategy was chosen
    entry_price:     float
    tp_price:        float
    sl_price:        float
    rr_ratio:        float
    signal_strength: int        # 0–100
    atr_14:          float
    indicators:      dict = field(default_factory=dict)
    notes:           str  = ""


# ─────────────────────────────────────────────────────────────
# INDICATOR PRIMITIVES
# ─────────────────────────────────────────────────────────────

def _atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range — the universal volatility ruler."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window).mean()


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(window).mean()
    loss  = (-delta.clip(upper=0)).rolling(window).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series,
          fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast   = close.ewm(span=fast,   adjust=False).mean()
    ema_slow   = close.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def _bollinger(close: pd.Series, window: int = 20, num_std: float = 2.0) -> tuple:
    """Returns (upper_band, middle_band, lower_band, %B)."""
    sma   = close.rolling(window).mean()
    std   = close.rolling(window).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    pct_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return upper, sma, lower, pct_b


def _adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average Directional Index — trend strength (not direction)."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_high  = high.shift(1)
    prev_low   = low.shift(1)
    prev_close = close.shift(1)

    plus_dm  = np.where((high - prev_high) > (prev_low - low),
                        np.maximum(high - prev_high, 0), 0)
    minus_dm = np.where((prev_low - low) > (high - prev_high),
                        np.maximum(prev_low - low, 0), 0)

    tr_series  = _atr(df, 1)   # single-bar TR
    atr_window = tr_series.rolling(window).mean()
    plus_di  = 100 * (pd.Series(plus_dm,  index=df.index).rolling(window).mean() / atr_window)
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(window).mean() / atr_window)
    dx       = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx      = dx.rolling(window).mean()
    return adx.fillna(0)


def _support_resistance(close: pd.Series, window: int = 20) -> tuple:
    """
    Rolling window high (resistance) and low (support).
    Used to snap TP to the nearest resistance level.
    """
    resistance = close.rolling(window).max().iloc[-1]
    support    = close.rolling(window).min().iloc[-1]
    return float(support), float(resistance)


# ─────────────────────────────────────────────────────────────
# REGIME DETECTOR
# ─────────────────────────────────────────────────────────────

def detect_price_regime(df: pd.DataFrame) -> dict:
    """
    Classify the stock's recent price action into one of three regimes:
      TRENDING   — strong directional move (high ADX)
      RANGING    — choppy, mean-reverting (low ADX, tight BB)
      BREAKOUT   — price breaking out of a compression zone

    This drives strategy selection.
    """
    close = df["Close"]

    adx_val  = safe_scalar(_adx(df).iloc[-1])
    atr_val  = safe_scalar(_atr(df).iloc[-1])
    bb_upper, bb_mid, bb_lower, pct_b = _bollinger(close)

    # BB width as % of price — low width = compression
    bb_width_pct = float(((bb_upper - bb_lower) / bb_mid).iloc[-1] * 100)

    current  = float(close.iloc[-1])
    prev_bb_upper = float(bb_upper.iloc[-2]) if len(bb_upper) > 2 else float(bb_upper.iloc[-1])

    # Breakout condition: price today crossed above the prior day's upper band
    is_breakout = current > prev_bb_upper and bb_width_pct < 4.0

    if is_breakout:
        regime = "BREAKOUT"
        reason = f"Price crossed upper BB; BB width compressed at {bb_width_pct:.1f}%"
    elif adx_val > 25:
        regime = "TRENDING"
        reason = f"ADX={adx_val:.1f} — strong directional trend"
    else:
        regime = "RANGING"
        reason = f"ADX={adx_val:.1f} — low trend strength, mean-reversion favoured"

    return {
        "regime":        regime,
        "reason":        reason,
        "adx":           round(adx_val, 1),
        "bb_width_pct":  round(bb_width_pct, 2),
        "atr":           round(atr_val, 4),
        "is_breakout":   is_breakout,
    }


# ─────────────────────────────────────────────────────────────
# STRATEGY IMPLEMENTATIONS
# ─────────────────────────────────────────────────────────────

def strategy_momentum(df: pd.DataFrame, composite_risk: float = 50) -> dict:
    """
    Momentum / Trend-Following Strategy
    Best regime: TRENDING (ADX > 25)

    Entry:  MACD histogram turns positive + RSI > 50 (pullback from uptrend)
    TP:     Entry + 3.0 × ATR14 (snapped to nearest resistance if closer)
    SL:     Entry − 2.0 × ATR14 (below the most recent swing low)
    R:R:    1.5 minimum
    """
    close      = df["Close"]
    atr        = _atr(df)
    rsi        = _rsi(close)
    macd, sig, hist = _macd(close)
    support, resistance = _support_resistance(close)

    current    = float(close.iloc[-1])
    atr_val    = float(atr.iloc[-1])
    rsi_val    = float(rsi.iloc[-1])
    hist_val   = float(hist.iloc[-1])
    hist_prev  = float(hist.iloc[-2]) if len(hist) > 2 else 0.0
    macd_val   = float(macd.iloc[-1])

    # Signal conditions
    macd_cross_up = hist_val > 0 and hist_prev <= 0
    rsi_confirm   = 50 < rsi_val < 75          # in bullish zone, not overbought
    above_ma20    = current > float(close.rolling(20).mean().iloc[-1])

    strength = 0
    if macd_cross_up: strength += 35
    if rsi_confirm:   strength += 30
    if above_ma20:    strength += 20
    if macd_val > 0:  strength += 15

    entry = current
    sl    = entry - (2.0 * atr_val)
    tp_atr = entry + (3.0 * atr_val)
    # Snap TP to resistance if it is closer than the pure ATR target
    tp    = min(tp_atr, resistance) if resistance > entry else tp_atr
    rr    = round((tp - entry) / (entry - sl), 2) if (entry - sl) > 0 else 0.0

    return {
        "strategy": "MOMENTUM",
        "entry": round(entry, 4), "tp": round(tp, 4), "sl": round(sl, 4),
        "rr_ratio": rr, "signal_strength": min(strength, 100), "atr_14": round(atr_val, 4),
        "indicators": {"rsi": round(rsi_val, 1), "macd_hist": round(hist_val, 4),
                       "macd_cross_up": macd_cross_up},
        "notes": "Trend-following; exit if MACD histogram turns negative",
    }


def strategy_mean_reversion(df: pd.DataFrame, composite_risk: float = 50) -> dict:
    """
    Mean Reversion Strategy
    Best regime: RANGING (ADX < 20, low BB width)

    Entry:  RSI < 35 (oversold) + price near or below lower Bollinger Band
    TP:     Middle Bollinger Band (mean reversion target)
    SL:     Entry − 1.5 × ATR14 (below recent low)
    R:R:    Typically 1.2–2.0
    """
    close      = df["Close"]
    atr        = _atr(df)
    rsi        = _rsi(close)
    bb_upper, bb_mid, bb_lower, pct_b = _bollinger(close)

    current  = float(close.iloc[-1])
    atr_val  = float(atr.iloc[-1])
    rsi_val  = float(rsi.iloc[-1])
    pct_b_val = float(pct_b.iloc[-1]) if not np.isnan(pct_b.iloc[-1]) else 0.5
    bb_mid_val = float(bb_mid.iloc[-1])
    bb_low_val = float(bb_lower.iloc[-1])

    # RSI divergence: check if price made lower low but RSI made higher low
    price_lower_low = float(close.iloc[-1]) < float(close.iloc[-5]) if len(close) > 5 else False
    rsi_higher_low  = float(rsi.iloc[-1]) > float(rsi.iloc[-5]) if len(rsi) > 5 else False
    rsi_divergence  = price_lower_low and rsi_higher_low

    strength = 0
    if rsi_val < 30:       strength += 40
    elif rsi_val < 40:     strength += 25
    if pct_b_val < 0.05:   strength += 30    # price at/below lower BB
    elif pct_b_val < 0.20: strength += 15
    if rsi_divergence:     strength += 20
    # Penalise in high-risk environments — mean reversion fails in trending bears
    strength -= int((composite_risk - 50) * 0.3) if composite_risk > 50 else 0

    entry  = current
    sl     = entry - (1.5 * atr_val)
    tp     = bb_mid_val                       # mean reversion target = middle BB
    rr     = round((tp - entry) / (entry - sl), 2) if (entry - sl) > 0 else 0.0

    return {
        "strategy": "MEAN_REVERSION",
        "entry": round(entry, 4), "tp": round(tp, 4), "sl": round(sl, 4),
        "rr_ratio": rr, "signal_strength": min(max(strength, 0), 100), "atr_14": round(atr_val, 4),
        "indicators": {"rsi": round(rsi_val, 1), "pct_b": round(pct_b_val, 3),
                       "rsi_divergence": rsi_divergence},
        "notes": "Mean-reversion; exit at middle BB or if RSI crosses 60",
    }


def strategy_breakout(df: pd.DataFrame, composite_risk: float = 50) -> dict:
    """
    Breakout Strategy
    Best regime: BREAKOUT (BB compression + price crossing upper band)

    Entry:  Price closes above 20-day high with volume confirmation
    TP:     Entry + 4.0 × ATR14 (wider target for explosive moves)
    SL:     Entry − 1.5 × ATR14 (tight — breakouts either work fast or fail)
    R:R:    Typically 2.0–3.0
    """
    close   = df["Close"]
    volume  = df.get("Volume", pd.Series(dtype=float))
    atr     = _atr(df)
    bb_upper, bb_mid, bb_lower, pct_b = _bollinger(close)

    current      = float(close.iloc[-1])
    atr_val      = float(atr.iloc[-1])
    bb_upper_val = float(bb_upper.iloc[-1])
    high_20d     = float(close.rolling(20).max().iloc[-1])
    high_prev    = float(close.rolling(20).max().iloc[-2]) if len(close) > 2 else high_20d

    # Volume confirmation
    vol_confirmed = False
    if not volume.empty and len(volume) > 20:
        avg_vol     = float(volume.rolling(20).mean().iloc[-1])
        current_vol = float(volume.iloc[-1])
        vol_confirmed = current_vol > avg_vol * 1.3

    # BB width compression leading to breakout
    bb_width_prev = float(((bb_upper - bb_lower) / bb_mid).rolling(5).min().iloc[-1] * 100)

    strength = 0
    if current > high_20d:       strength += 35     # breaking 20d high
    if current > bb_upper_val:   strength += 25     # above upper BB
    if vol_confirmed:            strength += 25     # volume surge
    if bb_width_prev < 3.0:      strength += 15     # was compressed

    entry  = current
    sl     = entry - (1.5 * atr_val)
    tp     = entry + (4.0 * atr_val)
    rr     = round((tp - entry) / (entry - sl), 2) if (entry - sl) > 0 else 0.0

    return {
        "strategy": "BREAKOUT",
        "entry": round(entry, 4), "tp": round(tp, 4), "sl": round(sl, 4),
        "rr_ratio": rr, "signal_strength": min(strength, 100), "atr_14": round(atr_val, 4),
        "indicators": {"bb_upper": round(bb_upper_val, 4), "high_20d": round(high_20d, 4),
                       "vol_confirmed": vol_confirmed},
        "notes": "Breakout — use time stop: exit if price doesn't move within 5 sessions",
    }


# ─────────────────────────────────────────────────────────────
# ROLLING SHARPE OPTIMISER
# ─────────────────────────────────────────────────────────────

def _simulate_strategy_returns(df: pd.DataFrame,
                                strategy_fn,
                                lookback_days: int = 60,
                                composite_risk: float = 50) -> float:
    """
    Quick simulation: run strategy on each of the last `lookback_days` windows
    and compute the rolling Sharpe of hypothetical returns.
    Used only to rank strategies — not for backtesting P&L.
    """
    signals  = []
    close    = df["Close"]
    n        = len(df)

    # Minimum required bars: 30 (for indicators) + lookback
    if n < 30 + lookback_days:
        return 0.0

    for i in range(lookback_days, 0, -1):
        try:
            window_df = df.iloc[:n - i + 1].copy()
            if len(window_df) < 30:
                continue
            sig = strategy_fn(window_df, composite_risk)
            # Simulate: if signal fires, next-day return vs ATR stop
            entry = sig["entry"]
            sl    = sig["sl"]
            tp    = sig["tp"]
            # Approximate 1-bar forward return
            if i > 1:
                fwd_price = float(close.iloc[n - i + 1])
                ret = (fwd_price - entry) / entry if entry > 0 else 0.0
            else:
                ret = 0.0
            signals.append(ret)
        except Exception:
            signals.append(0.0)

    if len(signals) < 5:
        return 0.0

    arr   = np.array(signals)
    mu    = arr.mean()
    sigma = arr.std()
    sharpe = (mu / sigma * np.sqrt(252)) if sigma > 0 else 0.0
    return round(float(sharpe), 4)


def optimise_strategy(df: pd.DataFrame,
                      price_regime: dict,
                      composite_risk: float = 50) -> dict:
    """
    Score all three strategies and pick the one with:
      (a) best Sharpe on recent history AND
      (b) highest regime fit for the current price action.

    Regime fit bonus:
      TRENDING  → +0.5 Sharpe bonus to MOMENTUM
      RANGING   → +0.5 Sharpe bonus to MEAN_REVERSION
      BREAKOUT  → +0.5 Sharpe bonus to BREAKOUT

    Returns a dict with all strategy scores and the selected winner.
    """
    regime = price_regime.get("regime", "RANGING")

    strategies = {
        "MOMENTUM":       strategy_momentum,
        "MEAN_REVERSION": strategy_mean_reversion,
        "BREAKOUT":       strategy_breakout,
    }
    regime_bonus = {
        "TRENDING":  {"MOMENTUM": 0.5, "MEAN_REVERSION": -0.3, "BREAKOUT": 0.0},
        "RANGING":   {"MOMENTUM": -0.2, "MEAN_REVERSION": 0.5, "BREAKOUT": -0.1},
        "BREAKOUT":  {"MOMENTUM": 0.1, "MEAN_REVERSION": -0.2, "BREAKOUT": 0.5},
    }.get(regime, {})

    scores = {}
    for name, fn in strategies.items():
        sharpe = _simulate_strategy_returns(df, fn, lookback_days=60, composite_risk=composite_risk)
        bonus  = regime_bonus.get(name, 0.0)
        scores[name] = round(sharpe + bonus, 4)

    best_strategy = max(scores, key=scores.get)

    return {
        "sharpe_scores":   scores,
        "regime_bonuses":  regime_bonus,
        "selected":        best_strategy,
        "selection_reason": f"Best Sharpe+regime fit in {regime} environment",
    }


# ─────────────────────────────────────────────────────────────
# MASTER ORCHESTRATOR
# ─────────────────────────────────────────────────────────────

def run_technical_analysis(ticker: str,
                            composite_risk: float = 50,
                            force_strategy: Optional[str] = None) -> TechnicalSignal:
    """
    Full technical analysis pipeline for a single stock.

    1. Fetch OHLCV price data
    2. Detect price regime (TRENDING / RANGING / BREAKOUT)
    3. Optimise strategy selection via rolling Sharpe
    4. Run the winning strategy to produce entry, TP, SL, R:R
    5. Return a TechnicalSignal dataclass

    Parameters
    ----------
    composite_risk : float
        Stage 1 composite risk score. Raises bar for mean-reversion entries.
    force_strategy : str, optional
        Override auto-selection. One of 'MOMENTUM', 'MEAN_REVERSION', 'BREAKOUT'.

    Returns
    -------
    TechnicalSignal — the final trade setup.
    """
    # ── 1. Fetch data ─────────────────────────────────────────
    try:
        df = yf.Ticker(ticker).history(period="1y", interval="1d")
        df = df.dropna(subset=["Close", "High", "Low"])
        if len(df) < 60:
            raise ValueError(f"Insufficient price history for {ticker}: {len(df)} bars")
    except Exception as e:
        raise RuntimeError(f"Data fetch failed for {ticker}: {e}")

    # ── 2. Detect regime ──────────────────────────────────────
    price_regime = detect_price_regime(df)

    # ── 3. Optimise strategy ──────────────────────────────────
    if force_strategy:
        selected = force_strategy.upper()
        optimisation = {"selected": selected,
                        "selection_reason": f"Manually forced to {selected}",
                        "sharpe_scores": {}, "regime_bonuses": {}}
    else:
        optimisation = optimise_strategy(df, price_regime, composite_risk)
        selected = optimisation["selected"]

    # ── 4. Run selected strategy ──────────────────────────────
    strategy_map = {
        "MOMENTUM":       strategy_momentum,
        "MEAN_REVERSION": strategy_mean_reversion,
        "BREAKOUT":       strategy_breakout,
    }
    strategy_fn = strategy_map.get(selected, strategy_momentum)
    sig = strategy_fn(df, composite_risk)

    # ── 5. R:R gate — minimum 1:1.5 ──────────────────────────
    if sig["rr_ratio"] < 1.5:
        sig["notes"] += " | WARNING: R:R below 1.5 — consider skipping this setup"
        sig["signal_strength"] = max(0, sig["signal_strength"] - 20)

    return TechnicalSignal(
        strategy        = selected,
        regime_fit      = price_regime["reason"],
        entry_price     = sig["entry"],
        tp_price        = sig["tp"],
        sl_price        = sig["sl"],
        rr_ratio        = sig["rr_ratio"],
        signal_strength = sig["signal_strength"],
        atr_14          = sig["atr_14"],
        indicators      = {
            **sig.get("indicators", {}),
            "price_regime":     price_regime["regime"],
            "adx":              price_regime["adx"],
            "optimisation":     optimisation,
        },
        notes = sig.get("notes", ""),
    )