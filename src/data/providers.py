import yfinance as yf
import pandas as pd
import numpy as np


def _enrich_info(info: dict, history: pd.DataFrame) -> dict:
    """
    Fill gaps in ticker_info that yfinance commonly omits for non-US tickers
    (.BK, .HK, .SI, etc.) so downstream WACC / beta calculations always have
    a usable value.

    Fields injected if missing or zero:
      marketCap  — computed from sharesOutstanding × current price
      beta       — computed from 1Y daily returns vs SPY (global risk proxy)
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
            spy_hist = yf.Ticker("SPY").history(period="1y")["Close"]
            asset_ret = history["Close"].pct_change().dropna()
            spy_ret   = spy_hist.pct_change().dropna()
            combined  = pd.concat([asset_ret, spy_ret], axis=1).dropna()
            if len(combined) >= 30:
                cov_mat = np.cov(combined.iloc[:, 0], combined.iloc[:, 1])
                beta_spy = float(np.clip(cov_mat[0, 1] / cov_mat[1, 1], -1.0, 4.0))
                info['beta_vs_spy'] = round(beta_spy, 4)
    except Exception:
        pass   # non-critical enrichment — silently skip

    return info


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
