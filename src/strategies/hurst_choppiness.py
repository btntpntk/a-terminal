"""
Hurst Exponent + Choppiness Index Regime Strategy.

Translates the SET Regime Detector from PineScript.
Hurst Exponent (R/S analysis) classifies the market as trending vs mean-reverting.
Choppiness Index confirms whether price moves directionally.

Long : Trending regime (Hurst > 0.55 AND Chop < chop_high) AND price > MA50
Flat : Mean-reverting, unclear regime, or below MA50
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtesting.interfaces import TradingStrategy


def _hurst_rs(prices: pd.Series, period: int) -> pd.Series:
    """Rolling Hurst exponent via R/S (rescaled range) analysis."""
    arr = prices.values.astype(float)
    n = len(arr)
    result = np.full(n, np.nan)

    for t in range(period, n):
        window = arr[t - period:t]
        mean_w = np.mean(window)
        deviations = window - mean_w
        cum_dev = np.cumsum(deviations)
        R = cum_dev.max() - cum_dev.min()
        S = np.std(window, ddof=0)
        if R > 0.0 and S > 0.0:
            result[t] = np.log(R / S) / np.log(period)

    return pd.Series(result, index=prices.index)


def _choppiness(prices: pd.Series, period: int) -> pd.Series:
    """
    Choppiness Index (close-only approximation).
    Uses |daily change| as ATR proxy and close rolling range as HL range proxy.
    Range: 0-100. High (>61.8) = choppy; Low (<38.2) = trending.
    """
    abs_diff = prices.diff().abs()
    atr_sum = abs_diff.rolling(period).sum()
    hl_range = prices.rolling(period).max() - prices.rolling(period).min()

    chop = np.where(
        hl_range > 0,
        100.0 * np.log10((atr_sum / hl_range).clip(lower=1e-10)) / np.log10(period),
        50.0,
    )
    return pd.Series(chop, index=prices.index).clip(0, 100)


class HurstChoppinessStrategy(TradingStrategy):
    """
    Long in trending regime (Hurst > trend_thresh AND Chop < chop_high AND above MA50).
    Uses close-only approximation for choppiness index.
    """
    name = "Hurst Choppiness Regime"
    supports_short = False

    def __init__(
        self,
        hurst_period: int = 100,
        hurst_smooth: int = 5,
        hurst_trend_thresh: float = 0.55,
        chop_period: int = 14,
        chop_high: float = 61.8,
        ma_period: int = 50,
    ):
        self.hurst_period = hurst_period
        self.hurst_smooth = hurst_smooth
        self.hurst_trend_thresh = hurst_trend_thresh
        self.chop_period = chop_period
        self.chop_high = chop_high
        self.ma_period = ma_period

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        for ticker in prices.columns:
            col = prices[ticker].dropna()
            if len(col) < self.hurst_period + self.ma_period:
                continue

            hurst_raw = _hurst_rs(col, self.hurst_period)
            # Fill NaN with 0.5 (random walk) before smoothing
            hurst_s = hurst_raw.fillna(0.5).ewm(span=self.hurst_smooth, adjust=False).mean()

            chop = _choppiness(col, self.chop_period)
            ma = col.rolling(self.ma_period).mean()

            trending = (hurst_s > self.hurst_trend_thresh) & (chop < self.chop_high)
            above_ma = col > ma

            sig = (trending & above_ma).reindex(prices.index).fillna(False).astype(float)
            signals[ticker] = sig

        return signals
