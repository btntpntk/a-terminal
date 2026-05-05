"""
CPR + Camarilla Weekly Pivot Strategy.

Translates the CPR Weekly + Camarilla Pivots indicator from PineScript.
Previous-week H/L/C are used to compute Central Pivot Range and Camarilla levels
at the start of each new week (no look-ahead: only the closed week is used).

Trend-following signal (Camarilla H4 breakout):
  Entry : daily close crosses above H4 (weekly Camarilla resistance break)
  Exit  : daily close drops below H3 (lost key level)

OHLCV fetched per ticker and resampled to weekly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtesting.interfaces import TradingStrategy
from ._ohlcv import load_ohlcv


def _weekly_camarilla(ohlcv: pd.DataFrame, daily_index: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Compute weekly CPR + Camarilla levels for every daily bar.
    Levels are fixed for the entire current week, based on the previous completed week.
    Returns DataFrame with columns: pivot, TC, BC, H4, H3, L3, L4.
    """
    weekly = ohlcv[["high", "low", "close"]].resample("W-FRI").agg(
        {"high": "max", "low": "min", "close": "last"}
    )
    # Shift by 1 week to use the *previous* completed week
    prev = weekly.shift(1)

    prevH = prev["high"]
    prevL = prev["low"]
    prevC = prev["close"]
    hl    = prevH - prevL

    pivot = (prevH + prevL + prevC) / 3.0
    BC    = (prevH + prevL) / 2.0
    TC    = (pivot - BC) + pivot
    H4    = prevC + hl * 1.1 / 2.0
    H3    = prevC + hl * 1.1 / 4.0
    L3    = prevC - hl * 1.1 / 4.0
    L4    = prevC - hl * 1.1 / 2.0

    lvls = pd.DataFrame(
        {"pivot": pivot, "TC": TC, "BC": BC, "H4": H4, "H3": H3, "L3": L3, "L4": L4}
    )
    # Forward-fill weekly levels onto daily index
    return lvls.reindex(daily_index, method="ffill")


class CPRCamarillaStrategy(TradingStrategy):
    """
    Trend-following Camarilla H4 breakout strategy.
    Long when daily close crosses above H4 (weekly Camarilla resistance).
    Exits when close drops below H3.
    """
    name = "CPR Camarilla Weekly"
    supports_short = False

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        start = prices.index[0].strftime("%Y-%m-%d")
        end   = prices.index[-1].strftime("%Y-%m-%d")

        for ticker in prices.columns:
            ohlcv = load_ohlcv(ticker, start, end)

            if ohlcv.empty:
                continue  # strategy cannot operate without H/L/C for weekly levels

            ohlcv = ohlcv.reindex(prices.index, method="ffill").dropna(subset=["close"])
            if len(ohlcv) < 10:
                continue

            lvls  = _weekly_camarilla(ohlcv, prices.index)
            close = ohlcv["close"].reindex(prices.index)

            H4 = lvls["H4"]
            H3 = lvls["H3"]

            # H4 crossover: today above H4, yesterday at or below H4
            entry = (close > H4) & (close.shift(1) <= H4)
            # Drop below H3 → exit
            exit_ = close < H3

            raw = pd.Series(np.nan, index=prices.index)
            raw[entry.fillna(False)] = 1.0
            raw[exit_.fillna(False)] = 0.0
            signals[ticker] = raw.ffill().fillna(0.0)

        return signals
