"""
Mean Reversion Strategy.
Z-score of 20-day rolling return vs 252-day history.
Long  z < -1.5 (oversold), Short z > +1.5 (overbought).
Daily rebalance.
"""

from __future__ import annotations

import pandas as pd

from src.backtesting.interfaces import TradingStrategy


class MeanReversionStrategy(TradingStrategy):
    name = "Mean Reversion"
    supports_short = False

    def __init__(self, short_window: int = 20, long_window: int = 252, z_threshold: float = 1.5):
        self.short_window = short_window
        self.long_window  = long_window
        self.z_threshold  = z_threshold

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        ret_20    = prices.pct_change(self.short_window, fill_method=None)
        roll_mean = ret_20.rolling(self.long_window, min_periods=self.long_window // 2).mean()
        roll_std  = ret_20.rolling(self.long_window, min_periods=self.long_window // 2).std()
        z_score   = (ret_20 - roll_mean) / roll_std.replace(0, float("nan"))

        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        signals[z_score < -self.z_threshold] = 1.0

        return signals.fillna(0.0)
