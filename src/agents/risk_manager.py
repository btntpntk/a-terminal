"""
src/agents/risk_manager.py
Stage 5 — Risk Management Engine

Responsibilities:
  1. Kelly fraction position sizing (half-Kelly with regime scaling)
  2. Portfolio heat tracking (total at-risk capital across open positions)
  3. Correlation check (prevents overconcentration in correlated names)
  4. CVaR budget enforcement (tail-risk cap at portfolio level)
  5. Final trade verdict: position size, exposure %, risk flags
"""

import numpy as np
import pandas as pd
import yfinance as yf
from dataclasses import dataclass, field
from typing import Optional
from src.agents.calculator import calculate_cvar_95, safe_scalar


# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

# Maximum fraction of portfolio allowed at risk across all open positions
MAX_PORTFOLIO_HEAT    = 0.06       # 6% — institutional standard
# Maximum single-position risk as a fraction of portfolio
MAX_SINGLE_RISK       = 0.02       # 2% per trade
# Minimum acceptable R:R ratio
MIN_RR_RATIO          = 1.5
# Max correlation allowed between a new position and existing holdings
MAX_CORRELATION       = 0.70       # Pearson r
# CVaR budget: max daily tail loss as a fraction of portfolio
MAX_CVAR_BUDGET       = 0.015      # 1.5% per day in tail scenario


# ─────────────────────────────────────────────────────────────
# OUTPUT DATACLASS
# ─────────────────────────────────────────────────────────────

@dataclass
class RiskDecision:
    verdict:              str          # APPROVED / REDUCED / REJECTED
    position_size_shares: int
    position_size_pct:    float        # % of portfolio
    risk_amount:          float        # THB/USD value at risk (entry→SL)
    regime_scale:         float        # multiplier applied (0.25–1.0)
    kelly_fraction:       float        # raw half-kelly before regime scale
    flags:                list  = field(default_factory=list)
    notes:                str   = ""


@dataclass
class OpenPosition:
    """Represents an existing open trade for portfolio-level calculations."""
    ticker:       str
    entry_price:  float
    sl_price:     float
    shares:       int
    portfolio_value: float             # total portfolio size in same currency


# ─────────────────────────────────────────────────────────────
# 1. HALF-KELLY POSITION SIZING
# ─────────────────────────────────────────────────────────────

def calculate_kelly_fraction(win_rate: float,
                              rr_ratio: float,
                              half_kelly: bool = True) -> float:
    """
    Kelly Criterion: f* = (W × (R+1) − 1) / R
    where W = win rate, R = reward-to-risk ratio.

    Half-Kelly (default): multiply f* by 0.5.
    This is the institutional standard — full Kelly is mathematically
    optimal but requires infinite rebalancing and causes large drawdowns.

    Parameters
    ----------
    win_rate  : float — historical win rate [0, 1]
    rr_ratio  : float — reward / risk (e.g. 2.0 = R:R of 2:1)
    half_kelly: bool  — apply 50% discount (recommended)

    Returns
    -------
    float — fraction of portfolio to risk (capped at MAX_SINGLE_RISK)
    """
    if rr_ratio <= 0 or win_rate <= 0:
        return 0.0

    # Kelly formula
    kelly = (win_rate * (rr_ratio + 1) - 1) / rr_ratio

    if kelly <= 0:
        return 0.0      # negative Kelly = don't trade

    if half_kelly:
        kelly *= 0.5

    # Hard cap: never risk more than MAX_SINGLE_RISK per trade
    return round(min(kelly, MAX_SINGLE_RISK), 6)


# ─────────────────────────────────────────────────────────────
# 2. REGIME SCALING
# ─────────────────────────────────────────────────────────────

def calculate_regime_scale(composite_risk: float) -> float:
    """
    Scale position size based on Stage 1 composite risk score.
    This is the critical link between macro and execution.

    composite_risk  Scale   Rationale
    ─────────────   ─────   ──────────────────────────────────────
    0 – 30          1.00    Low risk — full Kelly
    31 – 45         0.80    Moderate — slight reduction
    46 – 60         0.60    Elevated — meaningfully reduced
    61 – 74         0.40    High — cautious, smaller bets
    75 – 100        0.25    Critical — preserve capital
    """
    if composite_risk <= 30:  return 1.00
    if composite_risk <= 45:  return 0.80
    if composite_risk <= 60:  return 0.60
    if composite_risk <= 74:  return 0.40
    return 0.25


# ─────────────────────────────────────────────────────────────
# 3. PORTFOLIO HEAT
# ─────────────────────────────────────────────────────────────

def calculate_portfolio_heat(open_positions: list[OpenPosition]) -> dict:
    """
    Sum of all open risk amounts as a fraction of portfolio.
    Risk per position = (entry − SL) × shares / portfolio_value.

    Returns dict with total_heat_pct, remaining_capacity_pct, and
    whether a new trade would exceed the heat limit.
    """
    if not open_positions:
        return {
            "total_heat_pct":       0.0,
            "remaining_capacity":   MAX_PORTFOLIO_HEAT,
            "at_limit":             False,
            "positions_count":      0,
        }

    total_heat = 0.0
    for pos in open_positions:
        risk_per_share  = abs(pos.entry_price - pos.sl_price)
        position_risk   = (risk_per_share * pos.shares) / pos.portfolio_value
        total_heat     += position_risk

    remaining = max(0.0, MAX_PORTFOLIO_HEAT - total_heat)

    return {
        "total_heat_pct":     round(total_heat * 100, 3),
        "remaining_capacity": round(remaining * 100, 3),
        "at_limit":           total_heat >= MAX_PORTFOLIO_HEAT,
        "positions_count":    len(open_positions),
    }


# ─────────────────────────────────────────────────────────────
# 4. CORRELATION CHECK
# ─────────────────────────────────────────────────────────────

def check_correlation(new_ticker: str,
                      open_tickers: list[str],
                      period: str = "3mo") -> dict:
    """
    Pearson correlation of the new ticker's returns vs each open position.
    Flags if any pair exceeds MAX_CORRELATION (0.70).

    High correlation = you're adding a similar bet, not true diversification.
    """
    if not open_tickers:
        return {"max_correlation": 0.0, "correlated_with": [], "flag": False}

    try:
        # Fetch all returns in one batch
        all_tickers = [new_ticker] + open_tickers
        prices = {}
        for t in all_tickers:
            hist = yf.Ticker(t).history(period=period)["Close"].dropna()
            if not hist.empty:
                prices[t] = hist.pct_change().dropna()

        if new_ticker not in prices:
            return {"max_correlation": 0.0, "correlated_with": [], "flag": False}

        new_ret = prices[new_ticker]
        corrs   = {}

        for t in open_tickers:
            if t not in prices:
                continue
            combined = pd.concat([new_ret, prices[t]], axis=1).dropna()
            if len(combined) < 20:
                continue
            corr = float(combined.iloc[:, 0].corr(combined.iloc[:, 1]))
            corrs[t] = round(corr, 4)

        if not corrs:
            return {"max_correlation": 0.0, "correlated_with": [], "flag": False}

        max_corr       = max(corrs.values())
        correlated_with = [t for t, c in corrs.items() if c > MAX_CORRELATION]

        return {
            "all_correlations": corrs,
            "max_correlation":  round(max_corr, 4),
            "correlated_with":  correlated_with,
            "flag":             bool(correlated_with),
        }

    except Exception as e:
        return {"max_correlation": 0.0, "correlated_with": [], "flag": False,
                "error": str(e)}


# ─────────────────────────────────────────────────────────────
# 5. CVaR BUDGET CHECK
# ─────────────────────────────────────────────────────────────

def check_cvar_budget(new_ticker: str,
                      proposed_shares: int,
                      portfolio_value: float,
                      open_positions: list[OpenPosition] = None,
                      period: str = "6mo") -> dict:
    """
    Estimate the daily CVaR contribution of the new position and check
    whether it would breach the portfolio CVaR budget.

    CVaR contribution ≈ position_weight × stock_CVaR_95
    Portfolio CVaR budget = MAX_CVAR_BUDGET (1.5% of portfolio per day)
    """
    try:
        hist    = yf.Ticker(new_ticker).history(period=period)["Close"].dropna()
        returns = hist.pct_change().dropna()
        stock_cvar = calculate_cvar_95(returns)

        current_price    = float(hist.iloc[-1])
        position_value   = proposed_shares * current_price
        position_weight  = position_value / portfolio_value
        position_cvar    = position_weight * stock_cvar

        # Existing CVaR load — fetch actual CVaR per open position.
        # Falls back to a 2% floor only when price history is unavailable.
        existing_cvar = 0.0
        if open_positions:
            for pos in open_positions:
                try:
                    pos_hist    = yf.Ticker(pos.ticker).history(period=period)["Close"].dropna()
                    pos_returns = pos_hist.pct_change().dropna()
                    pos_cvar    = calculate_cvar_95(pos_returns)
                except Exception:
                    pos_cvar = 0.02   # fallback floor when data unavailable
                w = (pos.shares * pos.entry_price) / portfolio_value
                existing_cvar += w * pos_cvar

        total_cvar    = existing_cvar + position_cvar
        budget_ok     = total_cvar <= MAX_CVAR_BUDGET

        return {
            "new_position_cvar":  round(position_cvar * 100, 4),
            "existing_cvar_load": round(existing_cvar * 100, 4),
            "total_cvar_pct":     round(total_cvar * 100, 4),
            "budget_limit_pct":   MAX_CVAR_BUDGET * 100,
            "budget_ok":          budget_ok,
            "flag":               not budget_ok,
        }

    except Exception as e:
        return {"budget_ok": True, "flag": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# 6. MASTER RISK DECISION
# ─────────────────────────────────────────────────────────────

def make_risk_decision(ticker:          str,
                       entry_price:     float,
                       sl_price:        float,
                       tp_price:        float,
                       rr_ratio:        float,
                       portfolio_value: float,
                       composite_risk:  float = 50.0,
                       win_rate:        float = 0.50,
                       open_positions:  list[OpenPosition] = None,
                       open_tickers:    list[str] = None) -> RiskDecision:
    """
    Full risk management pipeline. Integrates all five components.

    Parameters
    ----------
    ticker          : str   — stock ticker
    entry_price     : float — technical entry price
    sl_price        : float — stop-loss price
    tp_price        : float — take-profit price
    rr_ratio        : float — reward:risk ratio from technical stage
    portfolio_value : float — total portfolio in same currency as prices
    composite_risk  : float — Stage 1 composite risk score (0–100)
    win_rate        : float — historical win rate of the system (default 0.50)
    open_positions  : list  — existing open trades (for heat & CVaR checks)
    open_tickers    : list  — tickers of open positions (for correlation check)
    """
    open_positions = open_positions or []
    open_tickers   = open_tickers   or []
    flags          = []

    # ── Gate 1: R:R check ────────────────────────────────────
    if rr_ratio < MIN_RR_RATIO:
        return RiskDecision(
            verdict="REJECTED", position_size_shares=0, position_size_pct=0.0,
            risk_amount=0.0, regime_scale=0.0, kelly_fraction=0.0,
            flags=[f"R:R {rr_ratio:.2f} below minimum {MIN_RR_RATIO}"],
            notes="Trade rejected: insufficient reward vs risk.",
        )

    # ── Step 1: Kelly fraction ────────────────────────────────
    raw_kelly = calculate_kelly_fraction(win_rate, rr_ratio)
    if raw_kelly <= 0:
        return RiskDecision(
            verdict="REJECTED", position_size_shares=0, position_size_pct=0.0,
            risk_amount=0.0, regime_scale=0.0, kelly_fraction=0.0,
            flags=["Negative Kelly — edge does not support the trade"],
        )

    # ── Step 2: Regime scale ──────────────────────────────────
    regime_scale   = calculate_regime_scale(composite_risk)
    scaled_kelly   = raw_kelly * regime_scale

    if composite_risk > 70:
        flags.append(f"HIGH REGIME RISK ({composite_risk:.0f}) — position scaled to {regime_scale*100:.0f}%")

    # ── Step 3: Portfolio heat ────────────────────────────────
    heat = calculate_portfolio_heat(open_positions)
    if heat["at_limit"]:
        return RiskDecision(
            verdict="REJECTED", position_size_shares=0, position_size_pct=0.0,
            risk_amount=0.0, regime_scale=regime_scale, kelly_fraction=raw_kelly,
            flags=["Portfolio heat limit reached — no new positions"],
            notes=f"Current heat: {heat['total_heat_pct']:.2f}% / limit {MAX_PORTFOLIO_HEAT*100:.0f}%",
        )

    # ── Step 4: Calculate shares ──────────────────────────────
    risk_per_share = abs(entry_price - sl_price)
    if risk_per_share <= 0:
        return RiskDecision(
            verdict="REJECTED", position_size_shares=0, position_size_pct=0.0,
            risk_amount=0.0, regime_scale=regime_scale, kelly_fraction=raw_kelly,
            flags=["Entry price equals SL price — invalid setup"],
        )

    # Max risk in currency terms
    max_risk_amount  = portfolio_value * scaled_kelly
    raw_shares       = int(max_risk_amount / risk_per_share)

    # Clamp to remaining heat capacity
    max_heat_risk    = portfolio_value * (heat["remaining_capacity"] / 100)
    capped_shares    = int(min(raw_shares * entry_price,
                               max_heat_risk + (raw_shares * risk_per_share)) / entry_price)
    shares           = max(0, min(raw_shares, capped_shares))

    position_value   = shares * entry_price
    position_pct     = (position_value / portfolio_value) * 100
    risk_amount      = shares * risk_per_share

    # ── Step 5: Correlation check ─────────────────────────────
    if open_tickers:
        corr_result = check_correlation(ticker, open_tickers)
        if corr_result.get("flag"):
            corr_pct = corr_result["max_correlation"] * 100
            flags.append(f"HIGH CORRELATION ({corr_pct:.0f}%) with {corr_result['correlated_with']} — position halved")
            shares    = shares // 2
            risk_amount = shares * risk_per_share
            position_pct = (shares * entry_price / portfolio_value) * 100

    # ── Step 6: CVaR budget ───────────────────────────────────
    cvar_check = check_cvar_budget(ticker, shares, portfolio_value, open_positions)
    if cvar_check.get("flag"):
        flags.append(f"CVaR budget breach: {cvar_check['total_cvar_pct']:.3f}% vs limit {MAX_CVAR_BUDGET*100:.1f}% — shares reduced")
        # Reduce until CVaR fits (binary search approximation: halve)
        shares      = shares // 2
        risk_amount = shares * risk_per_share
        position_pct = (shares * entry_price / portfolio_value) * 100

    # ── Final verdict ─────────────────────────────────────────
    if shares <= 0:
        verdict = "REJECTED"
    elif flags:
        verdict = "REDUCED"
    else:
        verdict = "APPROVED"

    return RiskDecision(
        verdict              = verdict,
        position_size_shares = shares,
        position_size_pct    = round(position_pct, 3),
        risk_amount          = round(risk_amount, 2),
        regime_scale         = regime_scale,
        kelly_fraction       = raw_kelly,
        flags                = flags,
        notes                = (
            f"Entry {entry_price:.4f} | SL {sl_price:.4f} | TP {tp_price:.4f} | "
            f"R:R {rr_ratio:.2f} | Regime scale {regime_scale*100:.0f}% | "
            f"Portfolio heat post-trade: "
            f"{heat['total_heat_pct'] + (risk_amount/portfolio_value*100):.2f}%"
        ),
    )