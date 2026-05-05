"""
Chandelier Exit Strategy.

Translates the Chandelier Exit (Alex Orekhov) from PineScript.
Uses ATR-based trailing stops to determine trend direction.

Long stop  = Highest(close, length) - mult × ATR(length)  [ratchets up]
Short stop = Lowest(close,  length) + mult × ATR(length)  [ratchets down]

Entry : direction switches to +1 (close crosses above previous short stop)
Exit  : direction switches to -1 (close crosses below previous long stop)

Includes the SET circuit-breaker ATR filter: bars with daily change >= ceiling_thresh
have their ATR contribution replaced by the previous bar's ATR value.
OHLCV fetched per ticker; falls back to close-only if unavailable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtesting.interfaces import TradingStrategy
from ._ohlcv import load_ohlcv


def _filtered_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int,
    ceiling_thresh: float = 0.25,
) -> pd.Series:
    """Wilder ATR with circuit-breaker filter (exclude large daily moves)."""
    # True range (single bar)
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    daily_chg = (close / prev_close - 1.0).abs()
    tr_filtered = tr.copy()

    # Replace filtered bars with previous bar's TR
    tr_vals   = tr.values.copy()
    chg_vals  = daily_chg.values
    for i in range(1, len(tr_vals)):
        if not np.isnan(chg_vals[i]) and chg_vals[i] >= ceiling_thresh:
            tr_vals[i] = tr_vals[i-1]

    tr_clean = pd.Series(tr_vals, index=close.index)
    return tr_clean.ewm(alpha=1.0/period, adjust=False, min_periods=period).mean()


def _chandelier_direction(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int,
    mult: float,
    ceiling_thresh: float,
) -> pd.Series:
    """Return +1.0 / -1.0 direction series."""
    atr = _filtered_atr(high, low, close, period, ceiling_thresh)

    high_src = close.rolling(period).max()   # useClose=True (conservative)
    low_src  = close.rolling(period).min()

    c_v  = close.values.astype(float)
    a_v  = atr.values
    hs_v = high_src.values
    ls_v = low_src.values
    n    = len(c_v)

    long_stop  = np.full(n, np.nan)
    short_stop = np.full(n, np.nan)
    direction  = np.ones(n)

    # Initialise first valid bar
    for i in range(n):
        if not np.isnan(a_v[i]) and not np.isnan(hs_v[i]):
            long_stop[i]  = hs_v[i] - mult * a_v[i]
            short_stop[i] = ls_v[i] + mult * a_v[i]
            break

    for i in range(1, n):
        if np.isnan(a_v[i]) or np.isnan(hs_v[i]):
            long_stop[i]  = long_stop[i-1]
            short_stop[i] = short_stop[i-1]
            direction[i]  = direction[i-1]
            continue

        ls_base = hs_v[i] - mult * a_v[i]
        ss_base = ls_v[i] + mult * a_v[i]

        ls_prev = long_stop[i-1]  if not np.isnan(long_stop[i-1])  else ls_base
        ss_prev = short_stop[i-1] if not np.isnan(short_stop[i-1]) else ss_base

        # Ratchet long stop upward if yesterday's close was above it
        long_stop[i]  = max(ls_base, ls_prev) if c_v[i-1] > ls_prev else ls_base
        # Ratchet short stop downward if yesterday's close was below it
        short_stop[i] = min(ss_base, ss_prev) if c_v[i-1] < ss_prev else ss_base

        # Direction: current close vs previous stops
        if c_v[i] > ss_prev:
            direction[i] = 1.0
        elif c_v[i] < ls_prev:
            direction[i] = -1.0
        else:
            direction[i] = direction[i-1]

    return pd.Series(direction, index=close.index)


class ChandelierExitStrategy(TradingStrategy):
    """Long when Chandelier Exit direction is +1, flat when -1."""
    name = "Chandelier Exit"
    supports_short = False

    def __init__(
        self,
        period: int = 22,
        mult: float = 3.0,
        ceiling_thresh: float = 0.25,
    ):
        self.period = period
        self.mult = mult
        self.ceiling_thresh = ceiling_thresh

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        start = prices.index[0].strftime("%Y-%m-%d")
        end   = prices.index[-1].strftime("%Y-%m-%d")

        for ticker in prices.columns:
            ohlcv = load_ohlcv(ticker, start, end)

            if ohlcv.empty:
                c = prices[ticker].dropna()
                direction = _chandelier_direction(
                    c, c, c, self.period, self.mult, self.ceiling_thresh
                )
            else:
                ohlcv = ohlcv.reindex(prices.index, method="ffill").dropna(subset=["close"])
                if ohlcv.empty:
                    continue
                direction = _chandelier_direction(
                    ohlcv["high"], ohlcv["low"], ohlcv["close"],
                    self.period, self.mult, self.ceiling_thresh,
                )

            direction = direction.reindex(prices.index).ffill().fillna(1.0)
            signals[ticker] = (direction == 1.0).astype(float)

        return signals
