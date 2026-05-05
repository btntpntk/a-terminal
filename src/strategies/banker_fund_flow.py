"""
Banker Fund Flow Strategy (5-Phase State Machine).

Translates the BFF oscillator from PineScript (blackcat1402 L3 inspired).
Uses a normalized MACD-like oscillator to classify market phases:
  Phase 0 – Neutral   (flat)
  Phase 1 – Entry     (long signal)
  Phase 2 – Increase  (long signal)
  Phase 3 – Exit      (flat/exit)
  Phase 4 – Rebound   (long signal)

Uses close prices only (hlc3 ≈ close approximation).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtesting.interfaces import TradingStrategy

# Phases that produce a long signal
_LONG_PHASES = {1, 2, 4}


def _bff_signals(
    col: pd.Series,
    fast_len: int,
    slow_len: int,
    signal_len: int,
    roc_len: int,
    thresh_up: float,
) -> pd.Series:
    """Run the 5-phase BFF state machine for a single price series."""
    src = col.values.astype(float)
    n = len(src)

    # EMA helpers (pandas ewm)
    s = pd.Series(src, index=col.index)
    ema_f = s.ewm(span=fast_len, adjust=False).mean().values
    ema_s = s.ewm(span=slow_len, adjust=False).mean().values
    diff = ema_f - ema_s

    d_series = pd.Series(diff, index=col.index)
    sig_line = d_series.ewm(span=signal_len, adjust=False).mean().values
    hist = diff - sig_line

    # Normalise by rolling stdev of source
    stdev = s.rolling(slow_len, min_periods=slow_len // 2).std(ddof=0).values
    denom = np.where(stdev > 0, stdev, 1e-10)
    diff_norm = diff / denom
    sig_norm = sig_line / denom
    hist_norm = hist / denom

    # 3-bar ROC of fast EMA, smoothed
    roc = pd.Series(ema_f, index=col.index).pct_change(roc_len).values * 100.0
    mom_smooth = pd.Series(roc, index=col.index).ewm(span=3, adjust=False).mean().values

    result = np.zeros(n)
    phase = 0

    for i in range(1, n):
        dn = diff_norm[i]
        sn = sig_norm[i]
        hn = hist_norm[i]
        mom = mom_smooth[i]

        if np.isnan(dn) or np.isnan(mom):
            result[i] = 1.0 if phase in _LONG_PHASES else 0.0
            continue

        cross_up   = (diff_norm[i] > sig_norm[i]) and (diff_norm[i-1] <= sig_norm[i-1])
        cross_down = (diff_norm[i] < sig_norm[i]) and (diff_norm[i-1] >= sig_norm[i-1])
        diff_above_sig = dn > sn
        hist_rising    = hn > hist_norm[i-1] if not np.isnan(hist_norm[i-1]) else False
        mom_pos   = mom > thresh_up
        mom_weak  = abs(mom) < thresh_up

        # Phase transitions — REBOUND checked before ENTRY
        if cross_up and dn < 0 and phase == 3:
            phase = 4
        elif cross_up and dn < 0:
            phase = 1
        elif diff_above_sig and dn > 0 and hist_rising and mom_pos:
            phase = 2
        elif cross_down and diff_norm[i-1] > 0:
            phase = 3
        elif mom_weak and abs(dn) < 0.1:
            phase = 0
        # else: keep current phase

        result[i] = 1.0 if phase in _LONG_PHASES else 0.0

    return pd.Series(result, index=col.index)


class BankerFundFlowStrategy(TradingStrategy):
    """
    Long during Entry (1), Increase (2), and Rebound (4) phases.
    Flat during Neutral (0) and Exit (3) phases.
    """
    name = "Banker Fund Flow"
    supports_short = False

    def __init__(
        self,
        fast_len: int = 5,
        slow_len: int = 20,
        signal_len: int = 9,
        roc_len: int = 3,
        thresh_up: float = 0.002,
    ):
        self.fast_len = fast_len
        self.slow_len = slow_len
        self.signal_len = signal_len
        self.roc_len = roc_len
        self.thresh_up = thresh_up

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        for ticker in prices.columns:
            col = prices[ticker].dropna()
            if len(col) < self.slow_len + self.signal_len:
                continue
            sig = _bff_signals(
                col,
                self.fast_len,
                self.slow_len,
                self.signal_len,
                self.roc_len,
                self.thresh_up,
            )
            signals[ticker] = sig.reindex(prices.index).fillna(0.0)

        return signals
