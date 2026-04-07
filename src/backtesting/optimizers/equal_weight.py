# src/backtesting/optimizers/equal_weight.py
"""Equal weight across signaled assets. Long book = 1/N_long, short book = -1/N_short."""

from __future__ import annotations

import pandas as pd

from ..interfaces import PortfolioOptimizer


class EqualWeightOptimizer(PortfolioOptimizer):
    name = "Equal Weight"

    def compute_weights(self, signals: pd.Series, returns_history: pd.DataFrame, **kwargs) -> pd.Series:
        weights = pd.Series(0.0, index=signals.index)

        longs  = signals[signals > 0]
        shorts = signals[signals < 0]

        if len(longs) > 0:
            weights[longs.index] = 1.0 / len(longs)
        if len(shorts) > 0:
            weights[shorts.index] = -1.0 / len(shorts)

        return weights
