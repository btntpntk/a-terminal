"""
12-1 Month Momentum Strategy.
Signal = 12-month total return minus most-recent 1-month return.
Long top quintile, short bottom quintile.
Rebalances monthly (first trading day of each month).
"""

from __future__ import annotations

import pandas as pd

from src.backtesting.interfaces import TradingStrategy


class MomentumStrategy(TradingStrategy):
    name = "Momentum (12-1)"
    supports_short = False

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        ret_12   = prices.pct_change(252, fill_method=None)
        ret_1    = prices.pct_change(21,  fill_method=None)
        momentum = ret_12 - ret_1

        monthly_dates = prices.resample("MS").first().index.intersection(prices.index)

        last_signal = pd.Series(0.0, index=prices.columns)

        for i, date in enumerate(prices.index):
            if date in monthly_dates or i == 0:
                row = momentum.loc[date].dropna()
                if len(row) < 5:
                    last_signal = pd.Series(0.0, index=prices.columns)
                else:
                    n        = len(row)
                    quintile = max(1, n // 5)
                    ranked   = row.rank(ascending=True)
                    sig      = pd.Series(0.0, index=prices.columns)
                    long_tickers = ranked[ranked >= n - quintile + 1].index
                    sig.loc[long_tickers] = 1.0
                    last_signal = sig

            signals.loc[date] = last_signal

        return signals
