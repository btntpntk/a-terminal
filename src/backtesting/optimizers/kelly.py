# src/backtesting/optimizers/kelly.py
"""
Fractional Kelly (25%) optimizer.
Estimate μ and σ per asset from trailing 60-day returns.
Individual weight cap: 40%.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..interfaces import PortfolioOptimizer

_KELLY_FRACTION = 0.25
_MAX_WEIGHT     = 0.40
_HIST           = 60


class KellyCriterionOptimizer(PortfolioOptimizer):
    name = "Kelly Criterion (25%)"

    def compute_weights(self, signals: pd.Series, returns_history: pd.DataFrame, **kwargs) -> pd.Series:
        weights = pd.Series(0.0, index=signals.index)
        available = [t for t in signals.index if t in returns_history.columns]
        if not available:
            return weights

        hist = returns_history[available].tail(_HIST).dropna(how="all").fillna(0.0)

        mu  = hist.mean()
        var = hist.var().replace(0, float("nan"))

        # Kelly fraction per asset: f* = μ / σ²
        kelly = (mu / var).fillna(0.0) * _KELLY_FRACTION
        kelly = kelly.clip(lower=0.0)   # only positive fractions here; direction from signal

        longs  = [t for t in signals[signals > 0].index if t in available]
        shorts = [t for t in signals[signals < 0].index if t in available]

        def _apply(tickers, sign):
            if not tickers:
                return
            k = kelly[tickers].clip(upper=_MAX_WEIGHT)
            total = k.sum()
            if total > 1.0:
                k = k / total   # normalize so long book sums to ≤1
            weights[tickers] = sign * k

        _apply(longs,  1.0)
        _apply(shorts, -1.0)
        return weights
