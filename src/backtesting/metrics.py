# src/backtesting/metrics.py
"""
Portfolio performance metrics computed from an equity curve and trade log.
"""

from __future__ import annotations

import math

import pandas as pd


def compute_metrics(
    equity: pd.Series,
    trade_log: pd.DataFrame,
    risk_free_rate: float = 0.02,
) -> dict:
    """
    Compute the full set of KPI metrics from an equity curve and trade log.

    Parameters
    ----------
    equity : pd.Series  — DatetimeIndex, portfolio value starting at initial_capital
    trade_log : pd.DataFrame  — columns: asset, entry_date, exit_date, direction, return_pct, pnl
    risk_free_rate : float  — annual risk-free rate (default 2%)
    """
    metrics: dict = {}

    # ── Equity-curve metrics ─────────────────────────────────────────────
    equity = equity.dropna()
    if len(equity) < 2:
        return _empty_metrics()

    total_return = float((equity.iloc[-1] / equity.iloc[0]) - 1)
    n_days = (equity.index[-1] - equity.index[0]).days
    n_years = max(n_days / 365.25, 1 / 365.25)

    cagr = float((1 + total_return) ** (1 / n_years) - 1)

    daily_returns = equity.pct_change(fill_method=None).dropna()
    mean_daily = float(daily_returns.mean())
    std_daily = float(daily_returns.std())

    rf_daily = risk_free_rate / 252
    sharpe_ratio = float((mean_daily - rf_daily) / std_daily * math.sqrt(252)) if std_daily > 0 else 0.0

    # Max drawdown
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max
    max_drawdown = float(drawdown.min())  # negative value

    calmar_ratio = float(cagr / abs(max_drawdown)) if max_drawdown != 0 else 0.0
    volatility_ann = float(std_daily * math.sqrt(252))

    metrics.update({
        "total_return":   total_return,
        "cagr":           cagr,
        "sharpe_ratio":   sharpe_ratio,
        "max_drawdown":   max_drawdown,
        "calmar_ratio":   calmar_ratio,
        "volatility_ann": volatility_ann,
    })

    # ── Trade log metrics ────────────────────────────────────────────────
    if trade_log is None or trade_log.empty:
        metrics.update({
            "avg_trade_return": None,
            "win_rate":         None,
            "avg_win":          None,
            "avg_loss":         None,
            "reward_to_risk":   None,
            "total_trades":     0,
            "long_trades":      0,
            "short_trades":     0,
        })
        return _clean(metrics)

    rets = trade_log["return_pct"].dropna()
    total_trades = int(len(rets))
    wins  = rets[rets > 0]
    losses = rets[rets < 0]

    avg_trade_return = float(rets.mean()) if total_trades > 0 else None
    win_rate  = float((rets > 0).mean()) if total_trades > 0 else None
    avg_win   = float(wins.mean())   if len(wins)   > 0 else None
    avg_loss  = float(losses.mean()) if len(losses) > 0 else None

    if avg_win is not None and avg_loss is not None and avg_loss != 0:
        reward_to_risk = float(abs(avg_win / avg_loss))
    else:
        reward_to_risk = None

    long_trades  = int((trade_log["direction"] == "long").sum())
    short_trades = int((trade_log["direction"] == "short").sum())

    metrics.update({
        "avg_trade_return": avg_trade_return,
        "win_rate":         win_rate,
        "avg_win":          avg_win,
        "avg_loss":         avg_loss,
        "reward_to_risk":   reward_to_risk,
        "total_trades":     total_trades,
        "long_trades":      long_trades,
        "short_trades":     short_trades,
    })

    return _clean(metrics)


def _empty_metrics() -> dict:
    return {
        "total_return": None, "cagr": None, "sharpe_ratio": None,
        "max_drawdown": None, "calmar_ratio": None, "volatility_ann": None,
        "avg_trade_return": None, "win_rate": None, "avg_win": None,
        "avg_loss": None, "reward_to_risk": None,
        "total_trades": 0, "long_trades": 0, "short_trades": 0,
    }


def _clean(d: dict) -> dict:
    """Replace NaN/Inf with None."""
    out = {}
    for k, v in d.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            out[k] = None
        else:
            out[k] = v
    return out
