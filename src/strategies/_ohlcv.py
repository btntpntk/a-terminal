"""
Shared OHLCV loader for strategies that need high/low/volume data.
Uses the same .cache/prices/ parquet cache as data_loader and VADER.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pandas as pd

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "prices"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_TTL = 86_400  # 1 day


def load_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    Download full OHLCV for *ticker* between *start* and *end* (YYYY-MM-DD).
    Returns DataFrame with columns [open, high, low, close, volume], DatetimeIndex.
    Returns empty DataFrame on any failure — callers must handle this case.
    """
    import yfinance as yf

    key = f"ohlcv_{ticker}_{start}_{end}"
    cp = _CACHE_DIR / f"{hashlib.md5(key.encode()).hexdigest()}.parquet"

    if cp.exists() and (time.time() - cp.stat().st_mtime) < _TTL:
        return pd.read_parquet(cp)

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
        if raw.empty:
            return pd.DataFrame()

        df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df.to_parquet(cp)
        return df

    except Exception:
        return pd.DataFrame()


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """ATR using Wilder's smoothing (matches PineScript ta.atr)."""
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
