"""
src/hmm_regime/features.py

Build the 3-feature observation matrix for the HMM regime detector.

Features (all lookahead-free — window covers only t-1 and earlier):
  ret_5d   — 5-day cumulative log return of the target ticker
  rvol_21d — 21-day annualized realized volatility of the target ticker
  vix      — VIX level as of previous close

CRITICAL LOOKAHEAD RULE
-----------------------
All rolling ops apply .shift(1) before rolling, so at time t the
window covers [t-N-1 … t-1] — strictly past data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Construct the 3-feature observation matrix from price + VIX data.

    Parameters
    ----------
    df : pd.DataFrame
        Raw data from data_loader.load_raw_data().
        Required columns: spy_close, vix

    Returns
    -------
    pd.DataFrame
        Columns: ret_5d, rvol_21d, vix
        All values at index t use only data from t-1 or earlier.
    """
    out = pd.DataFrame(index=df.index)

    log_ret = np.log(df["spy_close"] / df["spy_close"].shift(1))

    # 5-day cumulative log return (window: t-6 … t-1)
    out["ret_5d"] = (
        log_ret
        .shift(1)
        .rolling(5, min_periods=5)
        .sum()
    )

    # 21-day realized volatility, annualized (window: t-22 … t-1)
    out["rvol_21d"] = (
        log_ret
        .shift(1)
        .rolling(21, min_periods=21)
        .std()
        * np.sqrt(252)
    )

    # VIX level as of previous close (published after market close)
    out["vix"] = df["vix"].shift(1)

    return out.dropna()
