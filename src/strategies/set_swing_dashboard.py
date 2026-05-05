"""
SET Swing Dashboard Strategy (7-Star Confluence Scorer).

Translates the 7-star confluence dashboard from PineScript.
Scores seven independent sub-signals and goes long when the score >= min_stars.

Sub-signals:
  1. Weinstein Stage 2: close > MA200 AND MA200 trending up AND close > MA150
  2. Minervini (6+/8): Minervini template score >= 6
  3. Hurst Trending: EMA-smoothed Hurst exponent > 0.52
  4. PP Supertrend Long: pivot-point Supertrend direction = +1
  5. LaRSI Good Zone: 0.20 < LaRSI < 0.85 (not oversold, not overbought)
  6. Chandelier Long: Chandelier Exit direction = +1
  7. WVF Calm: WVF < 15 (no fear spike / panic environment)

Conditions 4, 6, 7 use OHLCV when available; close-only fallbacks are provided.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtesting.interfaces import TradingStrategy
from ._ohlcv import load_ohlcv, wilder_atr

# ── Re-use helpers from sibling modules ──────────────────────────────────────
from .pivot_point_supertrend import _pp_supertrend_trend, _pivot_series  # noqa: F401
from .laguerre_rsi import _laguerre_rsi
from .hurst_choppiness import _hurst_rs
from .chandelier_exit import _chandelier_direction


def _minervini_score(col: pd.Series) -> pd.Series:
    ma50  = col.rolling(50).mean()
    ma150 = col.rolling(150).mean()
    ma200 = col.rolling(200).mean()
    h52   = col.rolling(252).max()
    l52   = col.rolling(252).min()

    return (
        ((col > ma150) & (col > ma200)).astype(int) +
        (ma150 > ma200).astype(int) +
        (ma200 > ma200.shift(25)).astype(int) +
        ((ma50 > ma150) & (ma50 > ma200)).astype(int) +
        (col > ma50).astype(int) +
        (col >= l52 * 1.25).astype(int) +
        (col >= h52 * 0.75).astype(int) +
        (ma200 > ma200.shift(1)).astype(int)
    )


class SETSwingDashboardStrategy(TradingStrategy):
    """
    Long when confluence score >= min_stars (default 5 out of 7).
    Each sub-signal contributes 1 point.
    """
    name = "SET Swing Dashboard"
    supports_short = False

    def __init__(
        self,
        min_stars: int = 5,
        hurst_period: int = 100,
        hurst_smooth: int = 5,
        hurst_thresh: float = 0.52,
        prd: int = 2,
        factor: float = 3.0,
        atr_period: int = 10,
        ce_period: int = 22,
        ce_mult: float = 3.0,
        larsi_gamma: float = 0.6,
        wvf_period: int = 22,
        wvf_calm_thresh: float = 15.0,
    ):
        self.min_stars = min_stars
        self.hurst_period = hurst_period
        self.hurst_smooth = hurst_smooth
        self.hurst_thresh = hurst_thresh
        self.prd = prd
        self.factor = factor
        self.atr_period = atr_period
        self.ce_period = ce_period
        self.ce_mult = ce_mult
        self.larsi_gamma = larsi_gamma
        self.wvf_period = wvf_period
        self.wvf_calm_thresh = wvf_calm_thresh

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        start = prices.index[0].strftime("%Y-%m-%d")
        end   = prices.index[-1].strftime("%Y-%m-%d")

        for ticker in prices.columns:
            col = prices[ticker]
            if col.dropna().empty:
                continue

            ohlcv = load_ohlcv(ticker, start, end)
            have_ohlcv = not ohlcv.empty

            if have_ohlcv:
                ohlcv = ohlcv.reindex(prices.index, method="ffill").dropna(subset=["close"])
                h = ohlcv["high"]
                l = ohlcv["low"]
                c = ohlcv["close"]
            else:
                h = l = c = col

            # ── Sub-signal 1: Weinstein Stage 2 ──────────────────────────────
            ma150 = col.rolling(150).mean()
            ma200 = col.rolling(200).mean()
            stage2 = ((col > ma200) & (ma200 > ma200.shift(10)) & (col > ma150)).fillna(False)

            # ── Sub-signal 2: Minervini 6+/8 ─────────────────────────────────
            minervini = (_minervini_score(col) >= 6).fillna(False)

            # ── Sub-signal 3: Hurst Trending ──────────────────────────────────
            hurst_raw = _hurst_rs(col, self.hurst_period).fillna(0.5)
            hurst_s   = hurst_raw.ewm(span=self.hurst_smooth, adjust=False).mean()
            hurst_ok  = (hurst_s > self.hurst_thresh).fillna(False)

            # ── Sub-signal 4: PP Supertrend Long ─────────────────────────────
            pp_trend = _pp_supertrend_trend(h, l, c, self.prd, self.factor, self.atr_period)
            ppst_long = (pp_trend.reindex(prices.index).ffill().fillna(1.0) == 1.0)

            # ── Sub-signal 5: LaRSI good zone ────────────────────────────────
            larsi = _laguerre_rsi(col.to_frame(), self.larsi_gamma).iloc[:, 0]
            larsi_good = ((larsi > 0.20) & (larsi < 0.85)).fillna(False)

            # ── Sub-signal 6: Chandelier Long ────────────────────────────────
            ce_dir = _chandelier_direction(h, l, c, self.ce_period, self.ce_mult, 0.25)
            chand_long = (ce_dir.reindex(prices.index).ffill().fillna(1.0) == 1.0)

            # ── Sub-signal 7: WVF Calm ────────────────────────────────────────
            lo_src = l if have_ohlcv else col
            hc22   = col.rolling(self.wvf_period).max()
            wvf    = (hc22 - lo_src.reindex(col.index)) / hc22.replace(0.0, np.nan) * 100.0
            wvf_calm = (wvf < self.wvf_calm_thresh).fillna(True)

            # ── Confluence score ──────────────────────────────────────────────
            score = (
                stage2.astype(int) + minervini.astype(int) + hurst_ok.astype(int) +
                ppst_long.astype(int) + larsi_good.astype(int) +
                chand_long.astype(int) + wvf_calm.astype(int)
            )

            signals[ticker] = (score >= self.min_stars).astype(float).fillna(0.0)

        return signals
