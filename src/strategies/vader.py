"""
VADER — Volatility-Adaptive Dual-Edge Regime strategy.

Three-regime architecture:
  COMPRESSION    → breakout signal (vol expanding from low base)
  TRENDING       → vol-normalised momentum signal (clear directional trend)
  MEAN_REVERSION → cross-timeframe z-score signal (high vol, no trend)
  TRANSITION     → no new entries (ambiguous regime)

Each regime runs independent signal logic and adaptive exit logic.
A composite VADER score gates all entries — signal + regime confidence
+ volume quality + liquidity must all be present simultaneously.

Portfolio Optimizer note
------------------------
VADER manages its own exit logic (chandelier trail, regime change, z-score
normalisation).  The Normal walk-forward engine respects VADER's signals but
adds its own stop-loss on top.  Recommended optimizers:

  Single-ticker mode : EqualWeightOptimizer  (full allocation to one asset)
  Multi-ticker mode  : InverseVolatilityOptimizer  (size by reciprocal σ,
                       which naturally concentrates in calmer assets —
                       aligns with VADER's VCI-based regime logic)

EqualWeightOptimizer is the safest default; choose one in the UI.

Integration
-----------
Inherits TradingStrategy so it plugs into the existing engine unchanged.
generate_signals() fetches OHLCV internally (same .cache/prices/ parquet
as data_loader), calls precompute(), then runs the stateful bar-by-bar
loop using compute_buy_signal / entry_metadata / compute_sell_signal.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.backtesting.interfaces import TradingStrategy

# ─────────────────────────────────────────────────────────────────────────────
# OHLCV loader  (shared .cache/prices/ with data_loader)
# ─────────────────────────────────────────────────────────────────────────────

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "prices"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_TTL = 86_400  # 1 day


def _load_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    Download full OHLCV for *ticker* between *start* and *end* (YYYY-MM-DD).
    Returns DataFrame columns [open, high, low, close, volume], DatetimeIndex.
    Returns empty DataFrame on any failure — caller uses close-only fallback.
    """
    import yfinance as yf

    key = f"ohlcv_{ticker}_{start}_{end}"
    cp  = _CACHE_DIR / f"{hashlib.md5(key.encode()).hexdigest()}.parquet"

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
        df.index   = pd.to_datetime(df.index)
        df = df.dropna(how="all").ffill()
        df.to_parquet(cp)
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Parameters dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VADERParams:
    # ── Regime detector ──────────────────────────────────────────────────────
    atr_short_period: int            = 7
    atr_long_period: int             = 50
    bb_period: int                   = 20
    bb_std: float                    = 2.0
    bb_lookback: int                 = 126
    vci_compression_threshold: float = 0.25   # VCI below → COMPRESSION
    vci_expansion_threshold: float   = 0.55   # VCI above → TRENDING or MR
    ema_fast: int                    = 21
    ema_slow: int                    = 55
    ema_trend: int                   = 200
    slope_lookback: int              = 10

    # ── Trending signal ───────────────────────────────────────────────────────
    mom_fast: int                    = 10
    mom_slow: int                    = 30
    vol_window: int                  = 20
    kc_period: int                   = 20
    kc_mult: float                   = 1.5

    # ── Compression signal ────────────────────────────────────────────────────
    don_period: int                  = 20
    vol_ma_period: int               = 20
    vol_surge_mult: float            = 1.5
    sq_period: int                   = 20

    # ── Mean-reversion signal ─────────────────────────────────────────────────
    z_short: int                     = 5
    z_medium: int                    = 10
    z_long: int                      = 20
    z_thresh: float                  = 1.5    # entry: all z-scores below -z_thresh
    z_exit_thresh: float             = 0.5    # exit:  z-scores above -z_exit_thresh
    rsi_period: int                  = 7
    rsi_threshold: float             = 30.0

    # ── Composite score ───────────────────────────────────────────────────────
    w_sig: float                     = 0.40
    w_conf: float                    = 0.30
    w_vol: float                     = 0.20
    w_liq: float                     = 0.10
    score_threshold: float           = 0.55

    # ── Exit parameters ───────────────────────────────────────────────────────
    chandelier_period: int           = 22
    chandelier_mult: float           = 3.0
    tp_range_mult: float             = 1.0   # compression: TP = entry + range × mult
    sl_range_mult: float             = 0.5   # compression: SL = entry - range × mult
    max_holding_days: int            = 20
    max_stop_loss_pct: float         = 0.07  # hard floor for MR trades


# ─────────────────────────────────────────────────────────────────────────────
# Indicator helper functions
# ─────────────────────────────────────────────────────────────────────────────

def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Average True Range — Wilder EWM smoothing."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def _rsi(close: pd.Series, period: int) -> pd.Series:
    """RSI — Wilder EWM smoothing."""
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(alpha=1.0 / period, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1.0 / period, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _percentile_rank(series: pd.Series, window: int) -> pd.Series:
    """Rolling percentile rank of each value within its preceding window, returns [0, 1]."""
    def _rank(arr: np.ndarray) -> float:
        return float((arr[:-1] < arr[-1]).mean()) if len(arr) > 1 else 0.5
    return series.rolling(window, min_periods=window).apply(_rank, raw=True)


def _keltner(df: pd.DataFrame, period: int, mult: float):
    """Keltner channel — returns (mid, upper, lower)."""
    atr_kc = _atr(df, period)
    mid    = df["close"].ewm(span=period, adjust=False).mean()
    return mid, mid + mult * atr_kc, mid - mult * atr_kc


# ─────────────────────────────────────────────────────────────────────────────
# VADER Strategy
# ─────────────────────────────────────────────────────────────────────────────

class VADERStrategy(TradingStrategy):
    """
    VADER — Volatility-Adaptive Dual-Edge Regime.

    Implements TradingStrategy so it plugs into the existing Normal and MC
    walk-forward engines without modification.

    The class exposes three public methods that mirror the reference interface:
      precompute(df)                   → indicator DataFrame
      compute_buy_signal(df, i)        → int  (1 = enter, 0 = no entry)
      compute_sell_signal(pos, df, i)  → (int, str)  (1 = exit, 0 = hold)
      entry_metadata(df, i)            → dict  (position init fields)

    generate_signals() wires these together into the signal DataFrame the
    engine expects, fetching OHLCV internally.
    """

    name           = "VADER"
    supports_short = False

    def __init__(self, params: Optional[VADERParams] = None, **kwargs):
        # Accept either a VADERParams instance or loose keyword overrides
        # so the engine can instantiate VADERStrategy() with no args.
        self.p = params if params is not None else VADERParams(**{
            k: v for k, v in kwargs.items() if hasattr(VADERParams, k)
        })
        self._indicators: Optional[pd.DataFrame] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Pre-compute all indicators once on a full OHLCV DataFrame
    # ─────────────────────────────────────────────────────────────────────────

    def precompute(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all VADER indicators on a full OHLCV DataFrame.
        df must have columns: open, high, low, close, volume.
        Returns a new DataFrame (original unchanged) with all indicator columns.
        All operations are causal — bar i uses only data ≤ i.
        """
        p  = self.p
        df = df.copy()

        close  = df["close"]
        high   = df["high"]
        low    = df["low"]
        volume = df["volume"]

        # ── ATR (short + long + exit) ─────────────────────────────────────────
        df["atr_short"] = _atr(df, p.atr_short_period)
        df["atr_long"]  = _atr(df, p.atr_long_period)
        df["atr_exit"]  = _atr(df, 14)

        # ── Bollinger Bands ───────────────────────────────────────────────────
        bb_mid         = close.rolling(p.bb_period).mean()
        bb_std_s       = close.rolling(p.bb_period).std(ddof=1)
        df["bb_upper"] = bb_mid + p.bb_std * bb_std_s
        df["bb_lower"] = bb_mid - p.bb_std * bb_std_s
        df["bb_mid"]   = bb_mid
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid.replace(0, np.nan)

        # ── VCI (Volatility Compression Index) ───────────────────────────────
        atr_ratio  = df["atr_short"] / df["atr_long"].replace(0, np.nan)
        bb_pct     = _percentile_rank(df["bb_width"].fillna(0), p.bb_lookback)
        df["VCI"]  = (0.5 * atr_ratio + 0.5 * bb_pct).clip(0, 1)

        # ── EMAs + Trend Slope ────────────────────────────────────────────────
        df["ema_fast"]    = close.ewm(span=p.ema_fast,  adjust=False).mean()
        df["ema_slow"]    = close.ewm(span=p.ema_slow,  adjust=False).mean()
        df["ema_trend"]   = close.ewm(span=p.ema_trend, adjust=False).mean()
        df["trend_slope"] = (
            (df["ema_trend"] - df["ema_trend"].shift(p.slope_lookback))
            / df["ema_trend"].replace(0, np.nan)
        )

        # TSF: +1 uptrend, −1 downtrend, 0 no trend
        df["TSF"] = np.where(
            (df["ema_fast"] > df["ema_slow"]) & (df["trend_slope"] > 0),  1,
            np.where(
            (df["ema_fast"] < df["ema_slow"]) & (df["trend_slope"] < 0), -1, 0)
        ).astype(float)

        # ── Regime ───────────────────────────────────────────────────────────
        df["regime"] = df.apply(
            lambda r: self._classify_regime(r["VCI"], r["TSF"]), axis=1
        )

        # ── Trending signal components ────────────────────────────────────────
        ret                 = close.pct_change()
        rolling_std_v       = ret.rolling(p.vol_window).std(ddof=1).replace(0, np.nan)
        df["norm_ret_fast"] = ret.rolling(p.mom_fast).sum() / rolling_std_v
        df["norm_ret_slow"] = ret.rolling(p.mom_slow).sum() / rolling_std_v
        df["mom_accel"]     = df["norm_ret_fast"] - df["norm_ret_fast"].shift(3)
        kc_mid, _, _        = _keltner(df, p.kc_period, p.kc_mult)
        df["kc_mid"]        = kc_mid
        df["price_above_kc"]= (close > kc_mid).astype(float)

        # ── Compression signal components ─────────────────────────────────────
        df["don_high"]  = high.rolling(p.don_period).max()
        df["don_low"]   = low.rolling(p.don_period).min()
        df["vol_ma"]    = volume.rolling(p.vol_ma_period).mean()
        df["vol_surge"] = volume / df["vol_ma"].replace(0, np.nan)
        don_mid         = (df["don_high"] + df["don_low"]) / 2.0
        df["sq_mom"]    = close - don_mid

        # ── Mean-reversion signal components ──────────────────────────────────
        for win, col in [(p.z_short, "z_s"), (p.z_medium, "z_m"), (p.z_long, "z_l")]:
            mu       = close.rolling(win).mean()
            sd       = close.rolling(win).std(ddof=1).replace(0, np.nan)
            df[col]  = (close - mu) / sd
        df["rsi"]    = _rsi(close, p.rsi_period)
        bar_range    = (high - low).replace(0, np.nan)
        df["hammer"] = (
            (close > df["open"]) & ((close - low) / bar_range > 0.6)
        ).astype(float)

        self._indicators = df
        return df

    # ─────────────────────────────────────────────────────────────────────────
    # Regime classifier
    # ─────────────────────────────────────────────────────────────────────────

    def _classify_regime(self, vci: float, tsf: float) -> str:
        p = self.p
        if pd.isna(vci):
            return "TRANSITION"
        if vci < p.vci_compression_threshold:
            return "COMPRESSION"
        if vci > p.vci_expansion_threshold:
            return "TRENDING" if abs(tsf) == 1 else "MEAN_REVERSION"
        return "TRANSITION"

    # ─────────────────────────────────────────────────────────────────────────
    # Buy signal
    # ─────────────────────────────────────────────────────────────────────────

    def compute_buy_signal(self, df: pd.DataFrame, i: int) -> int:
        """
        Returns 1 if a buy signal fires at bar i, else 0.
        df must be the indicators DataFrame returned by precompute().
        """
        p = self.p
        if i < max(p.ema_trend, p.bb_lookback, p.atr_long_period) + 5:
            return 0  # warmup guard

        r      = df.iloc[i]
        regime = r["regime"]

        if regime == "TRANSITION":
            return 0

        raw = False

        if regime == "TRENDING":
            raw = bool(
                (r["norm_ret_fast"] > r["norm_ret_slow"])
                and (r["mom_accel"] > 0)
                and (r["price_above_kc"] == 1)
                and (r["TSF"] == 1)
            )

        elif regime == "COMPRESSION":
            prev_don_high = df["don_high"].iloc[i - 1] if i > 0 else np.nan
            raw = bool(
                not np.isnan(prev_don_high)
                and (r["close"] > prev_don_high)
                and (r["vol_surge"] > p.vol_surge_mult)
                and (r["sq_mom"] > df["sq_mom"].iloc[i - 1])
                and (r["VCI"] < p.vci_compression_threshold)
            )

        elif regime == "MEAN_REVERSION":
            raw = bool(
                (r["z_s"] < -p.z_thresh)
                and (r["z_m"] < -p.z_thresh)
                and (r["z_l"] < -p.z_thresh)
                and (r["rsi"] < p.rsi_threshold)
                and (r["hammer"] == 1)
            )

        if not raw:
            return 0

        score = self._vader_score(r, regime)
        return 1 if score >= p.score_threshold else 0

    # ─────────────────────────────────────────────────────────────────────────
    # VADER composite score
    # ─────────────────────────────────────────────────────────────────────────

    def _vader_score(self, r: pd.Series, regime: str) -> float:
        """Composite VADER score in [0, 1]."""
        p = self.p

        if regime == "TRENDING":
            sig_s = float(np.clip((r["norm_ret_fast"] - r["norm_ret_slow"]) / 2.0, 0, 1))
        elif regime == "COMPRESSION":
            sig_s = float(np.clip(r["vol_surge"] - 1.0, 0, 1))
        else:
            sig_s = float(np.clip(abs(r["z_s"] + r["z_m"] + r["z_l"]) / 9.0, 0, 1))

        if regime == "TRENDING":
            reg_c = float(np.clip((r["VCI"] - p.vci_expansion_threshold) / 0.3, 0, 1))
        else:
            reg_c = float(np.clip(1.0 - r["VCI"] / p.vci_compression_threshold, 0, 1))

        vol_q    = float(np.clip(r["vol_surge"] - 0.8, 0, 1))
        hl_ratio = (r["high"] - r["low"]) / r["close"] if r["close"] > 0 else 0.0
        liq_s    = float(np.clip(1.0 - hl_ratio / 0.03, 0, 1))

        return (p.w_sig * sig_s + p.w_conf * reg_c
                + p.w_vol * vol_q + p.w_liq * liq_s)

    # ─────────────────────────────────────────────────────────────────────────
    # Entry metadata
    # ─────────────────────────────────────────────────────────────────────────

    def entry_metadata(self, df: pd.DataFrame, i: int) -> dict:
        """
        Returns dict with sl_price, tp_price, don_range, regime, vader_score.
        Call this when compute_buy_signal returns 1.
        """
        r      = df.iloc[i]
        p      = self.p
        close  = float(r["close"])
        regime = str(r["regime"])

        if regime == "TRENDING":
            window_high = df["close"].iloc[max(0, i - p.chandelier_period): i + 1].max()
            sl  = float(window_high - p.chandelier_mult * r["atr_exit"])
            sl  = min(sl, close * (1.0 - p.max_stop_loss_pct))
            tp  = np.inf

        elif regime == "COMPRESSION":
            don_range = float(r["don_high"] - r["don_low"])
            sl  = float(r["don_high"]) - p.sl_range_mult * don_range
            tp  = float(r["don_high"]) + p.tp_range_mult * don_range

        else:  # MEAN_REVERSION
            sl  = close * (1.0 - p.max_stop_loss_pct)
            tp  = np.inf

        return {
            "entry_price": close,
            "entry_bar":   i,
            "regime":      regime,
            "sl_price":    float(sl),
            "tp_price":    float(tp),
            "don_range":   float(r["don_high"] - r["don_low"]),
            "vader_score": self._vader_score(r, regime),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Sell signal
    # ─────────────────────────────────────────────────────────────────────────

    def compute_sell_signal(
        self,
        position: dict,
        df: pd.DataFrame,
        i: int,
    ) -> tuple[int, str]:
        """
        Returns (1, reason) if position should be closed, else (0, "").
        Mutates position["sl_price"] in-place for the chandelier ratchet.

        SL priority order (non-negotiable):
          1. Hard stop-loss
          2. Regime-specific exit
          3. Hostile regime change
          4. Time exit
        """
        r         = df.iloc[i]
        p         = self.p
        entry_reg = position["regime"]
        close     = float(r["close"])
        bars_held = i - position["entry_bar"]

        # ── PRIORITY 1: hard SL ───────────────────────────────────────────────
        if close <= position["sl_price"]:
            return 1, "STOP_LOSS"

        # ── PRIORITY 2: regime-specific exit ─────────────────────────────────
        if entry_reg == "TRENDING":
            window_high = df["close"].iloc[max(0, i - p.chandelier_period): i + 1].max()
            chan_sl = float(window_high - p.chandelier_mult * r["atr_exit"])
            # Ratchet upward only — never lower the stop
            position["sl_price"] = max(position["sl_price"], chan_sl)
            if r["TSF"] != 1:
                return 1, "TREND_BREAK"

        elif entry_reg == "COMPRESSION":
            if close >= position["tp_price"]:
                return 1, "TAKE_PROFIT"

        elif entry_reg == "MEAN_REVERSION":
            if r["z_s"] > -p.z_exit_thresh and r["z_m"] > -p.z_exit_thresh:
                return 1, "Z_REVERTED"

        # ── PRIORITY 3: hostile regime change ─────────────────────────────────
        cur_regime = str(r["regime"])
        if entry_reg == "TRENDING"       and cur_regime == "MEAN_REVERSION":
            return 1, "REGIME_EXIT"
        if entry_reg == "MEAN_REVERSION" and cur_regime == "TRENDING":
            return 1, "REGIME_EXIT"

        # ── PRIORITY 4: time exit ─────────────────────────────────────────────
        if bars_held >= p.max_holding_days:
            return 1, "TIME_EXIT"

        return 0, ""

    # ─────────────────────────────────────────────────────────────────────────
    # TradingStrategy interface — called by both Normal and MC engines
    # ─────────────────────────────────────────────────────────────────────────

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Fetches OHLCV per ticker, calls precompute(), then runs the stateful
        bar-by-bar loop using compute_buy_signal / entry_metadata /
        compute_sell_signal.  Returns a DataFrame of {0.0, 1.0} signals with
        the same shape as *prices*.
        """
        start_str = prices.index[0].strftime("%Y-%m-%d")
        end_str   = (prices.index[-1] + pd.Timedelta(days=2)).strftime("%Y-%m-%d")

        output = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        for ticker in prices.columns:
            close_col = prices[ticker].dropna()
            if len(close_col) < 50:
                continue

            # ── Build OHLCV DataFrame ─────────────────────────────────────────
            ohlcv = _load_ohlcv(ticker, start_str, end_str)

            if ohlcv.empty or len(ohlcv) < 50:
                # Close-only fallback: neutral volume → vol_surge = 1 always
                idx    = prices.index
                cl     = close_col.reindex(idx).ffill()
                ohlcv  = pd.DataFrame({
                    "open":   cl,
                    "high":   cl,
                    "low":    cl,
                    "close":  cl,
                    "volume": 1.0,
                }, index=idx)
            else:
                ohlcv = ohlcv.reindex(prices.index).ffill().bfill()
                cl    = close_col.reindex(prices.index).ffill()
                ohlcv["close"]  = ohlcv["close"].fillna(cl)
                ohlcv["open"]   = ohlcv["open"].fillna(ohlcv["close"])
                ohlcv["high"]   = ohlcv["high"].fillna(ohlcv["close"])
                ohlcv["low"]    = ohlcv["low"].fillna(ohlcv["close"])
                ohlcv["volume"] = ohlcv["volume"].clip(lower=0).replace(0, np.nan)

            try:
                ind_df = self.precompute(ohlcv)
                sig    = self._run_signal_loop(ind_df)
                output[ticker] = sig.reindex(prices.index).fillna(0.0)
            except Exception:
                output[ticker] = 0.0

        return output

    def _run_signal_loop(self, df: pd.DataFrame) -> pd.Series:
        """
        Bar-by-bar state machine over the precomputed indicator DataFrame.
        Uses compute_buy_signal / entry_metadata / compute_sell_signal exactly.
        """
        n      = len(df)
        signal = np.zeros(n, dtype=float)

        in_pos   = False
        position = {}

        for i in range(n):
            if not in_pos:
                if self.compute_buy_signal(df, i) == 1:
                    position = self.entry_metadata(df, i)
                    in_pos   = True
                    signal[i] = 1.0
            else:
                exit_flag, _ = self.compute_sell_signal(position, df, i)
                if exit_flag:
                    in_pos    = False
                    signal[i] = 0.0
                else:
                    signal[i] = 1.0

        return pd.Series(signal, index=df.index)
