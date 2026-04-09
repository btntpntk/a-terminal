"""
RSI Strategy.
Long if RSI(14) < 30 (oversold), Short if RSI(14) > 70 (overbought), else flat.
"""

from __future__ import annotations

import pandas as pd

from src.backtesting.interfaces import TradingStrategy


def _rsi(prices: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    delta    = prices.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


class RSIStrategy(TradingStrategy):
    name = "RSI (14)"
    supports_short = False

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period     = period
        self.oversold   = oversold
        self.overbought = overbought

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        rsi = _rsi(prices, self.period)

        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        signals[rsi < self.oversold] = 1.0
        # Exit (go flat) when overbought — signal drops to 0, no short
        signals[rsi > self.overbought] = 0.0

        return signals.fillna(0.0)
