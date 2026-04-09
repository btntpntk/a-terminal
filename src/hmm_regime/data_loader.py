"""
src/hmm_regime/data_loader.py

Downloads raw price and VIX data for the HMM regime detector.
Works for any ticker (US, EM, crypto, indices).

Returns a DataFrame with columns:
  spy_close  — target ticker adjusted close
  vix        — ^VIX level (used as volatility feature)

Lookahead: raw series only — all shift/lag ops are in features.py.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "hmm"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_TTL_SECONDS = 86_400  # 1 day


def _cache_path(key: str) -> Path:
    safe = hashlib.md5(key.encode()).hexdigest()
    return _CACHE_DIR / f"{safe}.parquet"


def _is_fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < _TTL_SECONDS


def _download_close(ticker: str, start: str, end: str) -> pd.Series | None:
    """Download adjusted close for a single ticker. Returns None if unavailable."""
    try:
        raw = yf.download(
            ticker,
            start=start,
            end=end,
            interval="1d",
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
        )
    except Exception as exc:
        raise ValueError(f"Download failed for {ticker}: {exc}") from exc

    if raw.empty or "Close" not in raw.columns:
        return None
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    s = close.dropna().copy()
    if s.empty:
        return None
    s.name = ticker
    s.index = pd.to_datetime(s.index)
    return s


def load_raw_data(
    spy_ticker: str = "SPY",
    start: str = "2000-01-01",
    end: str | None = None,
) -> pd.DataFrame:
    """
    Load aligned daily price and VIX data.

    Parameters
    ----------
    spy_ticker : str
        Any equity, ETF, index, or crypto ticker supported by yfinance.
    start : str
        ISO start date (inclusive).
    end : str | None
        ISO end date. Defaults to today.

    Returns
    -------
    pd.DataFrame
        DatetimeIndex, columns: spy_close, vix
    """
    if end is None:
        end = pd.Timestamp.today().strftime("%Y-%m-%d")

    cache_key = f"hmm_v3_{spy_ticker}_{start}_{end}"
    cp = _cache_path(cache_key)

    if _is_fresh(cp):
        return pd.read_parquet(cp)

    # ── Download ──────────────────────────────────────────────────────────────
    price_s = _download_close(spy_ticker, start, end)
    if price_s is None:
        raise ValueError(f"No price data for {spy_ticker} [{start}:{end}]")

    vix_s = _download_close("^VIX", start, end)
    if vix_s is None:
        raise ValueError(f"No VIX data for [{start}:{end}]")

    # Align on target ticker's trading days, forward-fill VIX gaps
    df = (
        pd.concat([price_s.rename("spy_close"), vix_s.rename("vix")], axis=1)
        .sort_index()
        .ffill()
        .dropna(subset=["spy_close"])
    )

    # Drop rows where VIX is still NaN (before VIX history starts ~1990)
    df = df.dropna()

    if df.empty:
        raise ValueError(
            f"No overlapping data for {spy_ticker} and ^VIX in [{start}:{end}]. "
            "Try a later start date."
        )

    df.to_parquet(cp)
    return df
