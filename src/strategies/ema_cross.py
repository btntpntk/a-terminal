"""
EMA Cross Strategy.
Long when EMA(12) crosses above EMA(26), flat when it crosses below.
"""

from __future__ import annotations

import pandas as pd

from src.backtesting.interfaces import TradingStrategy


class EMACrossStrategy(TradingStrategy):
    name = "EMA Cross (12/26)"
    supports_short = False

    def __init__(self, fast: int = 12, slow: int = 26):
        self.fast = fast
        self.slow = slow

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        ema_fast = prices.ewm(span=self.fast, adjust=False).mean()
        ema_slow = prices.ewm(span=self.slow, adjust=False).mean()

        above = ema_fast > ema_slow
        # Hold long while fast stays above slow (not just on cross day)
        signals = above.astype(float)

        return signals.fillna(0.0)
