# src/backtesting/interfaces.py
"""
Standard abstract base classes for the walk-forward backtesting engine.
All concrete strategies and optimizers must implement these contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class TradingStrategy(ABC):
    """
    Generates trading signals for a universe of assets.

    generate_signals() must return a DataFrame with the same shape as `prices`.
    Values: +1 = long, -1 = short, 0 = flat, NaN = no opinion (asset excluded).
    Implementations must NOT use future prices (no lookahead bias).
    """
    name: str
    supports_short: bool = True

    @abstractmethod
    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Parameters
        ----------
        prices : pd.DataFrame
            DatetimeIndex rows × ticker columns. Adjusted close prices.

        Returns
        -------
        pd.DataFrame
            Same shape as `prices`. Values ∈ {+1, 0, -1, NaN}.
        """


class Universe:
    """Definition of a tradable asset universe."""

    def __init__(
        self,
        name: str,
        tickers: list[str],
        benchmark_ticker: str,
        display_name: str | None = None,
        fallback_benchmark: str | None = None,
        sectors: dict | None = None,
        data_source: str = "yfinance",
        frequency: str = "daily",
    ):
        self.name = name
        self.display_name = display_name or name
        self.tickers = tickers
        self.benchmark_ticker = benchmark_ticker
        self.fallback_benchmark = fallback_benchmark
        self.sectors = sectors  # sector_name -> {"etf": str, "members": list[str]}
        self.data_source = data_source
        self.frequency = frequency


class PortfolioOptimizer(ABC):
    """
    Converts a signal vector into portfolio weights.

    compute_weights() must satisfy:
        abs(long_weights).sum()  <= 1.0
        abs(short_weights).sum() <= 1.0
    """
    name: str

    @abstractmethod
    def compute_weights(
        self,
        signals: pd.Series,
        returns_history: pd.DataFrame,
        **kwargs,
    ) -> pd.Series:
        """
        Parameters
        ----------
        signals : pd.Series
            index=tickers, values ∈ {+1, 0, -1}
        returns_history : pd.DataFrame
            DatetimeIndex rows × ticker columns of daily returns (trailing window).

        Returns
        -------
        pd.Series
            index=tickers, values=float weights.
            Positive = long, negative = short.
        """
