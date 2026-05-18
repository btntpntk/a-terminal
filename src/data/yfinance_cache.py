"""
src/data/yfinance_cache.py
Disk-backed TTL cache for the yfinance Ticker properties used by the scan
pipeline. Without this, every re-scan re-downloads the same ~500 HTTP payloads
from Yahoo (5 calls × 100 tickers for SET100).

Storage layout
--------------
.cache/ticker/<safe-ticker>/<field>.<ext>
  history_1y.parquet      ← stock.history(period="1y")
  financials.parquet      ← stock.financials
  balance_sheet.parquet   ← stock.balance_sheet
  cashflow.parquet        ← stock.cashflow
  info.json               ← dict(stock.info)

Freshness
---------
TTL enforced via file mtime. Defaults:
  PRICE_TTL_SECONDS        = 4h   (history bars change intraday)
  FUNDAMENTALS_TTL_SECONDS = 24h  (financials refresh quarterly)

Safety
------
- Writes are atomic (temp file + os.replace) so a crashed write never
  produces a half-written cache file that poisons the next read.
- Read failures (corrupt file, schema mismatch) silently fall through to a
  fresh fetch — the cache never causes a correctness regression.
- Cache write failures are non-fatal; the call still returns live data.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yfinance as yf


# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

_CACHE_ROOT = Path(__file__).resolve().parents[2] / ".cache" / "ticker"
_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

PRICE_TTL_SECONDS:        int = 4 * 3600
FUNDAMENTALS_TTL_SECONDS: int = 24 * 3600

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


# ─────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────

def _safe_name(ticker: str) -> str:
    """Make a ticker safe to use as a directory name on any filesystem."""
    return _SAFE_RE.sub("_", ticker) or "_unknown"


def _ticker_dir(ticker: str) -> Path:
    d = _CACHE_ROOT / _safe_name(ticker)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_fresh(path: Path, ttl_seconds: int) -> bool:
    try:
        if not path.exists():
            return False
        return (time.time() - path.stat().st_mtime) < ttl_seconds
    except OSError:
        return False


def _atomic_write(path: Path, write_fn: Callable[[Path], None]) -> None:
    """Write via temp + os.replace so partial writes never poison the cache."""
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        write_fn(tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _sanitize_for_json(obj: Any) -> Any:
    """Convert numpy/pandas/NaN values into JSON-safe primitives."""
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    item = getattr(obj, "item", None)
    if callable(item):
        try:
            return _sanitize_for_json(item())
        except Exception:
            pass
    return str(obj)


def _read_parquet_safe(path: Path) -> pd.DataFrame | None:
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _write_parquet_safe(df: pd.DataFrame, path: Path) -> None:
    if df is None or df.empty:
        return
    try:
        _atomic_write(path, lambda tmp: df.to_parquet(tmp))
    except Exception:
        pass  # cache write failure is non-critical


def _read_json_safe(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _write_json_safe(obj: dict, path: Path) -> None:
    if not obj:
        return
    try:
        payload = _sanitize_for_json(obj)
        def _w(tmp: Path) -> None:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f)
        _atomic_write(path, _w)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# Public API — cached fetchers
# ─────────────────────────────────────────────────────────────

def get_history(
    ticker: str,
    period: str = "1y",
    ttl_seconds: int = PRICE_TTL_SECONDS,
) -> pd.DataFrame:
    """Cached `yf.Ticker(ticker).history(period=period)`."""
    path = _ticker_dir(ticker) / f"history_{period}.parquet"
    if _is_fresh(path, ttl_seconds):
        cached = _read_parquet_safe(path)
        if cached is not None and not cached.empty:
            return cached
    df = yf.Ticker(ticker).history(period=period)
    _write_parquet_safe(df, path)
    return df


def get_financials(
    ticker: str,
    ttl_seconds: int = FUNDAMENTALS_TTL_SECONDS,
) -> pd.DataFrame:
    path = _ticker_dir(ticker) / "financials.parquet"
    if _is_fresh(path, ttl_seconds):
        cached = _read_parquet_safe(path)
        if cached is not None:
            return cached
    df = yf.Ticker(ticker).financials
    if df is not None and not df.empty:
        _write_parquet_safe(df, path)
    return df if df is not None else pd.DataFrame()


def get_balance_sheet(
    ticker: str,
    ttl_seconds: int = FUNDAMENTALS_TTL_SECONDS,
) -> pd.DataFrame:
    path = _ticker_dir(ticker) / "balance_sheet.parquet"
    if _is_fresh(path, ttl_seconds):
        cached = _read_parquet_safe(path)
        if cached is not None:
            return cached
    df = yf.Ticker(ticker).balance_sheet
    if df is not None and not df.empty:
        _write_parquet_safe(df, path)
    return df if df is not None else pd.DataFrame()


def get_cashflow(
    ticker: str,
    ttl_seconds: int = FUNDAMENTALS_TTL_SECONDS,
) -> pd.DataFrame:
    path = _ticker_dir(ticker) / "cashflow.parquet"
    if _is_fresh(path, ttl_seconds):
        cached = _read_parquet_safe(path)
        if cached is not None:
            return cached
    df = yf.Ticker(ticker).cashflow
    if df is not None and not df.empty:
        _write_parquet_safe(df, path)
    return df if df is not None else pd.DataFrame()


def get_info(
    ticker: str,
    ttl_seconds: int = FUNDAMENTALS_TTL_SECONDS,
) -> dict:
    """Cached `dict(yf.Ticker(ticker).info)` — the slowest single yfinance endpoint."""
    path = _ticker_dir(ticker) / "info.json"
    if _is_fresh(path, ttl_seconds):
        cached = _read_json_safe(path)
        if cached:
            return cached
    info = dict(yf.Ticker(ticker).info)
    if info:
        _write_json_safe(info, path)
    return info


# ─────────────────────────────────────────────────────────────
# Cache maintenance
# ─────────────────────────────────────────────────────────────

def clear_all() -> dict:
    """Delete every cached ticker file. Returns counts for the admin endpoint."""
    files = 0
    dirs  = 0
    if _CACHE_ROOT.exists():
        for p in _CACHE_ROOT.rglob("*"):
            if p.is_file():
                try:
                    p.unlink()
                    files += 1
                except OSError:
                    pass
        for p in sorted(_CACHE_ROOT.rglob("*"), reverse=True):
            if p.is_dir():
                try:
                    p.rmdir()
                    dirs += 1
                except OSError:
                    pass
    return {"files_removed": files, "dirs_removed": dirs}


def clear_ticker(ticker: str) -> int:
    """Remove every cached file for one ticker. Returns file count removed."""
    d = _CACHE_ROOT / _safe_name(ticker)
    n = 0
    if d.exists():
        for p in d.iterdir():
            if p.is_file():
                try:
                    p.unlink()
                    n += 1
                except OSError:
                    pass
        try:
            d.rmdir()
        except OSError:
            pass
    return n
