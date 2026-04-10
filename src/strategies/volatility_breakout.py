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
    supports_short = False

    def __init__(self, window: int = 20, atr_multiplier: float = 0.5):
        self.window         = window
        self.atr_multiplier = atr_multiplier

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        # Shift by 1 so bar T signal uses the highest close of the previous 20 bars,
        # not the current bar's close (which would always be ≤ its own rolling max).
        high_20 = prices.rolling(self.window, min_periods=self.window).max().shift(1)
        atr     = _atr(prices, self.window).shift(1)

        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        signals[prices > high_20 + self.atr_multiplier * atr] = 1.0

        return signals.fillna(0.0)
