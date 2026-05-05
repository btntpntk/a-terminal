"""
Pivot Point Supertrend Strategy.

Translates LonesomeTheBlue's Pivot Point Supertrend from PineScript.
ATR-based bands are anchored to the midpoint of the latest confirmed pivot high/low.
Trend switches when the pivot midpoint crosses the opposite band.

Entry : trend = +1 (price above dynamic support)
Exit  : trend = -1 (price below dynamic resistance)

NOTE: pivot confirmation requires `prd` right-side bars, matching the PineScript behaviour.
      OHLCV is fetched per ticker; falls back to close-only if unavailable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtesting.interfaces import TradingStrategy
from ._ohlcv import load_ohlcv, wilder_atr


def _pivot_series(src: pd.Series, left: int, right: int, is_high: bool) -> pd.Series:
    """
    Return pivot values at the confirmation bar (i.e., `right` bars after the pivot).
    Matches ta.pivothigh / ta.pivotlow semantics.
    """
    arr = src.values.astype(float)
    n = len(arr)
    result = np.full(n, np.nan)

    for i in range(left, n - right):
        win_l = arr[i - left:i]
        win_r = arr[i + 1:i + right + 1]
        if len(win_l) < left or len(win_r) < right:
            continue
        if is_high:
            if arr[i] >= np.max(win_l) and arr[i] >= np.max(win_r):
                result[i + right] = arr[i]
        else:
            if arr[i] <= np.min(win_l) and arr[i] <= np.min(win_r):
                result[i + right] = arr[i]

    return pd.Series(result, index=src.index)


def _pp_supertrend_trend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    prd: int,
    factor: float,
    atr_period: int,
) -> pd.Series:
    """Return +1.0 / -1.0 series for Pivot Point Supertrend trend direction."""
    atr = wilder_atr(high, low, close, atr_period)

    ph_v = _pivot_series(high, prd, prd, is_high=True).values
    pl_v = _pivot_series(low,  prd, prd, is_high=False).values
    c_v = close.values.astype(float)
    a_v = atr.values

    n = len(c_v)
    UP    = np.full(n, np.nan)
    DN    = np.full(n, np.nan)
    TUp   = np.full(n, np.nan)
    TDown = np.full(n, np.nan)
    trend = np.ones(n)

    for i in range(1, n):
        # Update last confirmed pivot anchors
        UP[i] = ph_v[i] if not np.isnan(ph_v[i]) else (UP[i-1] if not np.isnan(UP[i-1]) else c_v[i])
        DN[i] = pl_v[i] if not np.isnan(pl_v[i]) else (DN[i-1] if not np.isnan(DN[i-1]) else c_v[i])

        pivot = c_v[i] if (np.isnan(UP[i]) or np.isnan(DN[i])) else (UP[i] + DN[i]) / 2.0
        a = a_v[i] if not np.isnan(a_v[i]) else 0.0

        ls_base = pivot - factor * a
        ss_base = pivot + factor * a

        tup_prev = TUp[i-1]   if not np.isnan(TUp[i-1])   else ls_base
        tdn_prev = TDown[i-1] if not np.isnan(TDown[i-1]) else ss_base

        # TUp ratchets up when pivot is above it (trailing support)
        TUp[i]   = max(ls_base, tup_prev) if pivot > tup_prev else ls_base
        # TDown ratchets down when pivot is below it (trailing resistance)
        TDown[i] = min(ss_base, tdn_prev) if pivot < tdn_prev else ss_base

        # Trend state: pivot crosses above TDown → bull; below TUp → bear
        if pivot > tdn_prev:
            trend[i] = 1.0
        elif pivot < tup_prev:
            trend[i] = -1.0
        else:
            trend[i] = trend[i-1]

    return pd.Series(trend, index=close.index)


class PivotPointSupertrendStrategy(TradingStrategy):
    """Long when Pivot Point Supertrend is bullish, flat when bearish."""
    name = "Pivot Point Supertrend"
    supports_short = False

    def __init__(
        self,
        prd: int = 2,
        factor: float = 3.0,
        atr_period: int = 10,
    ):
        self.prd = prd
        self.factor = factor
        self.atr_period = atr_period

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        start = prices.index[0].strftime("%Y-%m-%d")
        end   = prices.index[-1].strftime("%Y-%m-%d")

        for ticker in prices.columns:
            ohlcv = load_ohlcv(ticker, start, end)

            if ohlcv.empty:
                c = prices[ticker].dropna()
                trend = _pp_supertrend_trend(c, c, c, self.prd, self.factor, self.atr_period)
            else:
                ohlcv = ohlcv.reindex(prices.index, method="ffill").dropna(subset=["close"])
                if ohlcv.empty:
                    continue
                trend = _pp_supertrend_trend(
                    ohlcv["high"], ohlcv["low"], ohlcv["close"],
                    self.prd, self.factor, self.atr_period,
                )

            trend = trend.reindex(prices.index).ffill().fillna(1.0)
            signals[ticker] = (trend == 1.0).astype(float)

        return signals
