# src/backtesting/engine.py
"""
Walk-forward backtesting engine.

Fold structure (non-overlapping out-of-sample windows):
  Fold 1: train [0 : IS], test [IS : IS+OOS]
  Fold 2: train [OOS : IS+OOS], test [IS+OOS : IS+2*OOS]
  ...
Requires at least MIN_FOLDS=3 complete folds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .interfaces import PortfolioOptimizer, TradingStrategy
from .metrics import compute_metrics

MIN_FOLDS = 3


@dataclass
class BacktestResult:
    equity_curve:    pd.Series
    benchmark_curve: pd.Series
    trade_log:       pd.DataFrame
    fold_returns:    list[pd.Series]
    metrics:         dict
    weights_history: pd.DataFrame  # DatetimeIndex × ticker, end-of-day target weights


def run_backtest(
    prices: pd.DataFrame,
    benchmark_prices: pd.Series,
    strategy: TradingStrategy,
    optimizer: PortfolioOptimizer,
    initial_capital: float = 1_000_000.0,
    in_sample_window: int = 252,
    out_of_sample_window: int = 63,
    step_size: int | None = None,
    max_stop_loss_pct: float = 0.05,
    transaction_cost_pct: float = 0.001,
) -> BacktestResult:
    """Execute a walk-forward backtest and return a BacktestResult."""

    if step_size is None:
        step_size = out_of_sample_window

    n = len(prices)
    # Validate minimum folds
    required = in_sample_window + MIN_FOLDS * out_of_sample_window
    if n < required:
        raise ValueError(
            f"Price history too short: {n} days. Need at least {required} days "
            f"for {MIN_FOLDS} complete folds (IS={in_sample_window}, OOS={out_of_sample_window})."
        )

    # Build fold boundaries
    folds: list[tuple[int, int, int, int]] = []  # (train_start, train_end, test_start, test_end)
    train_start = 0
    while True:
        train_end = train_start + in_sample_window
        test_start = train_end
        test_end = test_start + out_of_sample_window
        if test_end > n:
            break
        folds.append((train_start, train_end, test_start, test_end))
        train_start += step_size

    if len(folds) < MIN_FOLDS:
        raise ValueError(f"Only {len(folds)} folds available; need at least {MIN_FOLDS}.")

    tickers = list(prices.columns)

    # Generate ALL signals up-front (strategies are rule-based / reactive, not fitted)
    # Pass benchmark_prices so strategies like DRSI can access it via **kwargs
    all_signals = strategy.generate_signals(prices, benchmark_prices=benchmark_prices)
    # Ensure same shape and fill NaN with 0
    all_signals = all_signals.reindex_like(prices).fillna(0)

    # ── Portfolio simulation state ───────────────────────────────────────
    portfolio_values: list[tuple[pd.Timestamp, float]] = []
    trade_records: list[dict] = []
    fold_equity_list: list[pd.Series] = []

    # Current weights and position tracking
    current_weights = pd.Series(0.0, index=tickers)
    equity = initial_capital

    # Stop-loss tracking: {ticker: {"entry_price": float, "direction": int}}
    open_positions: dict[str, dict] = {}

    # Track last day's prices across folds so fold boundaries don't drop a day's P&L
    prev_prices_global: pd.Series | None = None

    all_test_dates = set()
    weights_rows: list[tuple[pd.Timestamp, dict]] = []

    for fold_idx, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
        test_prices  = prices.iloc[te_s:te_e]
        test_signals = all_signals.iloc[te_s:te_e]
        returns_hist = prices.iloc[tr_s:tr_e].pct_change(fill_method=None).dropna()

        fold_equity_vals: list[tuple[pd.Timestamp, float]] = []

        for i, date in enumerate(test_prices.index):
            today_prices  = test_prices.iloc[i]
            today_signals = test_signals.iloc[i]

            # ── Apply stop-loss before computing new weights ─────────
            # Long  stop: price fell  >= max_stop_loss_pct  from entry  → close
            # Short stop: price rose  >= max_stop_loss_pct  from entry  → close
            # pnl_pct = (cur/entry - 1) * direction
            #   Long  +direction=+1: pnl_pct negative when price falls
            #   Short +direction=-1: pnl_pct negative when price rises
            stopped_tickers: set[str] = set()
            for ticker, pos in list(open_positions.items()):
                if ticker not in today_prices.index:
                    continue
                cur_price = today_prices.loc[ticker]
                try:
                    cur_price = float(cur_price)
                except (TypeError, ValueError):
                    continue
                if math.isnan(cur_price):
                    continue
                entry_price = pos["entry_price"]
                direction   = pos["direction"]
                pnl_pct = (cur_price / entry_price - 1) * direction
                if pnl_pct <= -max_stop_loss_pct:
                    if today_signals is test_signals.iloc[i]:
                        today_signals = today_signals.copy()
                    today_signals[ticker] = 0
                    stopped_tickers.add(ticker)

            # ── Compute target weights ────────────────────────────────
            active_signals = today_signals[today_signals != 0].dropna()
            if active_signals.empty:
                target_weights = pd.Series(0.0, index=tickers)
            else:
                try:
                    # Only pass return history for active tickers that exist
                    available = [t for t in active_signals.index if t in returns_hist.columns]
                    active_signals_clean = active_signals.loc[available]
                    rh = returns_hist[available].tail(60) if available else returns_hist.tail(60)
                    raw_w = optimizer.compute_weights(active_signals_clean, rh)
                    target_weights = raw_w.reindex(tickers).fillna(0.0)
                except Exception:
                    target_weights = pd.Series(0.0, index=tickers)

            # ── Transaction costs ─────────────────────────────────────
            turnover = (target_weights - current_weights).abs().sum()
            cost = turnover * transaction_cost_pct

            # ── Daily P&L ─────────────────────────────────────────────
            if prev_prices_global is None:
                # Absolute first day of the entire backtest — no prior prices
                daily_return = 0.0
            else:
                ref_prices = test_prices.iloc[i - 1] if i > 0 else prev_prices_global
                asset_returns = (today_prices / ref_prices - 1).fillna(0.0)
                daily_return = float((current_weights * asset_returns).sum())

            prev_prices_global = today_prices

            portfolio_return = daily_return - cost
            equity = equity * (1 + portfolio_return)

            # ── Update open positions ─────────────────────────────────
            for ticker in tickers:
                new_w = float(target_weights.get(ticker, 0.0))
                old_w = float(current_weights.get(ticker, 0.0))
                cur_price = float(today_prices.get(ticker, float("nan")))

                if math.isnan(cur_price):
                    continue

                if old_w == 0 and new_w != 0:
                    # Opening position — snapshot equity and weight at entry
                    open_positions[ticker] = {
                        "entry_price":  cur_price,
                        "entry_date":   date,
                        "entry_equity": equity,
                        "entry_weight": abs(new_w),
                        "direction":    1 if new_w > 0 else -1,
                    }
                elif old_w != 0 and new_w == 0:
                    # Closing position — record trade
                    pos = open_positions.pop(ticker, None)
                    if pos is not None:
                        ret_pct = (cur_price / pos["entry_price"] - 1) * pos["direction"]
                        # Capital committed at entry × price return = correct dollar PnL
                        capital_at_entry = pos["entry_weight"] * pos["entry_equity"]
                        pnl = capital_at_entry * ret_pct
                        trade_records.append({
                            "asset":          ticker,
                            "entry_date":     pos["entry_date"],
                            "exit_date":      date,
                            "entry_price":    pos["entry_price"],
                            "exit_price":     cur_price,
                            "direction":      "long" if pos["direction"] == 1 else "short",
                            "return_pct":     ret_pct,
                            "pnl":            pnl,
                            "equity_at_exit": equity,
                            "stop_triggered": ticker in stopped_tickers,
                        })
                elif old_w != 0 and new_w != 0 and (old_w * new_w < 0):
                    # Direction flip — close old, open new
                    pos = open_positions.pop(ticker, None)
                    if pos is not None:
                        ret_pct = (cur_price / pos["entry_price"] - 1) * pos["direction"]
                        capital_at_entry = pos["entry_weight"] * pos["entry_equity"]
                        pnl = capital_at_entry * ret_pct
                        trade_records.append({
                            "asset":          ticker,
                            "entry_date":     pos["entry_date"],
                            "exit_date":      date,
                            "entry_price":    pos["entry_price"],
                            "exit_price":     cur_price,
                            "direction":      "long" if pos["direction"] == 1 else "short",
                            "return_pct":     ret_pct,
                            "pnl":            pnl,
                            "equity_at_exit": equity,
                            "stop_triggered": False,
                        })
                    open_positions[ticker] = {
                        "entry_price":  cur_price,
                        "entry_date":   date,
                        "entry_equity": equity,
                        "entry_weight": abs(new_w),
                        "direction":    1 if new_w > 0 else -1,
                    }

            current_weights = target_weights.copy()

            # Record end-of-day weights (only non-zero positions to keep it sparse)
            weights_rows.append((date, {t: float(v) for t, v in target_weights.items() if abs(v) > 1e-6}))

            portfolio_values.append((date, equity))
            fold_equity_vals.append((date, equity))
            all_test_dates.add(date)

        fold_equity_list.append(
            pd.Series(
                {d: v for d, v in fold_equity_vals},
                name=f"fold_{fold_idx + 1}",
            )
        )

    # ── Build equity curve ───────────────────────────────────────────────
    equity_curve = pd.Series(
        {d: v for d, v in portfolio_values},
        dtype=float,
        name="portfolio",
    ).sort_index()

    # ── Build benchmark curve (rebased to initial_capital) ───────────────
    bm_dates = benchmark_prices.index[benchmark_prices.index.isin(equity_curve.index)]
    if len(bm_dates) == 0:
        bm_dates = benchmark_prices.index
    bm_slice = benchmark_prices.loc[bm_dates].sort_index().dropna()
    if len(bm_slice) == 0:
        benchmark_curve = pd.Series(dtype=float)
    else:
        benchmark_curve = (bm_slice / bm_slice.iloc[0]) * initial_capital
        benchmark_curve.name = "benchmark"

    # ── Trade log ────────────────────────────────────────────────────────
    trade_log = pd.DataFrame(trade_records) if trade_records else pd.DataFrame(
        columns=["asset", "entry_date", "exit_date", "direction", "return_pct", "pnl", "stop_triggered"]
    )

    metrics = compute_metrics(equity_curve, trade_log)

    # Build weights_history DataFrame (dates × tickers, NaN → 0)
    if weights_rows:
        weights_history = pd.DataFrame(
            [v for _, v in weights_rows],
            index=[d for d, _ in weights_rows],
        ).fillna(0.0)
        weights_history.index = pd.to_datetime(weights_history.index)
    else:
        weights_history = pd.DataFrame(index=equity_curve.index, columns=tickers, dtype=float).fillna(0.0)

    return BacktestResult(
        equity_curve=equity_curve,
        benchmark_curve=benchmark_curve,
        trade_log=trade_log,
        fold_returns=fold_equity_list,
        metrics=metrics,
        weights_history=weights_history,
    )
