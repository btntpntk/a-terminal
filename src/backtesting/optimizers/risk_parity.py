# src/backtesting/optimizers/risk_parity.py
"""
Risk Parity: each asset contributes equally to portfolio variance.
Uses scipy iterative solver.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ..interfaces import PortfolioOptimizer


class RiskParityOptimizer(PortfolioOptimizer):
    name = "Risk Parity"

    def compute_weights(self, signals: pd.Series, returns_history: pd.DataFrame, **kwargs) -> pd.Series:
        weights = pd.Series(0.0, index=signals.index)
        available = [t for t in signals.index if t in returns_history.columns]
        if not available:
            return weights

        longs  = [t for t in signals[signals > 0].index if t in available]
        shorts = [t for t in signals[signals < 0].index if t in available]

        def _risk_parity_weights(tickers) -> np.ndarray:
            n = len(tickers)
            if n == 0:
                return np.array([])
            if n == 1:
                return np.array([1.0])

            r = returns_history[tickers].tail(60).dropna(how="all").fillna(0.0)
            cov = r.cov().values + 1e-8 * np.eye(n)
            x0  = np.ones(n) / n
            target_rc = 1.0 / n  # equal risk contribution

            def _objective(w):
                w = np.abs(w)
                port_var = w @ cov @ w
                marginal = cov @ w
                rc = w * marginal / (port_var + 1e-12)
                return float(np.sum((rc - target_rc) ** 2))

            cons  = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
            bnds  = [(1e-6, 1.0)] * n
            res   = minimize(_objective, x0, method="SLSQP", bounds=bnds, constraints=cons,
                             options={"maxiter": 500, "ftol": 1e-12})
            w_opt = res.x if res.success else x0
            w_opt = np.abs(w_opt)
            total = w_opt.sum()
            return w_opt / total if total > 0 else x0

        if longs:
            w = _risk_parity_weights(longs)
            weights[longs] = w
        if shorts:
            w = _risk_parity_weights(shorts)
            weights[shorts] = -w

        return weights
