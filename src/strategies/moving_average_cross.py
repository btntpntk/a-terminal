"""
Moving Average Cross Strategy.
+1 if 20-day SMA > 50-day SMA, -1 if below.
Per-asset signal — no cross-sectional ranking.
"""

from __future__ import annotations

import pandas as pd

from src.backtesting.interfaces import TradingStrategy


class MovingAverageCrossStrategy(TradingStrategy):
    name = "MA Cross (20/50)"
    supports_short = True

    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        sma_fast = prices.rolling(self.fast, min_periods=self.fast).mean()
        sma_slow = prices.rolling(self.slow, min_periods=self.slow).mean()

        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        signals[sma_fast > sma_slow] =  1.0
        signals[sma_fast < sma_slow] = -1.0

        return signals.fillna(0.0)
