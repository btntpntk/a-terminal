from __future__ import annotations

import yfinance as yf
import pandas as pd
import numpy as np


def _enrich_info(
    info: dict,
    history: pd.DataFrame,
    spy_history: pd.Series | pd.DataFrame | None = None,
) -> dict:
    """
    Fill gaps in ticker_info that yfinance commonly omits for non-US tickers
    (.BK, .HK, .SI, etc.) so downstream WACC / beta calculations always have
    a usable value.

    Fields injected if missing or zero:
      marketCap  — computed from sharesOutstanding × current price
      beta       — computed from 1Y daily returns vs SPY (global risk proxy)

    Parameters
    ----------
    spy_history : optional
        Pre-fetched SPY Close series (or DataFrame). Pass this when running
        a batch of tickers so the SPY fetch happens once instead of once per
        ticker. When None, falls back to fetching from yfinance.
    """
    # ── Market cap ────────────────────────────────────────────────────────────
    if not info.get('marketCap') or float(info.get('marketCap', 0)) == 0:
        shares = float(info.get('sharesOutstanding') or
                       info.get('impliedSharesOutstanding') or 0)
        price  = float(info.get('currentPrice') or
                       info.get('regularMarketPrice') or
                       info.get('previousClose') or
                       (history['Close'].iloc[-1] if not history.empty else 0))
        computed_mc = shares * price
        if computed_mc > 0:
            info['marketCap'] = computed_mc

    # ── Beta vs SPY (global benchmark) ───────────────────────────────────────
    # yfinance beta for .BK tickers is measured vs SET50, not S&P 500.
    # We compute both and store the SPY beta under 'beta_vs_spy' while
    # preserving the original local 'beta' for SET-relative risk display.
    try:
        if not history.empty and len(history) >= 60:
            if spy_history is None:
                # Route the fallback fetch through the disk cache so callers
                # that don't pre-fetch (e.g. the debug endpoint) still avoid
                # the network on repeat hits.
                from src.data.yfinance_cache import get_history as _get_history
                spy_close = _get_history("SPY", period="1y")["Close"]
            elif isinstance(spy_history, pd.DataFrame):
                spy_close = spy_history["Close"]
            else:
                spy_close = spy_history
            asset_ret = history["Close"].pct_change().dropna()
            spy_ret   = spy_close.pct_change().dropna()
            combined  = pd.concat([asset_ret, spy_ret], axis=1).dropna()
            if len(combined) >= 30:
                cov_mat = np.cov(combined.iloc[:, 0], combined.iloc[:, 1])
                beta_spy = float(np.clip(cov_mat[0, 1] / cov_mat[1, 1], -1.0, 4.0))
                info['beta_vs_spy'] = round(beta_spy, 4)
    except Exception:
        pass   # non-critical enrichment — silently skip

    return info


def fetch_spy_close_1y() -> pd.Series:
    """
    Fetch 1Y SPY Close series. Intended to be called once per scan and
    passed into `_enrich_info` for every ticker so the SPY round-trip is
    not repeated N times.

    Routes through the disk cache so consecutive scans within the price
    TTL (default 4h) skip the network entirely.
    """
    from src.data.yfinance_cache import get_history
    return get_history("SPY", period="1y")["Close"]


async def fetch_all_data(ticker: str) -> dict:
    """
    Institutional data aggregator.
    Returns raw ticker objects and processed returns for quantitative analysis.
    """
    stock   = yf.Ticker(ticker)
    history = stock.history(period="3y")

    if history.empty:
        raise ValueError(f"No price history found for ticker: {ticker}")

    returns = history['Close'].pct_change().dropna()

    # Enrich info dict with computed fields missing for non-US tickers
    info = dict(stock.info)   # copy so we don't mutate the cached object
    info = _enrich_info(info, history)

    return {
        "ticker":       ticker,
        "raw_stock_obj": stock,
        "prices":       history,
        "returns":      returns,
        "info":         info,
        "metrics": {
            "fwd_pe":          info.get("forwardPE"),
            "debt_to_equity":  info.get("debtToEquity"),
            "market_cap":      info.get("marketCap"),
            "beta":            info.get("beta"),
            "beta_vs_spy":     info.get("beta_vs_spy"),
        },
    }
