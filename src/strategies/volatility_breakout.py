"""
Volatility Breakout Strategy.
Long  if price > 20-day high + 0.5 × ATR(20).
Short if price < 20-day low  - 0.5 × ATR(20).
"""

from __future__ import annotations

import pandas as pd

from src.backtesting.interfaces import TradingStrategy


def _atr(prices: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Approximate ATR from close-to-close differences (no OHLC)."""
    return prices.diff().abs().rolling(period, min_periods=period).mean()


class VolatilityBreakoutStrategy(TradingStrategy):
    name = "Volatility Breakout"
    supports_short = True

    def __init__(self, window: int = 20, atr_multiplier: float = 0.5):
        self.window         = window
        self.atr_multiplier = atr_multiplier

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        high_20 = prices.rolling(self.window, min_periods=self.window).max()
        low_20  = prices.rolling(self.window, min_periods=self.window).min()
        atr     = _atr(prices, self.window)

        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        signals[prices > high_20 + self.atr_multiplier * atr] =  1.0
        signals[prices < low_20  - self.atr_multiplier * atr] = -1.0

        return signals.fillna(0.0)
