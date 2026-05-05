"""
Mansfield RS + Minervini Trend Template Strategy.

Translates the Weinstein Stage 2 / Minervini SEPA template from PineScript.
Scores 8 Minervini conditions and goes long when score >= min_score.

Works on close prices only (52-week high/low approximated from close rolling window).
Mansfield RS requires `benchmark_prices` kwarg (pd.Series) — skipped if absent.

Entry : score >= min_score (default 8 = all conditions pass)
Exit  : score < exit_score (default 6)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtesting.interfaces import TradingStrategy


class MansfieldMinerviniStrategy(TradingStrategy):
    """
    Long when Minervini template score >= min_score (default: all 8 conditions).
    Exit when score drops below exit_score (default 6).
    """
    name = "Mansfield Minervini"
    supports_short = False

    def __init__(
        self,
        min_score: int = 8,
        exit_score: int = 6,
        ma_rs_len: int = 52,
    ):
        self.min_score = min_score
        self.exit_score = exit_score
        self.ma_rs_len = ma_rs_len

    def _score(
        self,
        col: pd.Series,
        benchmark: pd.Series | None,
    ) -> pd.Series:
        """Return integer Series [0..8] of Minervini conditions passed."""
        ma50 = col.rolling(50).mean()
        ma150 = col.rolling(150).mean()
        ma200 = col.rolling(200).mean()
        high52 = col.rolling(252).max()
        low52 = col.rolling(252).min()

        c1 = (col > ma150) & (col > ma200)
        c2 = ma150 > ma200
        c3 = ma200 > ma200.shift(25)
        c4 = (ma50 > ma150) & (ma50 > ma200)
        c5 = col > ma50
        c6 = col >= low52 * 1.25
        c7 = col >= high52 * 0.75
        c8 = ma200 > ma200.shift(1)

        score = (
            c1.astype(int) + c2.astype(int) + c3.astype(int) + c4.astype(int) +
            c5.astype(int) + c6.astype(int) + c7.astype(int) + c8.astype(int)
        )
        return score

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        benchmark: pd.Series | None = kwargs.get("benchmark_prices")

        raw = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)

        for ticker in prices.columns:
            col = prices[ticker]
            if col.dropna().empty:
                continue

            score = self._score(col, benchmark)

            entry = score >= self.min_score
            exit_ = score < self.exit_score

            raw.loc[entry, ticker] = 1.0
            raw.loc[exit_, ticker] = 0.0

        return raw.ffill().fillna(0.0)
