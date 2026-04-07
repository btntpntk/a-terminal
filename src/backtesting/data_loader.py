# src/backtesting/data_loader.py
"""
Price data loader with file-based caching.
Cache lives in .cache/prices/<ticker>_<period>.parquet (TTL = 1 day).
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "prices"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_TTL_SECONDS = 86_400  # 1 day


def _cache_path(key: str) -> Path:
    safe = hashlib.md5(key.encode()).hexdigest()
    return _CACHE_DIR / f"{safe}.parquet"


def _is_fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < _TTL_SECONDS


def load_prices(
    tickers: list[str],
    period_years: int = 3,
    extra_tickers: list[str] | None = None,
) -> pd.DataFrame:
    """
    Download adjusted close prices for `tickers` (+ any extra_tickers).
    Returns a DataFrame: DatetimeIndex × ticker columns, forward-filled.
    """
    all_tickers = list(dict.fromkeys(tickers + (extra_tickers or [])))
    cache_key = f"{'_'.join(sorted(all_tickers))}_{period_years}y"
    cp = _cache_path(cache_key)

    if _is_fresh(cp):
        return pd.read_parquet(cp)

    period = f"{period_years}y"
    raw = yf.download(
        all_tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        multi_level_index=len(all_tickers) > 1,
    )

    if raw.empty:
        raise ValueError(f"No price data returned for {all_tickers}")

    # Extract close prices
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw[["Close"]].rename(columns={"Close": all_tickers[0]})

    # Drop rows where ALL are NaN, then forward-fill
    closes = closes.dropna(how="all").ffill()
    closes.index = pd.to_datetime(closes.index)

    closes.to_parquet(cp)
    return closes
