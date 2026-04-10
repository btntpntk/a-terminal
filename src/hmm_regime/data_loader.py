import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "hmm"
_TTL = timedelta(days=1)


def _cache_path(ticker: str, start: str) -> Path:
    key = f"{ticker}:{start}"
    h = hashlib.md5(key.encode()).hexdigest()
    return _CACHE_DIR / f"{h}.parquet"


def load_prices(ticker: str, start: str) -> pd.DataFrame:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(ticker, start)

    if path.exists():
        age = datetime.utcnow() - datetime.utcfromtimestamp(path.stat().st_mtime)
        if age < _TTL:
            return pd.read_parquet(path)

    df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No price data returned for {ticker}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Close"]].copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    df.to_parquet(path)
    return df
