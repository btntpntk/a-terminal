# src/backtesting/optimizers/mean_variance.py
"""
Mean-Variance (max Sharpe) optimizer using scipy.
60-day return history, L2 regularization λ=0.1.
Separate optimization for long and short books.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ..interfaces import PortfolioOptimizer

_LAMBDA = 0.1   # L2 regularization
_HIST   = 60    # days of return history


class MeanVarianceOptimizer(PortfolioOptimizer):
    name = "Mean-Variance"

    def compute_weights(self, signals: pd.Series, returns_history: pd.DataFrame, **kwargs) -> pd.Series:
        weights = pd.Series(0.0, index=signals.index)
        available = [t for t in signals.index if t in returns_history.columns]
        if not available:
            return weights

        hist = returns_history[available].tail(_HIST).dropna(how="all")
        if len(hist) < 10:
            # Fallback to equal weight
            longs  = signals[signals > 0].index.intersection(available)
            shorts = signals[signals < 0].index.intersection(available)
            if len(longs)  > 0: weights[longs]  =  1.0 / len(longs)
            if len(shorts) > 0: weights[shorts]  = -1.0 / len(shorts)
            return weights

        longs  = [t for t in signals[signals > 0].index if t in available]
        shorts = [t for t in signals[signals < 0].index if t in available]

        def _opt_book(tickers, sign):
            if not tickers:
                return
            r = hist[tickers].dropna(how="all").fillna(0.0)
            mu  = r.mean().values
            cov = r.cov().values + _LAMBDA * np.eye(len(tickers))
            n   = len(tickers)
            x0  = np.ones(n) / n

            def neg_sharpe(w):
                port_ret = mu @ w
                port_var = w @ cov @ w
                return -(port_ret / (np.sqrt(port_var) + 1e-10))

            cons  = {"type": "eq", "fun": lambda w: w.sum() - 1.0}
            bnds  = [(0, 1)] * n
            res   = minimize(neg_sharpe, x0, method="SLSQP", bounds=bnds, constraints=cons,
                             options={"maxiter": 200, "ftol": 1e-9})
            w_opt = res.x if res.success else x0
            w_opt = np.clip(w_opt, 0, 1)
            total = w_opt.sum()
            if total > 0:
                w_opt /= total
            weights[tickers] = sign * w_opt

        _opt_book(longs,  1.0)
        _opt_book(shorts, -1.0)
        return weights
