# src/backtesting/mc_engine.py
"""
Monte Carlo Integrated Walk-Forward Backtesting Engine.

Combines MC-derived TP/SL levels with walk-forward backtesting.  Signals from
existing strategies trigger entries; TP/SL levels and position sizes come from
GBM / Student-t path simulation.

Key constraints (non-negotiable):
  - Vol/drift estimated only from data up to and including the signal bar (no lookahead).
  - SL is checked before TP before strategy signal (priority order in check_exits_priority).
  - RNG: np.random.default_rng(seed=seed_base + bar_index) — reproducible per bar.
  - purge_days >= holding_days, enforced by assertion before the fold loop.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .metrics import compute_metrics


# ─────────────────────────────────────────────────────────────────────────────
# Parameter dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MCParams:
    """All configuration for a Monte Carlo integrated walk-forward backtest."""
    # Strategies
    buy_strategy: str = "MomentumStrategy"
    sell_strategy: str = "TP_SL"   # strategy name | "TP_SL" | "BOTH"

    # Universe
    tickers: List[str] = field(default_factory=list)
    benchmark_ticker: str = "SPY"

    # Backtest period
    backtest_start: Optional[pd.Timestamp] = None
    backtest_end: Optional[pd.Timestamp] = None

    # Capital & risk
    initial_capital: float = 1_000_000.0
    max_stop_loss_pct: float = 0.08
    acceptable_risk_pct: float = 0.01

    # MC simulation
    n_simulations: int = 1000
    holding_days: int = 10
    tp_quantile: float = 0.80
    sl_quantile: float = 0.10
    shock_distribution: str = "student_t"   # "student_t" | "normal"
    student_t_df: int = 6

    # Volatility estimation
    vol_lookback_days: int = 20
    vol_method: str = "ewma"               # "ewma" | "rolling_std"
    ewma_halflife_days: int = 10
    vol_floor: float = 0.10
    vol_cap: float = 1.50
    drift_method: str = "zero"             # "zero" | "historical_mean"

    # Position & portfolio controls
    max_open_positions: int = 10
    max_position_pct: float = 0.15
    cash_reserve_pct: float = 0.10
    max_signals_per_bar: int = 5
    signal_confirmation_bars: int = 1
    cooloff_days: int = 5

    # Exit behaviour
    breakeven_trail_enabled: bool = True
    max_holding_days: int = 20             # default = holding_days * 2
    partial_tp_pct: float = 1.0

    # EV filter
    min_ev_dollars: float = 0.0
    min_rr_ratio: float = 1.5
    min_p_tp: float = 0.50

    # Position sizing
    sizing_method: str = "risk_parity_sl"  # "risk_parity_sl" | "kelly_mc"
    kelly_fraction: float = 0.25

    # Correlation controls
    correlation_penalty_enabled: bool = True
    correlation_threshold: float = 0.70
    correlation_penalty_factor: float = 0.50

    # Walk-forward
    n_folds: int = 4
    test_window_days: int = 63
    purge_days: int = 10
    optimise_mc_params_on_train: bool = False
    sl_quantile_grid: List[float] = field(default_factory=lambda: [0.05, 0.10, 0.15])
    tp_quantile_grid: List[float] = field(default_factory=lambda: [0.75, 0.80, 0.85, 0.90])
    wf_metric: str = "sharpe_ratio"

    # Fill price
    fill_price: str = "open_next_day"   # "open_next_day" | "close"

    # Misc
    seed_base: int = 42
    commission_bps: float = 10.0
    sl_commission_bps: float = 5.0


# ─────────────────────────────────────────────────────────────────────────────
# Supporting dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MCSimResult:
    """Output of one Monte Carlo simulation run."""
    ticker: str
    entry_price: float
    tp_price: float
    sl_price: float
    sl_raw: float
    tp_raw: float
    rr: float
    p_tp: float
    p_sl: float
    ev: float          # expected value per share (price units)
    mfe: float         # mean max favourable excursion (pct)
    mae: float         # mean max adverse excursion (pct)
    sigma_annual: float


@dataclass
class OpenPosition:
    """State of a currently open position."""
    ticker: str
    entry_bar: pd.Timestamp
    entry_bar_loc: int          # integer index in prices.index for time-exit counting
    entry_price: float
    shares: int
    dollars_allocated: float
    sl_price: float
    initial_sl_price: float
    tp_price: float
    fold_id: int
    mc_sl_raw: float
    mc_tp: float
    rr: float
    p_tp: float
    p_sl: float
    ev: float
    sigma_annual: float
    signal_confirmation_count: int
    breakeven_trail_active: bool = False


@dataclass
class TradeRecord:
    """A completed trade — contains all fields needed for downstream analysis."""
    # Identity
    ticker: str
    fold_id: int
    # Entry
    entry_bar: pd.Timestamp
    entry_price: float
    # Exit
    exit_bar: pd.Timestamp
    exit_price: float
    exit_reason: str        # STOP_LOSS | TAKE_PROFIT | SELL_SIGNAL | TIME_EXIT
    # Size
    shares: int
    dollars_allocated: float
    # P&L
    pnl_gross: float
    pnl_net: float
    return_pct: float
    equity_at_exit: float
    # MC metadata
    mc_sl_raw: float
    mc_sl_applied: float
    mc_tp: float
    rr: float
    p_tp: float
    p_sl: float
    ev: float
    sigma_annual: float
    signal_confirmation_count: int
    # Normal-engine compatibility aliases (set in __post_init__)
    asset: str = ""
    entry_date: Optional[pd.Timestamp] = None
    exit_date: Optional[pd.Timestamp] = None
    direction: str = "long"
    pnl: float = 0.0
    stop_triggered: bool = False

    def __post_init__(self):
        self.asset = self.ticker
        self.entry_date = self.entry_bar
        self.exit_date = self.exit_bar
        self.pnl = self.pnl_net
        self.stop_triggered = (self.exit_reason == "STOP_LOSS")


@dataclass
class MCEngineResult:
    """Return value of run_mc_walk_forward — compatible with BacktestResult fields."""
    equity_curve: pd.Series
    benchmark_curve: pd.Series
    trade_log: pd.DataFrame
    fold_returns: List[pd.Series]
    metrics: dict
    weights_history: pd.DataFrame
    # MC-specific extras
    mc_trade_details: List[dict]
    mc_aggregate_stats: dict
    # Single-ticker mode: buy-and-hold curve rebased to initial_capital (None otherwise)
    buyhold_curve: Optional[pd.Series] = None


# ─────────────────────────────────────────────────────────────────────────────
# Vol / drift estimation
# ─────────────────────────────────────────────────────────────────────────────

def estimate_vol_drift(
    ticker: str,
    bar: pd.Timestamp,
    prices: pd.DataFrame,
    params: MCParams,
) -> Tuple[Optional[float], float]:
    """
    Estimate annualised volatility and drift for *ticker* at *bar*.

    Parameters
    ----------
    ticker : column name in prices
    bar    : the signal bar date — data is sliced to [:bar] INCLUSIVE
    prices : full price DataFrame (DatetimeIndex × tickers)
    params : MCParams

    Returns
    -------
    (sigma_annual, mu_annual) or (None, 0.0) if insufficient history.

    Constraints
    -----------
    - Only data up to and including bar is used (no lookahead).
    - Hard assertion: returns.index.max() <= bar.
    """
    if ticker not in prices.columns:
        return None, 0.0

    hist = prices[ticker].loc[:bar].tail(params.vol_lookback_days + 1)
    returns = hist.pct_change().dropna()

    if len(returns) < max(5, params.vol_lookback_days // 2):
        return None, 0.0

    # Non-negotiable lookahead guard
    assert returns.index.max() <= bar, (
        f"Lookahead violation for {ticker} at {bar}: "
        f"returns.index.max()={returns.index.max()}"
    )

    if params.vol_method == "ewma":
        ewma_var = returns.ewm(halflife=params.ewma_halflife_days).var().iloc[-1]
        sigma_daily = math.sqrt(float(ewma_var)) if ewma_var > 0 else returns.std()
    else:
        sigma_daily = float(returns.std())

    sigma_annual = float(np.clip(
        sigma_daily * math.sqrt(252),
        params.vol_floor,
        params.vol_cap,
    ))

    mu_annual = 0.0
    if params.drift_method == "historical_mean":
        mu_annual = float(returns.mean()) * 252

    return sigma_annual, mu_annual


# ─────────────────────────────────────────────────────────────────────────────
# Monte Carlo simulation
# ─────────────────────────────────────────────────────────────────────────────

def run_mc_simulation(
    ticker: str,
    entry_price: float,
    sigma_annual: float,
    mu_annual: float,
    bar_index: int,
    params: MCParams,
) -> MCSimResult:
    """
    Simulate *n_simulations* GBM / Student-t price paths of length *holding_days*.

    Parameters
    ----------
    ticker       : asset identifier (used only for the result label)
    entry_price  : simulated entry price
    sigma_annual : annualised volatility (already clipped to [vol_floor, vol_cap])
    mu_annual    : annualised drift (0 when drift_method=="zero")
    bar_index    : integer index of this bar — used to seed the RNG
    params       : MCParams

    Returns
    -------
    MCSimResult with tp_price, sl_price, rr, p_tp, p_sl, ev, mfe, mae.

    Notes
    -----
    - RNG is seeded with seed_base + bar_index for reproducibility.
    - Itô correction applied to drift: daily_drift = (mu - 0.5*sigma²) * dt.
    - SL floor = entry * (1 - max_stop_loss_pct); the more protective (higher) of
      sl_raw and sl_floor is used.
    - TP is uncapped.
    """
    dt = 1.0 / 252.0
    daily_drift = (mu_annual - 0.5 * sigma_annual ** 2) * dt
    daily_vol = sigma_annual * math.sqrt(dt)

    rng = np.random.default_rng(seed=params.seed_base + bar_index)

    endpoints: List[float] = []
    path_max: List[float] = []
    path_min: List[float] = []

    for _ in range(params.n_simulations):
        if params.shock_distribution == "student_t":
            z = rng.standard_t(df=params.student_t_df, size=params.holding_days)
        else:
            z = rng.standard_normal(size=params.holding_days)

        log_rets = daily_drift + daily_vol * z
        path = entry_price * np.exp(np.cumsum(log_rets))
        endpoints.append(float(path[-1]))
        path_max.append(float(path.max()))
        path_min.append(float(path.min()))

    tp_raw = float(np.quantile(endpoints, params.tp_quantile))
    sl_raw = float(np.quantile(endpoints, params.sl_quantile))

    sl_floor = entry_price * (1.0 - params.max_stop_loss_pct)
    sl_price = max(sl_raw, sl_floor)   # more protective = higher price
    tp_price = tp_raw

    sl_distance = entry_price - sl_price
    if sl_distance <= 0:
        # Degenerate: vol too low or sl_quantile pushed SL above entry
        sl_price = entry_price * (1.0 - params.max_stop_loss_pct)
        sl_distance = entry_price - sl_price

    rr = (tp_price - entry_price) / sl_distance if sl_distance > 0 else 0.0
    p_tp = float(np.mean([mx >= tp_price for mx in path_max]))
    p_sl = float(np.mean([mn <= sl_price for mn in path_min]))
    ev = p_tp * (tp_price - entry_price) - p_sl * sl_distance

    mfe = float(np.mean([(mx - entry_price) / entry_price for mx in path_max]))
    mae = float(np.mean([(mn - entry_price) / entry_price for mn in path_min]))

    return MCSimResult(
        ticker=ticker,
        entry_price=entry_price,
        tp_price=tp_price,
        sl_price=sl_price,
        sl_raw=sl_raw,
        tp_raw=tp_raw,
        rr=rr,
        p_tp=p_tp,
        p_sl=p_sl,
        ev=ev,
        mfe=mfe,
        mae=mae,
        sigma_annual=sigma_annual,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Correlation helper
# ─────────────────────────────────────────────────────────────────────────────

def _max_corr_with_open(
    ticker: str,
    open_tickers: List[str],
    prices: pd.DataFrame,
    bar: pd.Timestamp,
    lookback: int,
) -> float:
    """
    Maximum absolute rolling correlation between *ticker* and any held ticker.

    Uses the last *lookback* trading days of returns, point-in-time at *bar*.
    Returns 0.0 if insufficient data or no open positions.
    """
    if not open_tickers:
        return 0.0
    all_t = [ticker] + [t for t in open_tickers if t != ticker]
    available = [t for t in all_t if t in prices.columns]
    if ticker not in available or len(available) < 2:
        return 0.0
    rets = prices[available].loc[:bar].tail(lookback + 1).pct_change().dropna()
    if len(rets) < 10:
        return 0.0
    try:
        corr_col = rets.corr()[ticker].drop(ticker, errors="ignore")
        return float(corr_col.abs().max()) if not corr_col.empty else 0.0
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Position sizing
# ─────────────────────────────────────────────────────────────────────────────

def compute_position_size(
    mc: MCSimResult,
    portfolio_value: float,
    cash: float,
    open_positions: Dict[str, OpenPosition],
    prices: pd.DataFrame,
    bar: pd.Timestamp,
    params: MCParams,
) -> Tuple[int, float]:
    """
    Compute the number of shares and dollar value for a new entry.

    Parameters
    ----------
    mc              : MCSimResult for this entry
    portfolio_value : current mark-to-market portfolio value
    cash            : available cash
    open_positions  : currently open positions (for correlation check)
    prices          : full price DataFrame (for correlation computation)
    bar             : current bar date
    params          : MCParams

    Returns
    -------
    (shares, dollars) — shares=0 means don't enter.
    """
    if params.sizing_method == "risk_parity_sl":
        risk_dollars = portfolio_value * params.acceptable_risk_pct
        sl_distance = mc.entry_price - mc.sl_price
        if sl_distance <= 0:
            return 0, 0.0
        dollars = risk_dollars / sl_distance * mc.entry_price
    else:  # kelly_mc
        f_star = max(0.0, (mc.p_tp * mc.rr - (1.0 - mc.p_tp)) / mc.rr) if mc.rr > 0 else 0.0
        dollars = f_star * params.kelly_fraction * portfolio_value

    # Hard caps
    dollars = min(dollars, portfolio_value * params.max_position_pct)
    reserve = portfolio_value * params.cash_reserve_pct
    dollars = min(dollars, cash - reserve)

    if dollars <= 0:
        return 0, 0.0

    # Correlation penalty
    if params.correlation_penalty_enabled and open_positions:
        max_corr = _max_corr_with_open(
            mc.ticker,
            list(open_positions.keys()),
            prices,
            bar,
            params.vol_lookback_days,
        )
        if max_corr > params.correlation_threshold:
            dollars *= (1.0 - params.correlation_penalty_factor)

    if dollars <= 0:
        return 0, 0.0

    shares = int(dollars / mc.entry_price)
    actual_dollars = shares * mc.entry_price
    return shares, actual_dollars


# ─────────────────────────────────────────────────────────────────────────────
# Exit priority check
# ─────────────────────────────────────────────────────────────────────────────

def check_exits_priority(
    pos: OpenPosition,
    current_price: float,
    bar: pd.Timestamp,
    bar_loc: int,           # integer index in prices.index
    sell_signal: float,     # pre-generated signal value for pos.ticker at bar
    params: MCParams,
) -> Optional[Tuple[str, float, float]]:
    """
    Check all exit conditions for *pos* in SL → TP → Signal → Time order.

    Parameters
    ----------
    pos           : open position
    current_price : today's close for this ticker
    bar           : current bar date
    bar_loc       : integer location of bar in the global prices index
    sell_signal   : strategy signal value for this ticker at bar
    params        : MCParams

    Returns
    -------
    (exit_reason, exit_price, commission_rate) or None (hold).

    Exit reasons: "STOP_LOSS" | "TAKE_PROFIT" | "PARTIAL_TP" | "SELL_SIGNAL" | "TIME_EXIT"
    """
    # ── PRIORITY 1: SL — always first, always hard ────────────────────────
    if current_price <= pos.sl_price:
        commission = (params.commission_bps + params.sl_commission_bps) / 10_000.0
        return ("STOP_LOSS", current_price, commission)

    # ── PRIORITY 2: TP — only when sell_strategy includes MC exits ────────
    if params.sell_strategy in ("TP_SL", "BOTH"):
        if current_price >= pos.tp_price:
            commission = params.commission_bps / 10_000.0
            if params.partial_tp_pct < 1.0:
                return ("PARTIAL_TP", pos.tp_price, commission)
            return ("TAKE_PROFIT", pos.tp_price, commission)

    # ── PRIORITY 3: strategy sell signal ─────────────────────────────────
    if params.sell_strategy != "TP_SL":
        if float(sell_signal) != 1.0:   # no longer bullish
            commission = params.commission_bps / 10_000.0
            return ("SELL_SIGNAL", current_price, commission)

    # ── BREAKEVEN TRAIL: ratchet SL to entry after 1R profit ─────────────
    if params.breakeven_trail_enabled and not pos.breakeven_trail_active:
        initial_risk = pos.initial_sl_price  # already a price level
        initial_risk_pct = (pos.entry_price - pos.initial_sl_price) / pos.entry_price
        profit_pct = (current_price - pos.entry_price) / pos.entry_price
        if profit_pct >= initial_risk_pct:
            pos.sl_price = max(pos.sl_price, pos.entry_price)   # ratchet only
            pos.breakeven_trail_active = True

    # ── TIME EXIT: force close after max_holding_days ─────────────────────
    bars_held = bar_loc - pos.entry_bar_loc
    if bars_held >= params.max_holding_days:
        commission = params.commission_bps / 10_000.0
        return ("TIME_EXIT", current_price, commission)

    return None  # hold


# ─────────────────────────────────────────────────────────────────────────────
# Single fold runner (internal)
# ─────────────────────────────────────────────────────────────────────────────

def _run_fold(
    prices: pd.DataFrame,
    buy_signals: pd.DataFrame,
    sell_signals: pd.DataFrame,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    params: MCParams,
    fold_id: int,
    # shared state (mutated in-place across folds)
    open_positions: Dict[str, OpenPosition],
    cash_ref: List[float],          # [cash] — mutable container
    signal_streak: Dict[str, int],
    cooloff_tracker: Dict[str, pd.Timestamp],
    bar_counter: List[int],         # [global_bar_idx]
    breakeven_trail_count: List[int],
    filtered_ev: List[int],
    filtered_rr: List[int],
    filtered_ptp: List[int],
    total_candidates: List[int],
) -> Tuple[List[TradeRecord], List[Tuple[pd.Timestamp, float]], List[Tuple[pd.Timestamp, dict]]]:
    """
    Run one test fold bar-by-bar. Mutates open_positions, cash_ref, signal_streak,
    cooloff_tracker, bar_counter in-place so state carries across folds.

    Returns (trade_records, equity_vals, weights_vals).
    """
    test_prices = prices.loc[test_start:test_end]
    if test_prices.empty:
        return [], [], []

    test_dates = test_prices.index
    prices_index = prices.index

    trade_records: List[TradeRecord] = []
    equity_vals: List[Tuple[pd.Timestamp, float]] = []
    weights_vals: List[Tuple[pd.Timestamp, dict]] = []

    # pending_entries: ticker → (MCSimResult, sig_count) — for open_next_day mode
    pending_entries: Dict[str, Tuple[MCSimResult, int]] = {}

    for bar_idx_in_fold, bar in enumerate(test_dates):
        today_prices = test_prices.loc[bar]
        bar_loc = prices_index.get_loc(bar)
        cash = cash_ref[0]

        # ── Mark-to-market ────────────────────────────────────────────────
        mtm = sum(
            pos.shares * float(today_prices.get(t, 0) or 0)
            for t, pos in open_positions.items()
        )
        portfolio_value = cash + mtm

        # ── Execute pending entries (open_next_day) ───────────────────────
        if params.fill_price == "open_next_day" and pending_entries:
            to_remove = []
            n_added = 0
            for ticker, (mc_res, sig_count) in pending_entries.items():
                if ticker in open_positions:
                    to_remove.append(ticker)
                    continue
                if len(open_positions) >= params.max_open_positions:
                    break
                entry_price = float(today_prices.get(ticker, 0) or 0)
                if entry_price <= 0:
                    to_remove.append(ticker)
                    continue

                # Re-evaluate size at actual entry price (MC levels kept from signal bar)
                shares, dollars = compute_position_size(
                    mc_res, portfolio_value, cash, open_positions, prices, bar, params
                )
                if shares <= 0:
                    to_remove.append(ticker)
                    continue

                commission = (params.commission_bps / 10_000.0) * dollars
                cost = dollars + commission
                if cash < cost:
                    to_remove.append(ticker)
                    continue

                cash -= cost
                cash_ref[0] = cash
                open_positions[ticker] = OpenPosition(
                    ticker=ticker,
                    entry_bar=bar,
                    entry_bar_loc=bar_loc,
                    entry_price=entry_price,
                    shares=shares,
                    dollars_allocated=dollars,
                    sl_price=mc_res.sl_price,
                    initial_sl_price=mc_res.sl_price,
                    tp_price=mc_res.tp_price,
                    fold_id=fold_id,
                    mc_sl_raw=mc_res.sl_raw,
                    mc_tp=mc_res.tp_price,
                    rr=mc_res.rr,
                    p_tp=mc_res.p_tp,
                    p_sl=mc_res.p_sl,
                    ev=mc_res.ev,
                    sigma_annual=mc_res.sigma_annual,
                    signal_confirmation_count=sig_count,
                )
                to_remove.append(ticker)
                n_added += 1
            for t in to_remove:
                pending_entries.pop(t, None)

        # ── Check exits for open positions ────────────────────────────────
        exits_this_bar: List[Tuple[str, OpenPosition, float, Tuple]] = []
        for ticker, pos in list(open_positions.items()):
            cur_price = float(today_prices.get(ticker, 0) or 0)
            if cur_price <= 0:
                continue
            sell_sig = (
                float(sell_signals.at[bar, ticker])
                if sell_signals is not None and bar in sell_signals.index and ticker in sell_signals.columns
                else 1.0   # no signal → hold
            )
            result = check_exits_priority(pos, cur_price, bar, bar_loc, sell_sig, params)
            if result is not None:
                exits_this_bar.append((ticker, pos, cur_price, result))

        # ── Process exits ─────────────────────────────────────────────────
        for ticker, pos, cur_price, (exit_reason, exit_price, commission_rate) in exits_this_bar:
            if exit_reason == "PARTIAL_TP":
                # Close fraction; keep remainder with breakeven SL
                close_shares = max(1, int(pos.shares * params.partial_tp_pct))
                remain_shares = pos.shares - close_shares
                close_dollars = close_shares * exit_price
                commission = commission_rate * close_dollars
                pnl_gross = close_shares * (exit_price - pos.entry_price)
                pnl_net = pnl_gross - commission
                cash += close_dollars - commission
                cash_ref[0] = cash

                portfolio_value_exit = cash + sum(
                    p.shares * float(today_prices.get(t, 0) or 0)
                    for t, p in open_positions.items()
                )

                trade_records.append(TradeRecord(
                    ticker=ticker, fold_id=pos.fold_id,
                    entry_bar=pos.entry_bar, entry_price=pos.entry_price,
                    exit_bar=bar, exit_price=exit_price,
                    exit_reason="TAKE_PROFIT",
                    shares=close_shares, dollars_allocated=pos.dollars_allocated,
                    pnl_gross=pnl_gross, pnl_net=pnl_net,
                    return_pct=(exit_price / pos.entry_price - 1.0),
                    equity_at_exit=portfolio_value_exit,
                    mc_sl_raw=pos.mc_sl_raw, mc_sl_applied=pos.sl_price,
                    mc_tp=pos.mc_tp, rr=pos.rr, p_tp=pos.p_tp, p_sl=pos.p_sl,
                    ev=pos.ev, sigma_annual=pos.sigma_annual,
                    signal_confirmation_count=pos.signal_confirmation_count,
                ))

                if remain_shares > 0:
                    # Update position: fewer shares, SL moved to entry
                    open_positions[ticker] = dataclasses.replace(
                        pos,
                        shares=remain_shares,
                        sl_price=max(pos.sl_price, pos.entry_price),
                        breakeven_trail_active=True,
                    )
                else:
                    del open_positions[ticker]
            else:
                pnl_gross = pos.shares * (exit_price - pos.entry_price)
                commission = commission_rate * pos.shares * exit_price
                pnl_net = pnl_gross - commission
                cash += pos.shares * exit_price - commission
                cash_ref[0] = cash

                portfolio_value_exit = cash + sum(
                    p.shares * float(today_prices.get(t, 0) or 0)
                    for t, p in open_positions.items()
                    if t != ticker
                )

                trade_records.append(TradeRecord(
                    ticker=ticker, fold_id=pos.fold_id,
                    entry_bar=pos.entry_bar, entry_price=pos.entry_price,
                    exit_bar=bar, exit_price=exit_price,
                    exit_reason=exit_reason,
                    shares=pos.shares, dollars_allocated=pos.dollars_allocated,
                    pnl_gross=pnl_gross, pnl_net=pnl_net,
                    return_pct=(exit_price / pos.entry_price - 1.0),
                    equity_at_exit=portfolio_value_exit,
                    mc_sl_raw=pos.mc_sl_raw, mc_sl_applied=pos.sl_price,
                    mc_tp=pos.mc_tp, rr=pos.rr, p_tp=pos.p_tp, p_sl=pos.p_sl,
                    ev=pos.ev, sigma_annual=pos.sigma_annual,
                    signal_confirmation_count=pos.signal_confirmation_count,
                ))
                del open_positions[ticker]

                if exit_reason == "STOP_LOSS":
                    cooloff_tracker[ticker] = bar
                    if params.breakeven_trail_enabled:
                        breakeven_trail_count[0] += 0  # only count activations, not SL hits

        # ── Check for breakeven trail activations (count) ─────────────────
        for pos in open_positions.values():
            if pos.breakeven_trail_active and not getattr(pos, "_bt_counted", False):
                breakeven_trail_count[0] += 1
                pos._bt_counted = True  # type: ignore[attr-defined]

        # ── Update signal streaks ─────────────────────────────────────────
        buy_row = buy_signals.loc[bar] if bar in buy_signals.index else pd.Series(0.0, index=prices.columns)
        for ticker in prices.columns:
            sig = float(buy_row.get(ticker, 0) or 0)
            if sig == 1.0:
                signal_streak[ticker] = signal_streak.get(ticker, 0) + 1
            else:
                signal_streak[ticker] = 0

        # ── Refresh cash and portfolio value after exits ──────────────────
        cash = cash_ref[0]
        mtm = sum(pos.shares * float(today_prices.get(t, 0) or 0) for t, pos in open_positions.items())
        portfolio_value = cash + mtm

        # ── New entry candidates ──────────────────────────────────────────
        candidates: List[str] = []
        for ticker in prices.columns:
            if ticker in open_positions:
                continue
            if params.fill_price == "open_next_day" and ticker in pending_entries:
                continue
            if signal_streak.get(ticker, 0) < params.signal_confirmation_bars:
                continue
            # Cooloff check (calendar days)
            if ticker in cooloff_tracker:
                days_since = (bar - cooloff_tracker[ticker]).days
                if days_since < params.cooloff_days:
                    continue
                else:
                    del cooloff_tracker[ticker]
            candidates.append(ticker)

        # Limit per bar
        candidates = candidates[: params.max_signals_per_bar]

        n_new = 0
        for ticker in candidates:
            total_open = len(open_positions) + (len(pending_entries) if params.fill_price == "open_next_day" else 0)
            if total_open >= params.max_open_positions:
                break
            if n_new >= params.max_signals_per_bar:
                break

            cur_price = float(today_prices.get(ticker, 0) or 0)
            if cur_price <= 0:
                continue

            sigma, mu = estimate_vol_drift(ticker, bar, prices, params)
            if sigma is None:
                continue

            global_bar_idx = bar_counter[0]
            bar_counter[0] += 1

            mc = run_mc_simulation(ticker, cur_price, sigma, mu, global_bar_idx, params)

            # Track filter stats
            total_candidates[0] += 1
            passed = True
            if mc.rr < params.min_rr_ratio:
                filtered_rr[0] += 1
                passed = False
            if mc.p_tp < params.min_p_tp:
                filtered_ptp[0] += 1
                passed = False
            if passed:
                # Check EV (need shares estimate; use quick estimate)
                quick_shares = max(1, int((portfolio_value * params.acceptable_risk_pct /
                                           max(cur_price - mc.sl_price, 0.01)) * cur_price))
                if mc.ev * quick_shares < params.min_ev_dollars:
                    filtered_ev[0] += 1
                    passed = False

            if not passed:
                continue

            if params.fill_price == "close":
                shares, dollars = compute_position_size(
                    mc, portfolio_value, cash, open_positions, prices, bar, params
                )
                if shares <= 0:
                    continue
                commission = (params.commission_bps / 10_000.0) * dollars
                cost = dollars + commission
                if cash < cost:
                    continue
                cash -= cost
                cash_ref[0] = cash
                open_positions[ticker] = OpenPosition(
                    ticker=ticker,
                    entry_bar=bar,
                    entry_bar_loc=bar_loc,
                    entry_price=cur_price,
                    shares=shares,
                    dollars_allocated=dollars,
                    sl_price=mc.sl_price,
                    initial_sl_price=mc.sl_price,
                    tp_price=mc.tp_price,
                    fold_id=fold_id,
                    mc_sl_raw=mc.sl_raw,
                    mc_tp=mc.tp_price,
                    rr=mc.rr,
                    p_tp=mc.p_tp,
                    p_sl=mc.p_sl,
                    ev=mc.ev,
                    sigma_annual=mc.sigma_annual,
                    signal_confirmation_count=signal_streak.get(ticker, 0),
                )
                n_new += 1
            else:
                pending_entries[ticker] = (mc, signal_streak.get(ticker, 0))
                n_new += 1

        # ── Record end-of-bar state ───────────────────────────────────────
        cash = cash_ref[0]
        mtm = sum(pos.shares * float(today_prices.get(t, 0) or 0) for t, pos in open_positions.items())
        portfolio_value = cash + mtm
        equity_vals.append((bar, portfolio_value))

        weight_row: Dict[str, float] = {}
        if portfolio_value > 0:
            for t, pos in open_positions.items():
                p = float(today_prices.get(t, 0) or 0)
                if p > 0:
                    weight_row[t] = pos.shares * p / portfolio_value
        weights_vals.append((bar, weight_row))

    return trade_records, equity_vals, weights_vals


# ─────────────────────────────────────────────────────────────────────────────
# Grid-search MC params on training window
# ─────────────────────────────────────────────────────────────────────────────

def _grid_search_mc_params(
    prices: pd.DataFrame,
    buy_signals: pd.DataFrame,
    sell_signals: pd.DataFrame,
    train_end: pd.Timestamp,
    params: MCParams,
) -> Tuple[float, float]:
    """
    Grid-search sl_quantile × tp_quantile on the last test_window_days of training data.

    Parameters
    ----------
    prices       : full price DataFrame
    buy_signals  : pre-generated buy signals
    sell_signals : pre-generated sell signals (or None)
    train_end    : end date of training period
    params       : base MCParams

    Returns
    -------
    (best_sl_quantile, best_tp_quantile)
    """
    # Evaluate on the last test_window_days of training data
    train_slice = prices.loc[:train_end]
    if len(train_slice) < params.vol_lookback_days + params.test_window_days:
        return params.sl_quantile, params.tp_quantile

    eval_end = train_end
    eval_start_loc = max(0, len(train_slice) - params.test_window_days)
    eval_start = train_slice.index[eval_start_loc]

    best_sharpe = -math.inf
    best_sl_q = params.sl_quantile
    best_tp_q = params.tp_quantile

    for sl_q in params.sl_quantile_grid:
        for tp_q in params.tp_quantile_grid:
            if tp_q <= sl_q + 0.05:
                continue
            trial_params = dataclasses.replace(
                params,
                sl_quantile=sl_q,
                tp_quantile=tp_q,
                optimise_mc_params_on_train=False,
            )
            # Isolated state for this trial
            trial_positions: Dict[str, OpenPosition] = {}
            trial_cash = [params.initial_capital]
            trial_streak: Dict[str, int] = {}
            trial_cooloff: Dict[str, pd.Timestamp] = {}
            trial_bar_counter = [0]

            records, eq_vals, _ = _run_fold(
                prices=prices,
                buy_signals=buy_signals,
                sell_signals=sell_signals,
                test_start=eval_start,
                test_end=eval_end,
                params=trial_params,
                fold_id=-1,
                open_positions=trial_positions,
                cash_ref=trial_cash,
                signal_streak=trial_streak,
                cooloff_tracker=trial_cooloff,
                bar_counter=trial_bar_counter,
                breakeven_trail_count=[0],
                filtered_ev=[0], filtered_rr=[0], filtered_ptp=[0],
                total_candidates=[0],
            )
            if len(eq_vals) < 5:
                continue
            eq = pd.Series({d: v for d, v in eq_vals}, dtype=float)
            if records:
                tl = pd.DataFrame([dataclasses.asdict(r) for r in records])
            else:
                tl = pd.DataFrame(columns=["return_pct", "direction"])
            m = compute_metrics(eq, tl)
            sharpe = m.get("sharpe_ratio") or -math.inf
            if math.isfinite(sharpe) and sharpe > best_sharpe:
                best_sharpe = sharpe
                best_sl_q = sl_q
                best_tp_q = tp_q

    return best_sl_q, best_tp_q


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_mc_walk_forward(
    prices: pd.DataFrame,
    benchmark_prices: pd.Series,
    params: MCParams,
) -> MCEngineResult:
    """
    Execute a Monte Carlo integrated walk-forward backtest.

    Parameters
    ----------
    prices           : DatetimeIndex × ticker DataFrame of adjusted close prices.
                       Must span [backtest_start - vol_lookback warmup, backtest_end].
    benchmark_prices : pd.Series of benchmark adjusted close prices.
    params           : MCParams with all configuration.

    Returns
    -------
    MCEngineResult — compatible with BacktestResult; includes mc_trade_details and
    mc_aggregate_stats as extras.

    Raises
    ------
    AssertionError  if purge_days < holding_days, or vol warmup is insufficient.
    ValueError      if buy_strategy is unknown or data is too short.
    """
    from src.strategies import STRATEGY_MAP

    # ── Input validation ──────────────────────────────────────────────────
    assert params.purge_days >= params.holding_days, (
        f"purge_days ({params.purge_days}) must be >= holding_days ({params.holding_days}) "
        "to prevent open positions crossing the fold boundary."
    )
    assert 0.01 <= params.max_stop_loss_pct <= 0.30, "max_stop_loss_pct must be in [0.01, 0.30]"
    assert 0.0 < params.acceptable_risk_pct <= 0.05, "acceptable_risk_pct must be in (0, 0.05]"
    assert params.fill_price in ("open_next_day", "close"), f"Unknown fill_price: {params.fill_price}"
    assert params.buy_strategy in STRATEGY_MAP, f"Unknown buy_strategy: {params.buy_strategy}"

    if params.sell_strategy not in ("TP_SL", "BOTH") and params.sell_strategy not in STRATEGY_MAP:
        raise ValueError(f"Unknown sell_strategy: {params.sell_strategy}")

    backtest_start = pd.Timestamp(params.backtest_start)
    backtest_end = pd.Timestamp(params.backtest_end)

    # Check vol warmup
    pre_data = prices.loc[:backtest_start]
    warmup_bars = len(pre_data) - 1  # exclude backtest_start itself
    assert warmup_bars >= params.vol_lookback_days, (
        f"Insufficient warmup data before backtest_start: {warmup_bars} bars, "
        f"need >= {params.vol_lookback_days}."
    )

    # ── Generate signals upfront ──────────────────────────────────────────
    buy_strat = STRATEGY_MAP[params.buy_strategy]()
    buy_signals = buy_strat.generate_signals(prices, benchmark_prices=benchmark_prices)
    buy_signals = buy_signals.reindex_like(prices).fillna(0.0)

    if params.sell_strategy in ("TP_SL",):
        sell_signals = None
    else:
        # "BOTH" → exit when buy signal drops; named strategy → use that strategy
        sell_key = params.buy_strategy if params.sell_strategy == "BOTH" else params.sell_strategy
        sell_strat = STRATEGY_MAP[sell_key]()
        sell_sigs_raw = sell_strat.generate_signals(prices, benchmark_prices=benchmark_prices)
        sell_signals = sell_sigs_raw.reindex_like(prices).fillna(0.0)

    # ── Build fold test windows ───────────────────────────────────────────
    test_dates_all = prices.loc[backtest_start:backtest_end].index
    if len(test_dates_all) == 0:
        raise ValueError("No trading days in [backtest_start, backtest_end].")

    n_bars = len(test_dates_all)
    bars_per_fold = n_bars // params.n_folds
    if bars_per_fold < 10:
        raise ValueError(
            f"Too few bars per fold ({bars_per_fold}). "
            f"Reduce n_folds or extend the backtest period."
        )

    fold_windows: List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    for fi in range(params.n_folds):
        ts_idx = fi * bars_per_fold
        te_idx = min((fi + 1) * bars_per_fold, n_bars) - 1
        ts = test_dates_all[ts_idx]
        te = test_dates_all[te_idx]
        train_end_date = ts - timedelta(days=params.purge_days)
        fold_windows.append((train_end_date, ts, te))

    # ── Shared mutable state across all folds ─────────────────────────────
    open_positions: Dict[str, OpenPosition] = {}
    cash_ref: List[float] = [params.initial_capital]
    signal_streak: Dict[str, int] = {}
    cooloff_tracker: Dict[str, pd.Timestamp] = {}
    bar_counter: List[int] = [0]
    breakeven_trail_count: List[int] = [0]
    filtered_ev: List[int] = [0]
    filtered_rr: List[int] = [0]
    filtered_ptp: List[int] = [0]
    total_candidates: List[int] = [0]

    all_trade_records: List[TradeRecord] = []
    all_equity_vals: List[Tuple[pd.Timestamp, float]] = []
    all_weights_vals: List[Tuple[pd.Timestamp, dict]] = []
    fold_equity_list: List[pd.Series] = []

    # ── Walk-forward fold loop ────────────────────────────────────────────
    for fold_idx, (train_end_date, test_start, test_end) in enumerate(fold_windows):
        # Optionally optimise MC params on training window
        if params.optimise_mc_params_on_train:
            fold_sl_q, fold_tp_q = _grid_search_mc_params(
                prices=prices,
                buy_signals=buy_signals,
                sell_signals=sell_signals,
                train_end=train_end_date,
                params=params,
            )
            fold_params = dataclasses.replace(
                params, sl_quantile=fold_sl_q, tp_quantile=fold_tp_q
            )
        else:
            fold_params = params

        records, eq_vals, wt_vals = _run_fold(
            prices=prices,
            buy_signals=buy_signals,
            sell_signals=sell_signals,
            test_start=test_start,
            test_end=test_end,
            params=fold_params,
            fold_id=fold_idx,
            open_positions=open_positions,
            cash_ref=cash_ref,
            signal_streak=signal_streak,
            cooloff_tracker=cooloff_tracker,
            bar_counter=bar_counter,
            breakeven_trail_count=breakeven_trail_count,
            filtered_ev=filtered_ev,
            filtered_rr=filtered_rr,
            filtered_ptp=filtered_ptp,
            total_candidates=total_candidates,
        )

        all_trade_records.extend(records)
        all_equity_vals.extend(eq_vals)
        all_weights_vals.extend(wt_vals)

        fold_equity_list.append(
            pd.Series(
                {d: v for d, v in eq_vals},
                dtype=float,
                name=f"fold_{fold_idx + 1}",
            )
        )

    # ── Force-close any positions still open at end of last fold ─────────
    if open_positions and all_equity_vals:
        last_bar = all_equity_vals[-1][0]
        last_prices = prices.loc[last_bar]
        for ticker, pos in list(open_positions.items()):
            cur_price = float(last_prices.get(ticker, 0) or 0)
            if cur_price <= 0:
                continue
            commission = params.commission_bps / 10_000.0 * pos.shares * cur_price
            pnl_gross = pos.shares * (cur_price - pos.entry_price)
            pnl_net = pnl_gross - commission
            cash_ref[0] += pos.shares * cur_price - commission
            all_trade_records.append(TradeRecord(
                ticker=ticker, fold_id=pos.fold_id,
                entry_bar=pos.entry_bar, entry_price=pos.entry_price,
                exit_bar=last_bar, exit_price=cur_price,
                exit_reason="TIME_EXIT",
                shares=pos.shares, dollars_allocated=pos.dollars_allocated,
                pnl_gross=pnl_gross, pnl_net=pnl_net,
                return_pct=(cur_price / pos.entry_price - 1.0),
                equity_at_exit=cash_ref[0],
                mc_sl_raw=pos.mc_sl_raw, mc_sl_applied=pos.sl_price,
                mc_tp=pos.mc_tp, rr=pos.rr, p_tp=pos.p_tp, p_sl=pos.p_sl,
                ev=pos.ev, sigma_annual=pos.sigma_annual,
                signal_confirmation_count=pos.signal_confirmation_count,
            ))
        open_positions.clear()

    # ── Build equity curve ────────────────────────────────────────────────
    equity_curve = pd.Series(
        {d: v for d, v in all_equity_vals},
        dtype=float,
        name="portfolio",
    ).sort_index()

    # ── Benchmark curve (rebased to initial_capital) ──────────────────────
    bm_dates = benchmark_prices.index[benchmark_prices.index.isin(equity_curve.index)]
    if len(bm_dates) == 0:
        bm_dates = benchmark_prices.index
    bm_slice = benchmark_prices.loc[bm_dates].sort_index().dropna()
    if len(bm_slice) > 0:
        benchmark_curve = (bm_slice / bm_slice.iloc[0]) * params.initial_capital
        benchmark_curve.name = "benchmark"
    else:
        benchmark_curve = pd.Series(dtype=float)

    # ── Trade log ─────────────────────────────────────────────────────────
    if all_trade_records:
        trade_log = pd.DataFrame([dataclasses.asdict(r) for r in all_trade_records])
    else:
        trade_log = pd.DataFrame(columns=[
            "asset", "entry_date", "exit_date", "entry_price", "exit_price",
            "direction", "return_pct", "pnl", "equity_at_exit", "stop_triggered",
            "mc_sl_raw", "mc_sl_applied", "mc_tp", "rr", "p_tp", "p_sl",
            "ev", "sigma_annual", "fold_id", "exit_reason",
        ])

    metrics = compute_metrics(equity_curve, trade_log)

    # ── Weights history ───────────────────────────────────────────────────
    if all_weights_vals:
        weights_history = pd.DataFrame(
            [v for _, v in all_weights_vals],
            index=[d for d, _ in all_weights_vals],
        ).fillna(0.0)
        weights_history.index = pd.to_datetime(weights_history.index)
    else:
        weights_history = pd.DataFrame(index=equity_curve.index, dtype=float)

    # ── MC-specific extras ────────────────────────────────────────────────
    mc_trade_details = [
        {
            "ticker":       r.ticker,
            "entry_date":   str(r.entry_bar)[:10],
            "sl_raw":       round(r.mc_sl_raw, 4),
            "sl_applied":   round(r.mc_sl_applied, 4),
            "tp":           round(r.mc_tp, 4),
            "rr":           round(r.rr, 3),
            "p_tp":         round(r.p_tp, 3),
            "ev":           round(r.ev, 4),
            "sigma_annual": round(r.sigma_annual, 4),
            "exit_reason":  r.exit_reason,
        }
        for r in all_trade_records
    ]

    n_total = total_candidates[0]
    mc_aggregate_stats: dict = {
        "mean_p_tp": (
            float(np.mean([r.p_tp for r in all_trade_records]))
            if all_trade_records else None
        ),
        "fraction_filtered_ev": (filtered_ev[0] / n_total if n_total > 0 else None),
        "fraction_filtered_rr": (filtered_rr[0] / n_total if n_total > 0 else None),
        "fraction_filtered_p_tp": (filtered_ptp[0] / n_total if n_total > 0 else None),
        "mean_sigma_at_entry": (
            float(np.mean([r.sigma_annual for r in all_trade_records]))
            if all_trade_records else None
        ),
        "breakeven_trail_activations": breakeven_trail_count[0],
        "total_candidates_evaluated": n_total,
        "total_trades_entered": len(all_trade_records),
    }

    # ── Buy-and-hold curve (single-ticker mode only) ──────────────────────
    buyhold_curve: Optional[pd.Series] = None
    if len(params.tickers) == 1:
        ticker = params.tickers[0]
        bh_prices = prices.loc[equity_curve.index, ticker].dropna() if ticker in prices.columns else pd.Series(dtype=float)
        if len(bh_prices) > 0:
            buyhold_curve = (bh_prices / bh_prices.iloc[0]) * params.initial_capital
            buyhold_curve.name = "buyhold"

    return MCEngineResult(
        equity_curve=equity_curve,
        benchmark_curve=benchmark_curve,
        trade_log=trade_log,
        fold_returns=fold_equity_list,
        metrics=metrics,
        weights_history=weights_history,
        mc_trade_details=mc_trade_details,
        mc_aggregate_stats=mc_aggregate_stats,
        buyhold_curve=buyhold_curve,
    )
