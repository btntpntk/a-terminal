"""
Laguerre RSI Strategy (Ehlers DSP).

Translates John Ehlers' Laguerre RSI from PineScript.
A 4-pole Laguerre filter smooths the price before computing an RSI-like oscillator.

Entry : LaRSI crosses above oversold level (default 0.25)
Exit  : LaRSI crosses below overbought level (default 0.75)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtesting.interfaces import TradingStrategy


def _laguerre_rsi(prices: pd.DataFrame, gamma: float) -> pd.DataFrame:
    """
    Compute Laguerre RSI for all tickers.
    Returns DataFrame same shape as prices, values in [0, 1].
    """
    n, m = prices.shape
    out = np.zeros((n, m))
    arr = prices.values.astype(float)

    for col in range(m):
        src = arr[:, col]
        L0 = L1 = L2 = L3 = 0.0
        for i in range(n):
            s = src[i]
            if np.isnan(s):
                out[i, col] = np.nan
                continue
            L0_new = (1 - gamma) * s + gamma * L0
            L1_new = -gamma * L0_new + L0 + gamma * L1
            L2_new = -gamma * L1_new + L1 + gamma * L2
            L3_new = -gamma * L2_new + L2 + gamma * L3

            cu = (max(L0_new - L1_new, 0) + max(L1_new - L2_new, 0) +
                  max(L2_new - L3_new, 0))
            cd = (max(L1_new - L0_new, 0) + max(L2_new - L1_new, 0) +
                  max(L3_new - L2_new, 0))

            out[i, col] = cu / (cu + cd) if (cu + cd) != 0.0 else 0.0

            L0, L1, L2, L3 = L0_new, L1_new, L2_new, L3_new

    return pd.DataFrame(out, index=prices.index, columns=prices.columns)


class LaguerreRSIStrategy(TradingStrategy):
    """
    Long when Laguerre RSI crosses above oversold; exit when it crosses below overbought.
    Works on close prices only — no OHLCV needed.
    """
    name = "Laguerre RSI"
    supports_short = False

    def __init__(
        self,
        gamma: float = 0.6,
        oversold: float = 0.25,
        overbought: float = 0.75,
    ):
        self.gamma = gamma
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        larsi = _laguerre_rsi(prices, self.gamma)

        # Entry: crosses above oversold (today >= OS and yesterday < OS)
        entry = (larsi >= self.oversold) & (larsi.shift(1) < self.oversold)
        # Exit: crosses below overbought (today <= OB and yesterday > OB)
        exit_ = (larsi <= self.overbought) & (larsi.shift(1) > self.overbought)

        # Build stateful signals via forward-fill
        raw = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
        raw[entry] = 1.0
        raw[exit_] = 0.0

        return raw.ffill().fillna(0.0)
