"""
Position Cost Distribution (筹码分布) Strategy.

Translates the CYQ / chip-distribution indicator from PineScript.
Computes a rolling volume-weighted price distribution with time-decay.
The "peak cost zone" is the price bucket with the highest chip concentration
(i.e., where most recently traded shares are sitting).

Signal logic:
  Long : close > peak_cost_zone  (price has broken above the main supply overhang)
  Flat : close <= peak_cost_zone (price still below where most holders bought in)

OHLCV + volume data required. Falls back to uniform volume if unavailable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtesting.interfaces import TradingStrategy
from ._ohlcv import load_ohlcv


def _peak_cost_rolling(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray,
    lookback: int,
    buckets: int,
    decay: float,
) -> np.ndarray:
    """
    Rolling peak cost zone via volume-weighted chip distribution.
    Returns array of peak cost prices (NaN for first lookback-1 bars).
    """
    n = len(close)
    peak_costs = np.full(n, np.nan)

    # Decay weights: index 0 = oldest bar, index lookback-1 = newest
    decay_arr = decay ** np.arange(lookback - 1, -1, -1)

    for t in range(lookback - 1, n):
        wc = close[t - lookback + 1:t + 1]
        wh = high[t  - lookback + 1:t + 1]
        wl = low[t   - lookback + 1:t + 1]
        wv = volume[t - lookback + 1:t + 1]

        hi_r = np.nanmax(wh)
        lo_r = np.nanmin(wl)
        rng  = hi_r - lo_r

        if rng <= 0.0:
            peak_costs[t] = np.nanmean(wc)
            continue

        b_lo = lo_r + rng * np.arange(buckets) / buckets          # (B,)
        b_hi = lo_r + rng * np.arange(1, buckets + 1) / buckets   # (B,)

        # Overlap between bar H/L and each bucket — shape (lookback, buckets)
        overlap = np.maximum(
            np.minimum(wh[:, None], b_hi[None, :]) -
            np.maximum(wl[:, None], b_lo[None, :]),
            0.0,
        )
        bar_rng = np.where((wh - wl) > 0, wh - wl, 1.0)[:, None]
        fraction = overlap / bar_rng

        mid_b = (b_lo + b_hi) / 2.0                                  # (B,)
        tp    = (wh + wl + wc) / 3.0                                  # (lookback,)
        vwap_w = 1.0 / (1.0 + np.abs(mid_b[None, :] - tp[:, None]) / rng)

        vol_clean = np.where(np.isnan(wv), 0.0, wv)

        chip_dist = (vol_clean[:, None] * fraction * vwap_w * decay_arr[:, None]).sum(axis=0)

        peak_bucket = int(np.argmax(chip_dist))
        peak_costs[t] = lo_r + rng * (peak_bucket + 0.5) / buckets

    return peak_costs


class PositionCostDistributionStrategy(TradingStrategy):
    """
    Long when close is above the rolling peak chip-concentration zone.
    Requires OHLCV + volume data; skips ticker if unavailable.
    """
    name = "Position Cost Distribution"
    supports_short = False

    def __init__(
        self,
        lookback: int = 120,
        buckets: int = 30,
        decay: float = 0.9,
    ):
        self.lookback = lookback
        self.buckets = buckets
        self.decay = decay

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        start = prices.index[0].strftime("%Y-%m-%d")
        end   = prices.index[-1].strftime("%Y-%m-%d")

        for ticker in prices.columns:
            ohlcv = load_ohlcv(ticker, start, end)

            if ohlcv.empty:
                close_arr = prices[ticker].ffill().values.astype(float)
                peak = _peak_cost_rolling(
                    close_arr, close_arr, close_arr,
                    np.ones(len(close_arr)),
                    self.lookback, self.buckets, self.decay,
                )
                close_s = prices[ticker]
            else:
                ohlcv = ohlcv.reindex(prices.index, method="ffill")
                close_s  = ohlcv["close"].ffill()
                high_arr = ohlcv["high"].ffill().values.astype(float)
                low_arr  = ohlcv["low"].ffill().values.astype(float)
                vol_arr  = ohlcv["volume"].fillna(0.0).values.astype(float)
                close_arr = close_s.values.astype(float)

                peak = _peak_cost_rolling(
                    close_arr, high_arr, low_arr, vol_arr,
                    self.lookback, self.buckets, self.decay,
                )

            peak_s = pd.Series(peak, index=prices.index)
            signals[ticker] = (close_s > peak_s).astype(float).fillna(0.0)

        return signals
