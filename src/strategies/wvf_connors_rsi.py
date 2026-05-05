"""
Williams Vix Fix + Connors RSI-2 Strategy (Bottom Kit).

Translates the WVF + ConnorsRSI-2 indicator from PineScript.

Williams Vix Fix (synthetic VIX): spikes when fear is elevated.
Connors RSI-2: composite of RSI(2), streak RSI, and 1-day ROC percentile rank.

Dual-confirm entry:
  - WVF spike yesterday then normalised today (wvfFired)
  - ConnorsRSI < crsi_os (default 10) — extreme oversold
  - Price above MA200 — still in structural uptrend

Exit when ConnorsRSI > crsi_ob (default 90) OR close drops below MA200.

OHLCV required for proper WVF (uses actual low prices); falls back to close-only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtesting.interfaces import TradingStrategy
from ._ohlcv import load_ohlcv


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0.0)
    loss  = (-delta).clip(lower=0.0)
    avg_g = gain.ewm(alpha=1.0/period, adjust=False, min_periods=period).mean()
    avg_l = loss.ewm(alpha=1.0/period, adjust=False, min_periods=period).mean()
    rs = avg_g / avg_l.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _streak_rsi(close: pd.Series, rsi_period: int = 3) -> pd.Series:
    """RSI of up/down streak count."""
    arr = close.values.astype(float)
    n = len(arr)
    streak = np.zeros(n)
    for i in range(1, n):
        if np.isnan(arr[i]) or np.isnan(arr[i-1]):
            streak[i] = 0.0
        elif arr[i] > arr[i-1]:
            streak[i] = 1.0 if streak[i-1] <= 0 else streak[i-1] + 1.0
        elif arr[i] < arr[i-1]:
            streak[i] = -1.0 if streak[i-1] >= 0 else streak[i-1] - 1.0
        else:
            streak[i] = 0.0
    return _rsi(pd.Series(streak, index=close.index), rsi_period)


def _roc_percentile_rank(close: pd.Series, rank_len: int = 100) -> pd.Series:
    """Percentile rank of 1-day ROC among last rank_len bars."""
    roc1 = close.pct_change() * 100.0

    def pct_rank(window: np.ndarray) -> float:
        cur  = window[-1]
        past = window[:-1]
        valid = past[~np.isnan(past)]
        if len(valid) == 0:
            return 50.0
        return float((valid <= cur).sum()) / len(valid) * 100.0

    return roc1.rolling(rank_len + 1, min_periods=rank_len).apply(pct_rank, raw=True)


def _connors_rsi(close: pd.Series, rsi2_len: int = 2, str_len: int = 3, rank_len: int = 100) -> pd.Series:
    rsi2       = _rsi(close, rsi2_len)
    s_rsi      = _streak_rsi(close, str_len)
    roc_rank   = _roc_percentile_rank(close, rank_len)
    crsi = (rsi2 + s_rsi + roc_rank) / 3.0
    return crsi


def _wvf(close: pd.Series, low: pd.Series | None, period: int = 22) -> pd.Series:
    """Williams Vix Fix. Falls back to close as low proxy if low is None."""
    lo = low if low is not None else close
    highest_close = close.rolling(period).max()
    wvf = (highest_close - lo) / highest_close.replace(0.0, np.nan) * 100.0
    return wvf


class WVFConnorsRSIStrategy(TradingStrategy):
    """
    Bottom-fishing strategy: dual confirm (WVF spike cleared + ConnorsRSI extreme OS + above MA200).
    Exits when ConnorsRSI becomes overbought or price drops below MA200.
    """
    name = "WVF + Connors RSI"
    supports_short = False

    def __init__(
        self,
        wvf_period: int = 22,
        bb_period: int = 20,
        bb_mult: float = 2.0,
        pct_lookback: int = 50,
        pct_high: float = 0.85,
        crsi_os: float = 10.0,
        crsi_ob: float = 90.0,
        ma_period: int = 200,
    ):
        self.wvf_period = wvf_period
        self.bb_period = bb_period
        self.bb_mult = bb_mult
        self.pct_lookback = pct_lookback
        self.pct_high = pct_high
        self.crsi_os = crsi_os
        self.crsi_ob = crsi_ob
        self.ma_period = ma_period

    def _signals_for(
        self, close: pd.Series, low: pd.Series | None, prices_index: pd.DatetimeIndex
    ) -> pd.Series:
        wvf       = _wvf(close, low, self.wvf_period)
        mid_bb    = wvf.rolling(self.bb_period).mean()
        upper_bb  = mid_bb + self.bb_mult * wvf.rolling(self.bb_period).std(ddof=0)
        range_high = wvf.rolling(self.pct_lookback).max() * self.pct_high

        spike  = ((wvf >= upper_bb) | (wvf >= range_high)).fillna(False).astype(bool)
        spike_prev = spike.shift(1)
        spike_prev.iloc[0] = False  # first row has no yesterday
        fired  = spike_prev.astype(bool) & ~spike  # was spike yesterday, not today

        crsi   = _connors_rsi(close)
        ma200  = close.rolling(self.ma_period).mean()

        entry  = fired & (crsi < self.crsi_os) & (close > ma200)
        exit_  = (crsi > self.crsi_ob) | (close < ma200)

        raw = pd.Series(np.nan, index=close.index)
        raw[entry] = 1.0
        raw[exit_] = 0.0
        return raw.ffill().fillna(0.0).reindex(prices_index).fillna(0.0)

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        start = prices.index[0].strftime("%Y-%m-%d")
        end   = prices.index[-1].strftime("%Y-%m-%d")

        for ticker in prices.columns:
            ohlcv = load_ohlcv(ticker, start, end)

            if ohlcv.empty:
                close = prices[ticker].dropna()
                sig   = self._signals_for(close, None, prices.index)
            else:
                ohlcv = ohlcv.reindex(prices.index, method="ffill")
                close = ohlcv["close"].dropna()
                low   = ohlcv["low"].reindex(close.index)
                sig   = self._signals_for(close, low, prices.index)

            signals[ticker] = sig

        return signals
