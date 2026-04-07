# src/backtesting/optimizers/inverse_vol.py
"""Inverse-volatility weighting. Weight ∝ 1/σ_i using 20-day realized vol."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..interfaces import PortfolioOptimizer


class InverseVolatilityOptimizer(PortfolioOptimizer):
    name = "Inverse Volatility"

    def __init__(self, vol_window: int = 20):
        self.vol_window = vol_window

    def compute_weights(self, signals: pd.Series, returns_history: pd.DataFrame, **kwargs) -> pd.Series:
        weights = pd.Series(0.0, index=signals.index)

        # Compute realized vols for available tickers
        available = [t for t in signals.index if t in returns_history.columns]
        if not available:
            return weights

        vols = returns_history[available].tail(self.vol_window).std().replace(0, float("nan"))

        longs  = signals[signals > 0].index.intersection(available)
        shorts = signals[signals < 0].index.intersection(available)

        def _inv_vol_weights(tickers, sign):
            if len(tickers) == 0:
                return
            v = (1.0 / vols[tickers]).fillna(0.0)
            total = v.sum()
            if total > 0:
                weights[tickers] = sign * v / total

        _inv_vol_weights(longs,  1.0)
        _inv_vol_weights(shorts, -1.0)

        return weights
